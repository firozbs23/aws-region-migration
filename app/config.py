"""
Centralised application configuration.

Every setting is read from environment variables (or a local .env file for
development). This is the ONLY file that needs to change when the stack is
migrated from one AWS region to another.
"""
from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # RDS SQL Server connection. Prefer DB_PASSWORD (no URL-encoding headaches).
    # DATABASE_URL is still accepted as a full override when set.
    db_host: str = "file-backup-db.c9g4u6ekudby.ap-southeast-1.rds.amazonaws.com"
    db_port: int = 1433
    db_user: str = "admin"
    db_password: str = ""
    db_name: str = "filebackup"
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    # ================================================================

    # ---- AWS credentials ----
    # On EC2 in every environment (POC and production) these are left
    # unset and the app relies on the instance's IAM role instead. They
    # only exist here so the app can also run from a laptop for local dev.
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # ---- S3 behaviour ----
    s3_presigned_url_expiry_seconds: int = 3600
    max_upload_size_mb: int = 100

    # ---- DB connection pool ----
    db_pool_size: int = 5
    db_max_overflow: int = 5

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if not self.db_password:
            raise ValueError(
                "DB_PASSWORD is not set. Add it to .env (RDS master password). "
                "Or set DATABASE_URL to a full mssql+pymssql://... connection string."
            )
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"mssql+pymssql://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def bucket_for_category(self, category: str) -> str:
        return {
            "documents": self.s3_bucket_documents,
            "media": self.s3_bucket_media,
            "archives": self.s3_bucket_archives,
        }[category]


@lru_cache
def get_settings() -> Settings:
    return Settings()
