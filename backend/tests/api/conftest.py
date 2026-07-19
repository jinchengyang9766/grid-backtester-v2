"""Shared API test fixtures: an isolated app over a temporary SQLite database.

Never touches the developer's default grid_backtester_dev.db and never
requires PostgreSQL.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.db import Base
from app.db.session import (
    create_database_engine,
    create_session_factory,
    get_db_session,
)
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'api_test.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(db_engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(db_engine)


def _build_app(session_factory: sessionmaker[Session]) -> FastAPI:
    application = create_app()

    def override_get_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db_session] = override_get_db_session
    return application


@pytest.fixture()
def api_app(session_factory: sessionmaker[Session]) -> FastAPI:
    return _build_app(session_factory)


@pytest.fixture()
def client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as test_client:
        yield test_client


@pytest.fixture()
def production_client(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("GRID_BACKTESTER_APP_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        with TestClient(_build_app(session_factory)) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()
