"""
Thin wrapper around boto3's S3 client.

Every function takes the target bucket as an explicit argument rather than
reading a single global bucket name -- the app routes uploads across three
buckets by category (see app/config.py: bucket_for_category). Region is
still read exclusively from app.config.Settings, so this module never needs
to change when the stack is migrated to a new region.
"""
import hashlib
import logging
from urllib.parse import quote

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _client():
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        logger.debug("S3 client using explicit AWS credentials from env")
        return boto3.client("s3", **kwargs)

    if settings.s3_public_access:
        # Bucket policy grants Principal "*" -- use unsigned requests (no IAM/keys).
        logger.debug("S3 client using unsigned requests (public bucket policy)")
        return boto3.client(
            "s3",
            region_name=settings.aws_region,
            config=Config(signature_version=UNSIGNED),
        )

    logger.debug("S3 client using default credential chain (IAM role on EC2)")
    return boto3.client("s3", **kwargs)


def public_object_url(bucket: str, key: str) -> str:
    encoded_key = quote(key, safe="/")
    return f"https://{bucket}.s3.{settings.aws_region}.amazonaws.com/{encoded_key}"


class S3AccessDeniedError(Exception):
    """Raised when S3 rejects the call (wrong region, IAM policy, or creds)."""

    def __init__(self, bucket: str, operation: str, detail: str):
        self.bucket = bucket
        self.operation = operation
        super().__init__(detail)


class FileTooLargeError(Exception):
    pass


def _wrap_s3_error(exc: ClientError, bucket: str, operation: str) -> Exception:
    code = exc.response.get("Error", {}).get("Code", "")
    if code in {"AccessDenied", "403"}:
        if settings.s3_public_access:
            hint = (
                f"S3 {operation} denied on bucket '{bucket}'. Confirm the bucket policy "
                f"allows public {operation} and Block Public Access is off."
            )
        else:
            hint = (
                f"S3 {operation} denied on bucket '{bucket}' in region '{settings.aws_region}'. "
                f"Attach an EC2 IAM role with s3:PutObject, or set S3_PUBLIC_ACCESS=true "
                f"if buckets are public."
            )
        return S3AccessDeniedError(bucket, operation, hint)
    return exc


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
    use_anonymous = settings.s3_public_access and not (
        settings.aws_access_key_id and settings.aws_secret_access_key
    )

    if use_anonymous:
        # AWS rejects anonymous CreateMultipartUpload even with a public bucket
        # policy -- single PutObject is the only option without IAM credentials.
        chunks: list[bytes] = []
        total_size = 0
        while True:
            chunk = fileobj.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_bytes:
                raise FileTooLargeError(f"Upload exceeds max size of {max_bytes} bytes")
            hasher.update(chunk)
            chunks.append(chunk)
        body = b"".join(chunks)
        try:
            client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
        except ClientError as exc:
            raise _wrap_s3_error(exc, bucket, "PutObject") from exc
        return hasher.hexdigest(), total_size

    first_chunk = fileobj.read(chunk_size)
    if not first_chunk:
        try:
            client.put_object(Bucket=bucket, Key=key, Body=b"", ContentType=content_type)
        except ClientError as exc:
            raise _wrap_s3_error(exc, bucket, "PutObject") from exc
        return hasher.hexdigest(), 0

    try:
        multipart = client.create_multipart_upload(Bucket=bucket, Key=key, ContentType=content_type)
    except ClientError as exc:
        raise _wrap_s3_error(exc, bucket, "CreateMultipartUpload") from exc
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
    if settings.s3_public_access and not (
        settings.aws_access_key_id and settings.aws_secret_access_key
    ):
        return public_object_url(bucket, key)
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
