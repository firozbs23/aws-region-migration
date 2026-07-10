import re
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

_DB_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_engine = None
_session_local = None


def _odbc_connect_string(database: str) -> str:
    if not _DB_NAME_RE.match(database):
        raise ValueError(f"Invalid database name: {database!r}")
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={settings.db_host},{settings.db_port};"
        f"DATABASE={database};"
        f"UID={settings.db_user};"
        f"PWD={settings.db_password};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )


def _make_engine(database: str, *, pool: bool = True):
    kwargs = {"pool_pre_ping": True}
    if pool:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={quote_plus(_odbc_connect_string(database))}",
        **kwargs,
    )


def ensure_database_exists() -> None:
    """RDS SQL Server has no auto-created app DB -- create it on first boot."""
    master = _make_engine("master", pool=False)
    try:
        with master.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(
                text(
                    f"IF DB_ID(N'{settings.db_name}') IS NULL "
                    f"CREATE DATABASE [{settings.db_name}]"
                )
            )
    finally:
        master.dispose()


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine(settings.db_name)
    return _engine


def get_session_local():
    global _session_local
    if _session_local is None:
        _session_local = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_local


Base = declarative_base()


def get_db():
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()
