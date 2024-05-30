import os
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Boolean, DateTime

from app.models import Base
from app.schemas import DownloadFileStateResponse


class DownloadFileState(Base):
    __tablename__ = 'download_file_state'

    id = Column(String, primary_key=True)
    url = Column(String, nullable=False)
    max_connections = Column(Integer, nullable=False)
    chunk_size = Column(Integer, nullable=False)
    save_as = Column(String)
    filename = Column(String, nullable=False)
    chunks_folder = Column(String, nullable=False)
    downloaded_size = Column(Integer, nullable=False)
    content_size = Column(Integer, nullable=False)
    formatted_content_size = Column(String)
    complete = Column(Boolean, nullable=False)
    in_progress = Column(Boolean, nullable=False)
    date_added = Column(DateTime, nullable=False)
    download_start = Column(DateTime, nullable=False)
    downloaded_size_this_session = Column(Integer, nullable=False)
    downloaded_file_path = Column(String)

    def __init__(self,
                 url,
                 max_connections,
                 chunk_size,
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
        self.id = uuid.uuid4().hex
        self.url = url
        self.max_connections = max_connections
        self.chunk_size = chunk_size
        self.save_as = save_as
        self.filename = filename
        self.chunks_folder = chunks_folder
        self.downloaded_size = downloaded_size
        self.content_size = content_size
        self.complete = complete
        self.in_progress = in_progress
        self.formatted_content_size = formatted_content_size
        self.download_start = download_start
        self.date_added = datetime.now()
        self.downloaded_size_this_session = downloaded_size_this_session
        self.downloaded_file_path = downloaded_file_path

    def __hash__(self):
        return self.url.__hash__()

    def __eq__(self, other):
        return self.url == other.url

    def init_because_missing(self):
        self.new_session()
        self.complete = False
        os.makedirs(self.chunks_folder)

    def new_session(self):
        self.downloaded_size_this_session = 0
        self.in_progress = False

    def resuming(self):
        self.download_start = datetime.now()
        self.in_progress = True
        self.downloaded_size = 0

    def pausing(self):
        self.in_progress = False

        if self.downloaded_size >= self.content_size:
            self.complete = True

    def add_chunk(self, size: int):
        self.downloaded_size += size
        self.downloaded_size_this_session += size

        if self.downloaded_size >= self.content_size:
            self.in_progress = False
            self.complete = True

    def to_pydantic_model(self):
        return DownloadFileStateResponse(
            id=self.id,
            url=self.url,
            max_connections=self.max_connections,
            chunk_size=self.chunk_size,
            save_as=self.save_as,
            filename=self.filename,
            chunks_folder=self.chunks_folder,
            downloaded_size=self.downloaded_size,
            content_size=self.content_size,
            formatted_content_size=self.formatted_content_size,
            complete=self.complete,
            in_progress=self.in_progress,
            date_added=str(self.date_added),
            download_start=str(self.download_start),
            downloaded_size_this_session=self.downloaded_size_this_session,
            downloaded_file_path=self.downloaded_file_path,
        )
