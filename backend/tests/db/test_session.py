"""Tests for database engine construction and session infrastructure."""

from unittest import mock

import app.db.session as session_module
import pytest
from app.db.session import (
    create_database_engine,
    create_session_factory,
    get_db_session,
)
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def test_sqlite_url_receives_check_same_thread_flag() -> None:
    with mock.patch.object(session_module, "create_engine") as fake_create:
        session_module.create_database_engine("sqlite:///./anything.db")
    fake_create.assert_called_once_with(
        "sqlite:///./anything.db", connect_args={"check_same_thread": False}
    )


def test_non_sqlite_url_gets_no_sqlite_connect_args() -> None:
    url = "postgresql+psycopg://user:secret@localhost:5432/grid"
    with mock.patch.object(session_module, "create_engine") as fake_create:
        session_module.create_database_engine(url)
    fake_create.assert_called_once_with(url, connect_args={})


def test_in_memory_sqlite_engine_executes_select_one() -> None:
    isolated_engine = create_database_engine("sqlite:///:memory:")
    with isolated_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_session_factory_returns_configured_sessions() -> None:
    isolated_engine = create_database_engine("sqlite:///:memory:")
    factory = create_session_factory(isolated_engine)
    assert isinstance(factory, sessionmaker)
    with factory() as session:
        assert isinstance(session, Session)
        assert session.autoflush is False
        assert session.expire_on_commit is False


def test_module_level_engine_and_factory_exist() -> None:
    assert isinstance(session_module.engine, Engine)
    assert isinstance(session_module.SessionLocal, sessionmaker)


def test_get_db_session_yields_then_closes_without_committing() -> None:
    fake_session = mock.MagicMock()
    with mock.patch.object(session_module, "SessionLocal", return_value=fake_session):
        generator = get_db_session()
        assert next(generator) is fake_session
        fake_session.close.assert_not_called()
        with pytest.raises(StopIteration):
            next(generator)
    fake_session.close.assert_called_once()
    fake_session.commit.assert_not_called()
    fake_session.rollback.assert_not_called()


def test_get_db_session_closes_even_on_error() -> None:
    fake_session = mock.MagicMock()
    with mock.patch.object(session_module, "SessionLocal", return_value=fake_session):
        generator = get_db_session()
        next(generator)
        with pytest.raises(RuntimeError):
            generator.throw(RuntimeError("request failed"))
    fake_session.close.assert_called_once()
    fake_session.rollback.assert_not_called()  # business layers own transactions
