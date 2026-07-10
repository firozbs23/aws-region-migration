import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import relationship

from app.database import Base


class FileRecord(Base):
    """One row per uploaded file. The binary content itself lives in S3;
    this table only stores the pointer (s3_bucket/s3_key) plus metadata."""

    __tablename__ = "files"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename = Column(String(512), nullable=False)
    # 700 chars, not S3's max of 1024: SQL Server rejects a UNIQUE index on
    # a non-Unicode column wider than 900 bytes, and our own generated keys
    # ("uploads/{uuid4}/{filename}") never get close to 700 in practice.
    s3_key = Column(String(700), nullable=False, unique=True)
    s3_bucket = Column(String(255), nullable=False)
    category = Column(String(32), nullable=False)  # documents | media | archives
    content_type = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    checksum_sha256 = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tags = relationship("FileTag", back_populates="file", cascade="all, delete-orphan")
    logs = relationship("AccessLog", back_populates="file", cascade="all, delete-orphan")


class FileTag(Base):
    """Arbitrary key/value metadata attached to a file (e.g. department=finance)."""

    __tablename__ = "file_tags"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(Uuid(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    tag_key = Column(String(128), nullable=False)
    tag_value = Column(String(512), nullable=False)

    file = relationship("FileRecord", back_populates="tags")


class AccessLog(Base):
    """Audit trail: every upload/download/delete against a file."""

    __tablename__ = "access_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(Uuid(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(32), nullable=False)  # upload | download | delete | view
    accessed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    note = Column(String(255), nullable=True)

    file = relationship("FileRecord", back_populates="logs")
