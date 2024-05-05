import asyncio
import os.path
import shutil
import signal
from datetime import datetime

import aiohttp
from fastapi import HTTPException
from sqlalchemy import desc

from app.models.download_file_state import DownloadFileState
from app.models.kdm_settings import KDMSettings
from app.schemas import KDMSettingsPayload
from app.services.db_service import sadbs


class KDownloadService:
    def __init__(self):
        self.lock = None
        self.running_tasks = None

    async def init(self):
        await sadbs.update(DownloadFileState, {DownloadFileState.downloaded_size_this_session: 0,
                                               DownloadFileState.in_progress: False})

        self.running_tasks = 0
        self.lock = asyncio.Lock()
        asyncio.create_task(self.start_sigint_listener())

    async def add(self, url):
        print("-" * 160)
        print(r"""
 _                       _______ _________ _        _______        ______   _______           _        _        _______  _______  ______   _______  _______   
| \    /\               (  ____ \\__   __/( \      (  ____ \      (  __  \ (  ___  )|\     /|( (    /|( \      (  ___  )(  ___  )(  __  \ (  ____ \(  ____ )  
|  \  / /               | (    \/   ) (   | (      | (    \/      | (  \  )| (   ) || )   ( ||  \  ( || (      | (   ) || (   ) || (  \  )| (    \/| (    )|  
|  (_/ /      _____     | (__       | |   | |      | (__          | |   ) || |   | || | _ | ||   \ | || |      | |   | || (___) || |   ) || (__    | (____)|  
|   _ (      (_____)    |  __)      | |   | |      |  __)         | |   | || |   | || |( )| || (\ \) || |      | |   | ||  ___  || |   | ||  __)   |     __)  
|  ( \ \                | (         | |   | |      | (            | |   ) || |   | || || || || | \   || |      | |   | || (   ) || |   ) || (      | (\ (     
|  /  \ \               | )      ___) (___| (____/\| (____/\      | (__/  )| (___) || () () || )  \  || (____/\| (___) || )   ( || (__/  )| (____/\| ) \ \__  
|_/    \/               |/       \_______/(_______/(_______/      (______/ (_______)(_______)|/    )_)(_______/(_______)|/     \|(______/ (_______/|/   \__/                                                                                                                                                                                                                                                                                                               
        """)

        exists = await sadbs.get(DownloadFileState, condition=DownloadFileState.url == url)
        kdm_settings: KDMSettings = await self.get_preferences()
        if exists:
            dfs: DownloadFileState = exists
            if dfs.in_progress:
                raise HTTPException(status_code=409, detail="Already in progress.")
            elif dfs.complete and os.path.exists(dfs.downloaded_file_path):
                msg = f"File already downloaded. Path: {dfs.downloaded_file_path}"
                print(msg)
                raise HTTPException(status_code=409, detail=msg)
            elif dfs.complete:
                dfs.init_because_missing()
                return await self.resume(dfs, kdm_settings)
            else:
                return await self.resume(dfs, kdm_settings)
        else:
            return await self.download(url, kdm_settings)

    async def download(self, url, kdm_settings: KDMSettings, save_as=None) -> DownloadFileState:
        filename: str = save_as if save_as else await self.__extract_filename(url)
        content_size: int = await self.__get_content_size(url=url)
        formatted_content_size: str = await self.__calculate_semantic_size(content_size)
        chunks_folder: str = await self.__get_chunks_folder_name(filename, kdm_settings.downloads_location)

        if not os.path.exists(chunks_folder):
            os.makedirs(chunks_folder)

        downloaded_size = 0
        download_start = datetime.now()

        dfs: DownloadFileState = DownloadFileState(
            url=url,
            max_connections=kdm_settings.max_connections,
            chunk_size=kdm_settings.chunk_size,
            save_as=save_as,
            filename=filename,
            chunks_folder=chunks_folder,
            downloaded_size=downloaded_size,
            content_size=content_size,
            in_progress=True,
            complete=False,
            formatted_content_size=formatted_content_size,
            download_start=download_start,
            downloaded_size_this_session=0,
            downloaded_file_path=None
        )

        await sadbs.insert(dfs)

        print(f"Downloading url: {url}, "
              f"max connections: {kdm_settings.max_connections}, "
              f"chunk_size: {kdm_settings.chunk_size}")

        asyncio.create_task(self.download_in_chunks(offset=0, dfs=dfs, kdm_settings=kdm_settings))

        r = dfs.to_pydantic_model()

        return r

    async def resume(self, dfs: DownloadFileState, kdm_settings: KDMSettings):
        print(f"Resuming file {dfs.filename}...")
        dfs.resuming()

        incomplete_chunks = []
        last_chunk_upper_bound = 0

        dir_files = os.listdir(dfs.chunks_folder)
        dir_files.sort(key=lambda x: int(x.split('/')[-1].split('-')[0]))

        if len(dir_files) == 0:
            offset = 0
            missing_chunks = None
        else:
            for filename in dir_files:
                if not filename[0].isdigit():
                    continue

                split_filename = filename.split("-")
                lower_chunk_bound = int(split_filename[0])
                upper_chunk_bound = int(split_filename[-1])
                last_chunk_upper_bound = max(last_chunk_upper_bound, upper_chunk_bound)

                file_path = os.path.join(dfs.chunks_folder, filename)
                file_size = os.path.getsize(file_path)

                if file_size >= (upper_chunk_bound - lower_chunk_bound + 1):
                    dfs.downloaded_size += file_size
                else:
                    self.running_tasks += 1
                    incomplete_chunks.append(self.chunk_download_task(dfs, lower_chunk_bound, upper_chunk_bound))

            offset = last_chunk_upper_bound + 1
            self.running_tasks += len(incomplete_chunks)
            missing_chunks = await self.__ensure_continuity(dfs, dir_files)

        print(f"Successfully resumed file {dfs.filename}, continuing download...")
        asyncio.create_task(self.download_in_chunks(offset=offset, dfs=dfs, missing_chunks=missing_chunks, kdm_settings=kdm_settings))

        r = dfs.to_pydantic_model()

        return r

    async def download_in_chunks(self,
                                 offset,
                                 dfs: DownloadFileState,
                                 kdm_settings: KDMSettings,
                                 missing_chunks: None | list = None):
        content_size = dfs.content_size
        max_connections = dfs.max_connections
        chunk_size = dfs.chunk_size

        while missing_chunks or dfs.downloaded_size < content_size:
            if self.running_tasks < max_connections:
                if missing_chunks and len(missing_chunks) > 0:
                    chunk_range_ = missing_chunks.pop()
                    start_end = chunk_range_.split("-")
                    start = int(start_end[0])
                    end = int(start_end[1])

                    asyncio.create_task(self.chunk_download_task(dfs, start, end))
                else:
                    if offset < content_size:
                        start = offset
                        remaining_size = content_size - offset
                        if remaining_size <= chunk_size:
                            end = content_size
                            offset = content_size
                        else:
                            end = offset + chunk_size - 1
                            offset += chunk_size

                        t = asyncio.create_task(self.chunk_download_task(dfs, start, end))

                self.running_tasks += 1
            else:
                await asyncio.sleep(0.5)

        downloaded_file_path = await self.__combine_chunks(dfs, kdm_settings)

        print(
            f"\nFile downloaded successfully, path: {downloaded_file_path}.")

    async def chunk_download_task(self, dfs: DownloadFileState, start, end):
        complete = False

        async with aiohttp.ClientSession() as session:
            tries = 0
            MAX_TRIES = 3

            while not complete and tries < MAX_TRIES:
                tries += 1
                try:
                    chunk = f"{start}-{end}"

                    chunk_response = await session.get(dfs.url, headers={'Range': f"bytes={chunk}"})

                    expected_bytes = (end - start + 1)

                    if chunk_response.status == 206 and chunk_response.content_length == expected_bytes:
                        data = await chunk_response.content.read()
                        output_file_path = os.path.join(dfs.chunks_folder, chunk)

                        with open(output_file_path, 'wb') as f:
                            f.write(data)

                        async with self.lock:
                            dfs.add_chunk(chunk_response.content_length)

                            await sadbs.insert(dfs)
                    else:
                        raise Exception(f"Expected {expected_bytes} but received {chunk_response.content_length}")

                    self.running_tasks -= 1
                    complete = True
                except Exception as e:
                    await asyncio.sleep(1)
                    if tries == MAX_TRIES:
                        await session.close()
                        print("\n")
                        exit(e)

    async def get_preferences(self):
        r = await sadbs.get_all(KDMSettings)

        if len(r) == 0:
            preferences = KDMSettings()
            await sadbs.insert(preferences)
        else:
            preferences: KDMSettings = r[0]

        return await preferences.to_pydantic_model()

    async def update_preferences(self, preferences: KDMSettingsPayload):
        r = await sadbs.get_all(KDMSettings)
        exists: KDMSettings = r[0]

        exists.max_connections = preferences.max_connections
        exists.chunk_size = preferences.chunk_size
        exists.downloads_location = preferences.downloads_location

        await sadbs.insert(exists)

    async def get_history(self, in_progress, start, limit):
        condition = DownloadFileState.in_progress == in_progress if in_progress else None
        r = await sadbs.get_all(DownloadFileState, condition=condition,
                                order_by=desc(DownloadFileState.download_start), offset=start, limit=limit)
        return [dfs.to_pydantic_model() for dfs in r]

    async def get_download_state_events(self):
        events = None
        items: list[DownloadFileState] = await sadbs.get_all(DownloadFileState,
                                                             condition=DownloadFileState.in_progress == True)
        for dfs in items:
            events = events or []
            seconds_elapsed = (datetime.now() - dfs.download_start).seconds or 1

            percentage = round((dfs.downloaded_size / dfs.content_size) * 100, 2)

            download_speed_task = asyncio.create_task(
                self.__calculate_download_speed(dfs.downloaded_size_this_session, seconds_elapsed))
            formatted_downloaded_size__task = asyncio.create_task(
                self.__calculate_semantic_size(dfs.downloaded_size))
            est_time_remaining_task = asyncio.create_task(
                self._estimate_remaining_time(dfs.content_size,
                                              dfs.downloaded_size,
                                              dfs.downloaded_size_this_session,
                                              seconds_elapsed))

            tasks = [download_speed_task, formatted_downloaded_size__task, est_time_remaining_task]

            res = await asyncio.gather(*tasks)

            event = {
                "Filename": dfs.filename,
                "Progress": f'{percentage}%',
                "Download Speed": res[0],
                "Downloaded": f'{res[1]}/{dfs.formatted_content_size}',
                "ETA": res[2],
            }

            print(
                f'\rFilename: {dfs.filename} |'
                f' Progress: {percentage}% |'
                f' Download Speed: {res[0]} |'
                f' Downloaded: {res[1]}/{dfs.formatted_content_size} |'
                f' ETA: {res[2]}',
                end='', flush=True)

            events.append(event)

        return events

    async def __get_chunks_folder_name(self, filename: str, base_dir: str):
        print("Creating folder for chunks ...")
        folder_name = ""

        for c in filename:
            folder_name += str(ord(c))

        chunks_folder = os.path.join(base_dir, ".kdm_chunks")

        if not os.path.exists(chunks_folder):
            os.makedirs(chunks_folder)

        folder_path = os.path.join(chunks_folder, folder_name)

        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        print(f"Created folder for chunks at {folder_name}")
        return folder_path

    async def __extract_filename(self, url: str):
        print("Extracting filename ...")
        without_query_param_tokens = url.split("?")
        first_token = without_query_param_tokens[0]
        without_path_param_tokens = first_token.split("/")
        filename = without_path_param_tokens[-1]

        filename = filename[-100:]  # 100 character limit

        print(f"Extracted filename as {filename}")

        return filename

    async def __get_content_size(self, url: str):
        print("Retrieving content size from server ...")

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Range': 'bytes=0-0'
                }

                response = await session.get(url, headers=headers)
                response_headers = response.headers
                content_range = response_headers.get('Content-Range')

                if not content_range:
                    exit(
                        "Failed to retrieve content size from server. Please ensure the server supports partial content delivery.")

                content_size = int(content_range.split('/')[1]) - 1

                formatted_content_size = await self.__calculate_semantic_size(content_size)

                print(f"Retrieved content size from server. Content size: {formatted_content_size}")

                return content_size
        except:
            raise HTTPException(status_code=400, detail="Failed to retrieve content size from server. Please ensure the server supports partial content delivery.")

    async def __calculate_semantic_size(self, _bytes: int):
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

        i = 0
        while _bytes >= 1024:
            _bytes /= 1024
            i += 1

        unit = units[i]

        res = f"{round(_bytes, 2)}{unit}"

        return res

    async def __calculate_download_speed(self, downloaded_size: int, seconds_elapsed: int):
        if downloaded_size == 0.0:
            return "----"
        else:
            bytes_downloaded_per_sec = downloaded_size / seconds_elapsed
            formatted_size = await self.__calculate_semantic_size(bytes_downloaded_per_sec)

            return f'{formatted_size}/s'

    async def _estimate_remaining_time(self, content_size: int, downloaded_size: int, downloaded_size_this_session: int,
                                       seconds_elapsed: int):
        if downloaded_size_this_session == 0.0:
            return "----"
        else:
            bytes_downloaded_per_sec = downloaded_size_this_session / seconds_elapsed

            est_seconds_remaining = round((content_size - downloaded_size) / bytes_downloaded_per_sec)

            # Calculate days, hours, minutes, and remaining seconds
            days = 0
            hours = 0
            minutes = 0

            ONE_DAY = 86400
            ONE_HOUR = 3600
            ONE_MINUTE = 60

            if est_seconds_remaining >= ONE_DAY:
                days = est_seconds_remaining // ONE_DAY
                est_seconds_remaining = est_seconds_remaining - (days * ONE_DAY)

            if est_seconds_remaining >= ONE_HOUR:
                hours = est_seconds_remaining // ONE_HOUR
                est_seconds_remaining = est_seconds_remaining - (hours * ONE_HOUR)

            if est_seconds_remaining >= ONE_MINUTE:
                minutes = est_seconds_remaining // ONE_MINUTE
                est_seconds_remaining = est_seconds_remaining - (minutes * ONE_MINUTE)

            seconds = est_seconds_remaining

            parts = []
            if days > 0:
                parts.append(f"{days} day{'s' if days > 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
            if minutes > 0:
                parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
            if seconds >= 0:
                parts.append(f"{seconds} second{'s' if seconds > 1 else ''}")

            res = " ".join(parts)

            return res

    async def __ensure_continuity(self, dfs: DownloadFileState, files: list) -> list | None:
        chunk_size = dfs.chunk_size
        content_size = dfs.content_size
        offset = 0
        overflow = dfs.content_size % chunk_size

        missing_chunks = []
        for filename in files:
            lower_bound = int(filename.split("-")[0])
            while offset < lower_bound:
                missing_chunks.append(f"{offset}-{offset + chunk_size - 1}")

                offset += chunk_size

            offset += (chunk_size if offset + chunk_size <= content_size else overflow)

        return missing_chunks if len(missing_chunks) > 0 else None

    async def __combine_chunks(self, dfs: DownloadFileState, kdm_settings: KDMSettings):
        folder = dfs.chunks_folder
        filename = dfs.filename

        print(f"\nCombining chunks in folder {folder} ...")
        output_file_path = os.path.join(kdm_settings.downloads_location, filename)

        with open(output_file_path, 'wb') as output_file:
            files = os.listdir(folder)
            files.sort(key=lambda x: int(x.split('/')[-1].split('-')[0]))

            missing_chunks = await self.__ensure_continuity(dfs, files)

            if missing_chunks:
                print("Found missing chunks...")
                await self.resume(dfs)
                return

            written_bytes = 0
            for chunk_name in files:
                chunk_path = os.path.join(folder, chunk_name)

                with open(chunk_path, 'rb') as input_file:
                    data = input_file.read()
                    written_bytes += len(data)
                    output_file.write(data)

            dfs.downloaded_file_path = output_file_path
            await sadbs.insert(dfs)
            shutil.rmtree(folder)
            formatted_size = await self.__calculate_semantic_size(written_bytes)
            print(f"Combined chunks in folder: {folder} as file: {filename}. {formatted_size} written.")

            return output_file_path

    async def start_sigint_listener(self):
        loop = asyncio.get_running_loop()
        sigint_received = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, sigint_received.set)
        await sigint_received.wait()

        # Cancel all running tasks
        tasks = asyncio.all_tasks()
        try:
            for task in tasks:
                task.cancel()

            await asyncio.gather(*tasks)
        except:
            ...


kdm = KDownloadService()
asyncio.create_task(kdm.init())
