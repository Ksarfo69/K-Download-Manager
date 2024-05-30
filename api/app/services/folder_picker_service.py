import os
from pathlib import Path

from fastapi import HTTPException

from app.enums import DirectoryFileType
from app.schemas import DirectoryItem, DirectoryListingRequest

from app.schemas import DirectoryListing


class FolderPicker:
    async def home(self):
        home = Path.home()

        r = await self.parse_files(home)

        return r

    async def goto(self, dlr: DirectoryListingRequest):
        if dlr.filename == "..":
            path = Path(dlr.base).parent
        else:
            path = Path(os.path.join(dlr.base, dlr.filename))

        if not path.exists():
            msg = "Provided path does not exist"
            print(msg)
            raise HTTPException(status_code=400, detail=msg)

        r = await self.parse_files(path)

        return r

    async def select(self, dlr: DirectoryListingRequest):
        path = Path(os.path.join(dlr.base, dlr.filename))

        if not path.exists():
            msg = "Provided path does not exist"
            print(msg)
            raise HTTPException(status_code=400, detail=msg)

        return str(path)

    async def parse_files(self, base):
        files = []

        try:
            for filename in os.listdir(base):
                abs_path = os.path.join(base, filename)
                if not filename.startswith("."):
                    files.append(DirectoryItem(filename=filename, kind=DirectoryFileType.FOLDER if os.path.isdir(
                        abs_path) else DirectoryFileType.FILE))

            return DirectoryListing(base=str(base), items=files)
        except PermissionError:
            msg = "Insufficient permission to access this folder."
            print(msg)
            raise HTTPException(status_code=403, detail=msg)


fp = FolderPicker()
