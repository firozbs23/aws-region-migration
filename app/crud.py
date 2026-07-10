import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def create_file_record(
    db: Session,
    *,
    original_filename: str,
    category: str,
    s3_key: str,
    s3_bucket: str,
    content_type: str,
    size_bytes: int,
    checksum_sha256: str,
    description: str | None,
    tags: dict[str, str] | None,
) -> models.FileRecord:
    record = models.FileRecord(
        original_filename=original_filename,
        category=category,
        s3_key=s3_key,
        s3_bucket=s3_bucket,
        content_type=content_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256,
        description=description,
    )
    db.add(record)
    db.flush()

    for key, value in (tags or {}).items():
        db.add(models.FileTag(file_id=record.id, tag_key=key, tag_value=value))

    db.add(models.AccessLog(file_id=record.id, action="upload"))
    db.commit()
    db.refresh(record)
    return record


def get_file(db: Session, file_id: uuid.UUID) -> models.FileRecord | None:
    # `.is_(False)` renders as "IS 0" on SQLAlchemy's mssql dialect, which
    # SQL Server rejects (T-SQL only allows IS with NULL). `== False` renders
    # as "= 0" everywhere, which is both valid T-SQL and portable.
    stmt = select(models.FileRecord).where(
        models.FileRecord.id == file_id, models.FileRecord.is_deleted == False  # noqa: E712
    )
    return db.scalar(stmt)


def list_files(
    db: Session, *, skip: int = 0, limit: int = 50, category: str | None = None
) -> list[models.FileRecord]:
    stmt = select(models.FileRecord).where(models.FileRecord.is_deleted == False)  # noqa: E712
    if category is not None:
        stmt = stmt.where(models.FileRecord.category == category)
    stmt = stmt.order_by(models.FileRecord.uploaded_at.desc()).offset(skip).limit(limit)
    return list(db.scalars(stmt))


def soft_delete_file(db: Session, record: models.FileRecord) -> None:
    record.is_deleted = True
    db.add(models.AccessLog(file_id=record.id, action="delete"))
    db.commit()


def log_action(db: Session, file_id: uuid.UUID, action: str, note: str | None = None) -> None:
    db.add(models.AccessLog(file_id=file_id, action=action, note=note))
    db.commit()


def get_logs(db: Session, file_id: uuid.UUID) -> list[models.AccessLog]:
    stmt = (
        select(models.AccessLog)
        .where(models.AccessLog.file_id == file_id)
        .order_by(models.AccessLog.accessed_at.desc())
    )
    return list(db.scalars(stmt))
