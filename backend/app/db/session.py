"""Database engine and session infrastructure.

Engine creation is lazy (SQLAlchemy connects on first use, never at import),
Alembic owns schema creation, and request/business layers own transaction
boundaries — get_db_session never commits or rolls back on its own.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

__all__ = [
    "SessionLocal",
    "create_database_engine",
    "create_session_factory",
    "engine",
    "get_db_session",
]


def create_database_engine(database_url: str) -> Engine:
    connect_args: dict[str, bool] = {}
    if database_url.startswith("sqlite"):
        # SQLite connections are thread-bound by default; FastAPI may service
        # a request on a different thread than the one that created the
        # connection. Non-SQLite URLs must not receive this SQLite-only flag.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


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
