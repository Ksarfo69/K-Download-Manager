import uuid
from pathlib import Path

from sqlalchemy import Column, Integer, String

from app.models import Base
from app.schemas import KDMSettingsPayload


class KDMSettings(Base):
    __tablename__ = "kdm_settings"

    id = Column(String, primary_key=True, default=uuid.uuid4().hex)
    max_connections = Column(Integer, nullable=False)
    chunk_size = Column(Integer, nullable=False)
    downloads_location = Column(String, nullable=False)

    def __init__(self):
        self.max_connections = 8
        self.chunk_size = 512000
        self.downloads_location = str(Path.home() / 'Downloads')

    async def to_pydantic_model(self):
        return KDMSettingsPayload(
            max_connections=self.max_connections,
            chunk_size=self.chunk_size,
            downloads_location=self.downloads_location
        )
