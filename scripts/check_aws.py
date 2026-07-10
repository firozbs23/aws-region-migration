#!/usr/bin/env python3
"""Verify S3 access before starting the app."""
import os
import sys

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError


def main() -> int:
    region = os.environ.get("AWS_REGION", "ap-southeast-1")
    bucket = os.environ.get("S3_BUCKET_DOCUMENTS", "")
    public = os.environ.get("S3_PUBLIC_ACCESS", "true").lower() in {"1", "true", "yes"}
    key_id = (os.environ.get("AWS_ACCESS_KEY_ID") or "").strip()
    has_static_keys = bool(key_id and (os.environ.get("AWS_SECRET_ACCESS_KEY") or "").strip())

    print(f"Checking S3 access (region={region}, public={public})")

    if public and not has_static_keys:
        print("Using unsigned S3 requests (public bucket policy)")
        s3 = boto3.client(
            "s3",
            region_name=region,
            config=Config(signature_version=UNSIGNED),
        )
    elif has_static_keys:
        print("Using AWS_ACCESS_KEY_ID from .env")
        s3 = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=key_id,
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"].strip(),
        )
    else:
        print("Using EC2 instance role via IMDS")
        try:
            session = boto3.Session(region_name=region)
            creds = session.get_credentials()
            if creds is None:
                raise NoCredentialsError()
            print(f"OK: credentials found (access key ...{creds.access_key[-4:]})")
            s3 = session.client("s3")
        except (NoCredentialsError, PartialCredentialsError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            print(
                "\nFix: set S3_PUBLIC_ACCESS=true in .env (public buckets), or attach "
                "an EC2 IAM role, or set AWS_ACCESS_KEY_ID/SECRET for local dev.",
                file=sys.stderr,
            )
            return 1

    if not bucket:
        print("WARN: S3_BUCKET_DOCUMENTS not set, skipping bucket probe")
        return 0

    try:
        s3.head_bucket(Bucket=bucket)
        print(f"OK: can reach bucket s3://{bucket}/")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        print(f"FAIL: cannot access bucket '{bucket}': {code} {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
