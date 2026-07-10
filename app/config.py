"""
Centralised application configuration.

Every setting is read from environment variables (or a local .env file for
development). This is the ONLY file that needs to change when the stack is
migrated from one AWS region to another.
"""
from functools import lru_cache
import re

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DB_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- Application metadata ----
    app_name: str = "File Backup Service"
    app_env: str = "poc"  # poc | staging | production

    # ================================================================
    # REGION-DEPENDENT SETTINGS -- the entire blast radius of a region
    # migration. Everything else in the codebase is region-agnostic.
    #   Singapore -> ap-southeast-1 (source)   Sydney -> ap-southeast-2 (target)
    # Full cutover procedure: doc/POC.pdf, "Region Migration Runbook".
    # ================================================================
    aws_region: str = "ap-southeast-1"

    # One bucket per upload category rather than one for everything (IAM
    # scoping, lifecycle policy, blast-radius isolation -- see app/s3_client.py).
    s3_bucket_documents: str = "myco-file-backup-documents-sg"
    s3_bucket_media: str = "myco-file-backup-media-sg"
    s3_bucket_archives: str = "myco-file-backup-archives-sg"

    # RDS SQL Server connection (use DB_* vars -- do NOT use DATABASE_URL).
    db_host: str = "file-backup-db.c9g4u6ekudby.ap-southeast-1.rds.amazonaws.com"
    db_port: int = 1433
    db_user: str = "admin"
    db_password: str = ""
    db_name: str = "filebackup"
    # ================================================================

    # ---- AWS credentials ----
    # On EC2 in every environment (POC and production) these are left
    # unset and the app relies on the instance's IAM role instead. They
    # only exist here so the app can also run from a laptop for local dev.
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # ---- S3 behaviour ----
    # When true, buckets are public (bucket policy Principal "*") and the app
    # uses unsigned S3 requests -- no IAM role or access keys required.
    s3_public_access: bool = True
    s3_presigned_url_expiry_seconds: int = 3600
    max_upload_size_mb: int = 100

    # ---- DB connection pool ----
    db_pool_size: int = 5
    db_max_overflow: int = 5

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        self.db_host = self.db_host.strip()
        self.db_user = self.db_user.strip()
        self.db_password = self.db_password.strip()
        self.db_name = self.db_name.strip()
        self.aws_region = self.aws_region.strip()

        # Empty strings in .env must not block the EC2 instance IAM role.
        if not (self.aws_access_key_id or "").strip():
            self.aws_access_key_id = None
        else:
            self.aws_access_key_id = self.aws_access_key_id.strip()
        if not (self.aws_secret_access_key or "").strip():
            self.aws_secret_access_key = None
        else:
            self.aws_secret_access_key = self.aws_secret_access_key.strip()

        if not self.db_host:
            raise ValueError("DB_HOST must be set to your RDS endpoint.")
        if self.db_host in {"localhost", "127.0.0.1", "db"}:
            raise ValueError(
                f"DB_HOST is '{self.db_host}' but must be your RDS endpoint "
                f"(e.g. file-backup-db.xxxxx.ap-southeast-1.rds.amazonaws.com)."
            )
        if not self.db_password:
            raise ValueError("DB_PASSWORD must be set to your RDS master password.")
        if not _DB_NAME_RE.match(self.db_name):
            raise ValueError(f"DB_NAME '{self.db_name}' is not a valid SQL Server identifier.")
        return self

    def bucket_for_category(self, category: str) -> str:
        return {
            "documents": self.s3_bucket_documents,
            "media": self.s3_bucket_media,
            "archives": self.s3_bucket_archives,
        }[category]


@lru_cache
def get_settings() -> Settings:
    return Settings()
