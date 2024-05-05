from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class DownloadRequest(BaseModel):
    url: str


class KDMSettingsPayload(BaseModel):
    max_connections: int = 8
    chunk_size: int = 512000
    downloads_location: str = Path.home() / 'Downloads'


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
    download_start: datetime
    downloaded_size_this_session: int
    downloaded_file_path: str | None
