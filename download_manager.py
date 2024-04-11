import argparse
import asyncio
import json
import os.path
import shutil
import signal
from datetime import datetime

import aiohttp

DB_PATH = os.path.join(os.path.realpath(os.path.dirname(__file__)), "dm.json")
if not os.path.exists(DB_PATH):
    with open(DB_PATH, "w") as f:
        f.write("{}")

DOWNLOADS_FOLDER = os.path.join(os.path.realpath(os.path.dirname(__file__)), "downloads")
if not os.path.exists(DOWNLOADS_FOLDER):
    os.makedirs(DOWNLOADS_FOLDER)

CHUNKS_FOLDER = os.path.join(os.path.realpath(os.path.dirname(__file__)), "chunks")
if not os.path.exists(CHUNKS_FOLDER):
    os.makedirs(CHUNKS_FOLDER)


class DownloadFileState:
    def __init__(self,
                 url,
                 max_connections,
                 chunk_size,
                 cap,
                 save_as,
                 filename,
                 chunks_folder,
                 downloaded_size,
                 content_size,
                 formatted_content_size,
                 complete,
                 in_progress,
                 download_start,
                 downloaded_size_this_session,
                 downloaded_file_path):
        self.url = url
        self.max_connections = max_connections
        self.chunk_size = chunk_size
        self.cap = cap
        self.save_as = save_as
        self.filename = filename
        self.chunks_folder = chunks_folder
        self.downloaded_size = downloaded_size
        self.content_size = content_size
        self.complete = complete
        self.in_progress = in_progress
        self.formatted_content_size = formatted_content_size
        self.download_start = download_start
        self.downloaded_size_this_session = downloaded_size_this_session
        self.downloaded_file_path = downloaded_file_path

    def __hash__(self):
        return self.url.__hash__()

    def __eq__(self, other):
        return self.url == other.url

    def to_dict(self):
        serial = self.__dict__

        return serial

    @classmethod
    def from_dict(cls, serial: dict):
        obj = DownloadFileState(**serial)

        return obj

    def new_session(self):
        self.downloaded_size_this_session = 0
        self.in_progress = False

    def add_chunk(self, size: int):
        self.downloaded_size += size
        self.downloaded_size_this_session += size

        if self.downloaded_size >= self.content_size:
            self.in_progress = False
            self.complete = True


