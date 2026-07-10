import json
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app import crud, s3_client
from app.config import get_settings
from app.database import get_db
from app.schemas import AccessLogOut, FileListItem, FileOut, PresignedDownload, UploadCategory

router = APIRouter(prefix="/api/v1/files", tags=["files"])
settings = get_settings()

_MEDIA_PREFIXES = ("image/", "video/", "audio/")
_ARCHIVE_CONTENT_TYPES = {
    "application/zip",
    "application/x-tar",
    "application/gzip",
    "application/x-gzip",
    "application/x-7z-compressed",
    "application/x-rar-compressed",
    "application/x-bzip2",
}


def safe_filename(filename: str | None) -> str:
    """Strip path components and fall back when the client omits a name."""
    if not filename:
        return "unnamed"
    name = os.path.basename(filename.replace("\\", "/"))
    return name or "unnamed"


def _infer_category(content_type: str) -> UploadCategory:
    if content_type in _ARCHIVE_CONTENT_TYPES:
        return UploadCategory.archives
    if content_type.startswith(_MEDIA_PREFIXES):
        return UploadCategory.media
    return UploadCategory.documents


@router.post(
    "/upload",
    response_model=FileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file and store it in S3",
)
async def upload_file(
    file: UploadFile = File(..., description="The binary file to back up"),
    category: UploadCategory | None = Form(
        None,
        description=(
            "Which of the three buckets to store this in: documents, media, "
            "or archives. If omitted, inferred from the file's content type."
        ),
    ),
    description: str | None = Form(None, description="Free-text description"),
    tags: str | None = Form(
        None, description='Optional JSON object of tags, e.g. {"department":"finance"}'
    ),
    db: Session = Depends(get_db),
):
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    content_type = file.content_type or "application/octet-stream"
    resolved_category = category or _infer_category(content_type)
    bucket = settings.bucket_for_category(resolved_category.value)

    parsed_tags: dict[str, str] = {}
    if tags:
        try:
            parsed_tags = json.loads(tags)
            if not isinstance(parsed_tags, dict) or not all(
                isinstance(v, str) for v in parsed_tags.values()
            ):
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=422, detail="tags must be a JSON object of string values"
            )

    original_filename = safe_filename(file.filename)
    key = f"uploads/{uuid.uuid4()}/{original_filename}"

    try:
        checksum, size = s3_client.upload_fileobj(file.file, bucket, key, content_type, max_bytes)
    except s3_client.FileTooLargeError:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds max upload size of {settings.max_upload_size_mb} MB",
        )

    try:
        record = crud.create_file_record(
            db,
            original_filename=original_filename,
            category=resolved_category.value,
            s3_key=key,
            s3_bucket=bucket,
            content_type=content_type,
            size_bytes=size,
            checksum_sha256=checksum,
            description=description,
            tags=parsed_tags,
        )
    except Exception:
        try:
            s3_client.delete_object(bucket, key)
        except Exception:
            pass
        raise
    return record


@router.get("", response_model=list[FileListItem], summary="List backed-up files")
def list_files(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    category: UploadCategory | None = None,
    db: Session = Depends(get_db),
):
    return crud.list_files(db, skip=skip, limit=limit, category=category.value if category else None)


@router.get("/{file_id}", response_model=FileOut, summary="Get file metadata")
def get_file(file_id: uuid.UUID, db: Session = Depends(get_db)):
    record = crud.get_file(db, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return record


@router.get(
    "/{file_id}/download",
    response_model=PresignedDownload,
    summary="Get a time-limited presigned S3 download URL",
)
def download_file(file_id: uuid.UUID, db: Session = Depends(get_db)):
    record = crud.get_file(db, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    url = s3_client.generate_presigned_download_url(
        record.s3_bucket, record.s3_key, record.original_filename
    )
    crud.log_action(db, record.id, "download")
    return PresignedDownload(
        url=url, expires_in_seconds=settings.s3_presigned_url_expiry_seconds
    )


@router.get("/{file_id}/logs", response_model=list[AccessLogOut], summary="Access log for a file")
def file_logs(file_id: uuid.UUID, db: Session = Depends(get_db)):
    record = crud.get_file(db, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return crud.get_logs(db, file_id)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a file")
def delete_file(file_id: uuid.UUID, db: Session = Depends(get_db)):
    record = crud.get_file(db, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    bucket, key = record.s3_bucket, record.s3_key
    crud.soft_delete_file(db, record)
    try:
        s3_client.delete_object(bucket, key)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="File was removed from the catalog but S3 cleanup failed; retry or reconcile manually.",
        ) from exc
