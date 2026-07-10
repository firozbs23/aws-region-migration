from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.database import Base, ensure_database_exists, get_engine
from app.routers import files as files_router
from app.schemas import RegionInfo

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # POC convenience only: creates tables if they don't exist. In a real
    # environment this is replaced by Alembic migrations run as a
    # deployment step.
    ensure_database_exists()
    Base.metadata.create_all(bind=get_engine())
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "Proof-of-concept file backup service. Uploads are streamed to one of "
        "three S3 buckets by category; metadata, tags, and access logs are "
        "stored in SQL Server (RDS)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(files_router.router)


@app.get("/health", tags=["ops"], summary="Liveness check")
def health():
    return {"status": "ok"}


@app.get(
    "/api/v1/region-info",
    response_model=RegionInfo,
    tags=["ops"],
    summary="Show which AWS region/resources this instance is currently bound to",
)
def region_info():
    return RegionInfo(
        aws_region=settings.aws_region,
        s3_bucket_documents=settings.s3_bucket_documents,
        s3_bucket_media=settings.s3_bucket_media,
        s3_bucket_archives=settings.s3_bucket_archives,
        database_host=settings.db_host,
        app_env=settings.app_env,
    )
