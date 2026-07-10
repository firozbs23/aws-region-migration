import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class UploadCategory(str, Enum):
    documents = "documents"
    media = "media"
    archives = "archives"


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag_key: str
    tag_value: str


class AccessLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    accessed_at: datetime
    note: str | None = None


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    category: str
    s3_bucket: str
    s3_key: str
    content_type: str
    size_bytes: int
    checksum_sha256: str | None = None
    description: str | None = None
    uploaded_at: datetime
    updated_at: datetime
    tags: list[TagOut] = []


class FileListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    category: str
    content_type: str
    size_bytes: int
    description: str | None = None
    uploaded_at: datetime


class PresignedDownload(BaseModel):
    url: str
    expires_in_seconds: int


class RegionInfo(BaseModel):
    aws_region: str
    s3_bucket_documents: str
    s3_bucket_media: str
    s3_bucket_archives: str
    database_host: str
    app_env: str
