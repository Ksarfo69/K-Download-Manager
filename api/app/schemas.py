from pydantic import BaseModel

from app.enums import DirectoryFileType


class DownloadRequest(BaseModel):
    url: str


class KDMSettingsPayload(BaseModel):
    max_connections: int
    chunk_size: int
    downloads_location: str


class DownloadFileStateResponse(BaseModel):
    id: str
    url: str
    max_connections: int
    chunk_size: int
    save_as: str | None
    filename: str
    chunks_folder: str
    downloaded_size: int
    content_size: int
    formatted_content_size: str
    complete: bool
    in_progress: bool
    date_added: str
    download_start: str
    downloaded_size_this_session: int
    downloaded_file_path: str | None


class DirectoryItem(BaseModel):
    filename: str
    kind: DirectoryFileType


class DirectoryListing(BaseModel):
    base: str
    items: list[DirectoryItem]


class DirectoryListingRequest(BaseModel):
    base: str
    filename: str