class DownloadManager:
    def __init__(self):
        with open(DB_PATH, 'r') as f:
            json_ = json.load(f)
            self.downloads = {}
            for k, v in json_.items():
                dfs = DownloadFileState.from_dict(v)
                dfs.new_session()
                self.downloads[k] = dfs

        self.running_tasks = 0
        self.lock = asyncio.Lock()
        asyncio.create_task(self.start_sigint_listener())
        asyncio.create_task(self.__track_download_state_changes())
        asyncio.create_task(self.__print_download_stats())

    async def add(self, **kwargs):
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
        url = kwargs['url']
        if url in self.downloads:
            dfs: DownloadFileState = self.downloads[url]
            if dfs.complete:
                print(f"File already downloaded. Path: {dfs.downloaded_file_path}")
            else:
                max_connections: int = kwargs.get('max_connections')
                if max_connections:
                    dfs.max_connections = max_connections
                await self.resume(dfs)
        else:
            await self.download(**kwargs)

    async def download(self, url, max_connections=8, chunk_size=512000, cap=None, save_as=None):
        filename: str = save_as if save_as else await self.__extract_filename(url)
        chunks_folder: str = await self.__get_chunks_folder_name(filename)
        content_size: int = await self.__get_content_size(url=url)
        formatted_content_size: str = await self.__calculate_semantic_size(content_size)

        if not os.path.exists(chunks_folder):
            os.makedirs(chunks_folder)

        downloaded_size = 0
        download_start = datetime.now()

        dfs: DownloadFileState = DownloadFileState(
            url=url,
            max_connections=max_connections,
            chunk_size=chunk_size,
            cap=cap,
            save_as=save_as,
            filename=filename,
            chunks_folder=chunks_folder,
            downloaded_size=downloaded_size,
            content_size=content_size,
            in_progress=True,
            complete=False,
            formatted_content_size=formatted_content_size,
            download_start=download_start.isoformat(),
            downloaded_size_this_session=0,
            downloaded_file_path=None
        )

        self.downloads[dfs.url] = dfs
        await self.__update_download_states_now()

        formatted_cap = await self.__calculate_semantic_size(cap) if cap else None
        print(f"Downloading url: {url}, "
              f"max connections: {max_connections}, "
              f"chunk_size: {chunk_size}, "
              f"cap:{f'{formatted_cap}' if cap else None}")

        await self.download_in_chunks(offset=0, dfs=dfs)

    async def resume(self, dfs: DownloadFileState):
        print(f"Resuming file {dfs.filename}...")
        dfs.download_start = datetime.now().isoformat()
        dfs.in_progress = True
        dfs.downloaded_size = 0

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
        await self.download_in_chunks(offset=offset, dfs=dfs, missing_chunks=missing_chunks)

    async def download_in_chunks(self, offset, dfs: DownloadFileState, missing_chunks: None | list = None):
        cap = dfs.cap
        content_size = dfs.content_size
        max_connections = dfs.max_connections
        chunk_size = dfs.chunk_size
        limit = cap if cap and cap < content_size else content_size

        while missing_chunks or dfs.downloaded_size < limit:
            if self.running_tasks < max_connections:
                if len(missing_chunks) > 0:
                    chunk_range_ = missing_chunks.pop()
                    start_end = chunk_range_.split("-")
                    start = int(start_end[0])
                    end = int(start_end[1])

                    asyncio.create_task(self.chunk_download_task(dfs, start, end))
                else:
                    if offset < limit:
                        start = offset
                        remaining_size = content_size - offset
                        if remaining_size <= chunk_size:
                            end = content_size
                            offset = content_size
                        else:
                            end = offset + chunk_size - 1
                            offset += chunk_size

                        asyncio.create_task(self.chunk_download_task(dfs, start, end))

                self.running_tasks += 1
            else:
                await asyncio.sleep(0.5)

        downloaded_file_path = await self.__combine_chunks(dfs)

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

    async def __track_download_state_changes(self):
        while True:
            payload = {k: v.to_dict() for k, v in self.downloads.items()}
            with open(DB_PATH, 'w') as f:
                json.dump(payload, f, indent=4)

            await asyncio.sleep(5)

    async def __update_download_states_now(self):
        payload = {k: v.to_dict() for k, v in self.downloads.items()}
        with open(DB_PATH, 'w') as f:
            json.dump(payload, f, indent=4)

    async def __print_download_stats(self):
        while True:
            items: [str, DownloadFileState] = self.downloads.copy().items()
            for _, dfs in items:
                if dfs.in_progress:
                    download_start = datetime.fromisoformat(dfs.download_start)
                    seconds_elapsed = (datetime.now() - download_start).seconds or 1

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

                    print(
                        f'\rFilename: {dfs.filename} |'
                        f' Progress: {percentage}% |'
                        f' Download Speed: {res[0]} |'
                        f' Downloaded: {res[1]}/{dfs.formatted_content_size} |'
                        f' ETA: {res[2]}',
                        end='', flush=True)

            await asyncio.sleep(1)

    async def __get_chunks_folder_name(self, filename: str):
        print("Creating folder for chunks ...")
        folder_name = ""

        for c in filename:
            folder_name += str(ord(c))

        folder_path = os.path.join(CHUNKS_FOLDER, folder_name)

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

    async def __combine_chunks(self, dfs: DownloadFileState):
        folder = dfs.chunks_folder
        filename = dfs.filename

        print(f"\nCombining chunks in folder {folder} ...")
        output_file_path = os.path.join(DOWNLOADS_FOLDER, filename)

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
            await self.__update_download_states_now()
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


async def main():
    parser = argparse.ArgumentParser(description="File Downloader with pause and resume capability.")
    parser.add_argument('url', help="URL parameter")
    parser.add_argument('--max-connections', type=int, default=8, help="Maximum number of connections")
    parser.add_argument('--chunk-size', type=int, default=512000, help="Chunk size")
    parser.add_argument('--cap', type=int, help="Size Cap parameter")
    parser.add_argument('--save-as', help="Save as parameter")

    args = parser.parse_args()

    dm = DownloadManager()

    await dm.add(**args.__dict__)


if __name__ == "__main__":
    asyncio.run(main())

cmd = "python download_manager.py https://dl4.dl1acemovies.xyz/dl/English/Series/Invincible/S02/720p/Invincible.S02E08.720p.AMZN.WEB-DL.2CH.H.264.AM.mkv --max-connections 10 --chunk-size 512000"
