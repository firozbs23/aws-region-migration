from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

# RDS SQL Server requires encrypted connections; pymssql defaults to 'request'
# which can fail with misleading "login failed" errors when force_ssl is on.
RDS_CONNECT_ARGS = {
    "tds_version": "7.4",
    "encryption": "require",
}

engine = create_engine(
    settings.resolved_database_url,
    connect_args=RDS_CONNECT_ARGS,
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
