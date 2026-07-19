"""Database engine and session infrastructure.

Engine creation is lazy (SQLAlchemy connects on first use, never at import),
Alembic owns schema creation, and request/business layers own transaction
boundaries — get_db_session never commits or rolls back on its own.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from app.core.config import get_settings

__all__ = [
    "SessionLocal",
    "create_database_engine",
    "create_session_factory",
    "engine",
    "get_db_session",
]


def _enable_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection, connection_record: ConnectionPoolEntry
) -> None:
    # SQLite ships with foreign-key enforcement OFF per connection; without
    # this pragma, ON DELETE CASCADE and FK violations are silently ignored.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_database_engine(database_url: str) -> Engine:
    connect_args: dict[str, bool] = {}
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        # SQLite connections are thread-bound by default; FastAPI may service
        # a request on a different thread than the one that created the
        # connection. Non-SQLite URLs must not receive this SQLite-only flag.
        connect_args["check_same_thread"] = False
    database_engine = create_engine(database_url, connect_args=connect_args)
    if is_sqlite:
        # Registration only; no connection is opened until first use.
        event.listen(database_engine, "connect", _enable_sqlite_foreign_keys)
    return database_engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine: Engine = create_database_engine(get_settings().database_url)
SessionLocal: sessionmaker[Session] = create_session_factory(engine)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
