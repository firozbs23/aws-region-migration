import pymssql
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()


def _connect():
    # Explicit pymssql.connect() avoids SQLAlchemy URL parsing issues that
    # can silently fall back to localhost with complex RDS hostnames/passwords.
    return pymssql.connect(
        server=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        tds_version="7.4",
        encryption="require",
    )


engine = create_engine(
    "mssql+pymssql://",
    creator=_connect,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
