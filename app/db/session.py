from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()


def _sqlite_database_url() -> str:
    """
    Return an absolute SQLite URL when the configured path is relative.

    Alembic runs from the repository root, but resolving here makes the
    database location independent of the process working directory.
    """
    if not settings.database_url.startswith("sqlite:///"):
        return settings.database_url

    configured_path = settings.database_url.removeprefix("sqlite:///")
    path = Path(configured_path)

    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path

    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


database_url = _sqlite_database_url()
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}

engine = create_engine(database_url, connect_args=connect_args)

if database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
