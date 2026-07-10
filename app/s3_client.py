"""
Thin wrapper around boto3's S3 client.

Every function takes the target bucket as an explicit argument rather than
reading a single global bucket name -- the app routes uploads across three
buckets by category (see app/config.py: bucket_for_category). Region is
still read exclusively from app.config.Settings, so this module never needs
to change when the stack is migrated to a new region.
"""
import hashlib
from urllib.parse import quote

import boto3

from app.config import get_settings

settings = get_settings()


def _client():
    kwargs = {"region_name": settings.aws_region}
    # Only pass explicit credentials for local dev. On EC2 (POC and
    # production) boto3 picks up the instance's IAM role automatically
    # and these stay None.
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("s3", **kwargs)


class FileTooLargeError(Exception):
    pass


def content_disposition_for_filename(filename: str) -> str:
    """Build a safe Content-Disposition header value for presigned downloads."""
    ascii_fallback = filename.replace("\\", "_").replace('"', "'")
    encoded = quote(filename, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def upload_fileobj(fileobj, bucket: str, key: str, content_type: str, max_bytes: int) -> tuple[str, int]:
    """Streams a file-like object to S3. Returns (sha256_checksum, size_bytes).
    Raises FileTooLargeError, aborting the multipart upload, if the stream
    exceeds max_bytes."""
    client = _client()
    hasher = hashlib.sha256()
    chunk_size = 8 * 1024 * 1024  # 8 MB

    first_chunk = fileobj.read(chunk_size)
    if not first_chunk:
        client.put_object(Bucket=bucket, Key=key, Body=b"", ContentType=content_type)
        return hasher.hexdigest(), 0

    multipart = client.create_multipart_upload(Bucket=bucket, Key=key, ContentType=content_type)
    upload_id = multipart["UploadId"]
    parts = []
    part_number = 1
    total_size = 0
    chunk = first_chunk

    try:
        while chunk:
            total_size += len(chunk)
            if total_size > max_bytes:
                raise FileTooLargeError(f"Upload exceeds max size of {max_bytes} bytes")
            hasher.update(chunk)
            part = client.upload_part(
                Bucket=bucket,
                Key=key,
                PartNumber=part_number,
                UploadId=upload_id,
                Body=chunk,
            )
            parts.append({"ETag": part["ETag"], "PartNumber": part_number})
            part_number += 1
            chunk = fileobj.read(chunk_size)

        client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except Exception:
        client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
        raise

    return hasher.hexdigest(), total_size


def delete_object(bucket: str, key: str) -> None:
    client = _client()
    client.delete_object(Bucket=bucket, Key=key)


def generate_presigned_download_url(bucket: str, key: str, filename: str) -> str:
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentDisposition": content_disposition_for_filename(filename),
        },
        ExpiresIn=settings.s3_presigned_url_expiry_seconds,
    )
