"""Tests for the read-only backtest comparison service."""

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from app.api.errors import ApiError
from app.backtests.comparison import compare_owned_backtests
from app.db import Base
from app.db.models import BacktestRun, Dataset, PriceBar, User
from app.db.session import create_database_engine, create_session_factory
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

START = date(2026, 1, 5)


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'compare.db'}")
    Base.metadata.create_all(database_engine)
    yield database_engine
    database_engine.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def make_user(session: Session, email: str) -> int:
    user = User(email=email, password_hash="hash")
    session.add(user)
    session.commit()
    return user.id


def make_dataset(session: Session, user_id: int) -> int:
    dataset = Dataset(
        user_id=user_id,
        name="cmp-ds",
        source_type="CSV",
        original_filename="c.csv",
        security_name=None,
        security_code=None,
        data_mode="CLOSE_ONLY",
        start_date=START,
        end_date=START + timedelta(days=2),
        row_count=3,
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"bad_rows": 0},
    )
    session.add(dataset)
    session.flush()
    for offset, close in enumerate(["10", "9", "10"]):
        session.add(
            PriceBar(
                dataset_id=dataset.id, date=START + timedelta(days=offset), close=Decimal(close)
            )
        )
    session.commit()
    return dataset.id


def make_run(
    session: Session,
    user_id: int,
    dataset_id: int,
    name: str,
    *,
    status: str = "COMPLETED",
    result_metrics: dict[str, Any] | None = None,
) -> int:
    run = BacktestRun(
        user_id=user_id,
        dataset_id=dataset_id,
        name=name,
        status=status,
        configuration={"grid_step": {"mode": "FIXED", "value": "1"}},
        ohlc_path_mode=None,
        start_date=START,
        end_date=START + timedelta(days=2),
        result_metrics=result_metrics,
        error_message=None if status == "COMPLETED" else "boom",
    )
    session.add(run)
    session.commit()
    return run.id


class QueryCounter:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.selects = 0

    def __enter__(self) -> "QueryCounter":
        sa_event.listen(self.engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *args: object) -> None:
        sa_event.remove(self.engine, "before_cursor_execute", self._record)

    def _record(self, conn: object, cursor: object, statement: str, *args: object) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.selects += 1


class TestCompare:
    def test_two_runs_preserve_request_order(self, session: Session) -> None:
        user_id = make_user(session, "a@example.com")
        dataset_id = make_dataset(session, user_id)
        first = make_run(session, user_id, dataset_id, "first", result_metrics={"x": "1"})
        second = make_run(session, user_id, dataset_id, "second", result_metrics={"x": "2"})
        # Request order [second, first] is preserved, not sorted by id.
        runs = compare_owned_backtests(
            session, current_user_id=user_id, backtest_ids=[second, first]
        )
        assert [run.id for run in runs] == [second, first]
        assert [run.result_metrics for run in runs] == [{"x": "2"}, {"x": "1"}]

    def test_three_or_more_runs(self, session: Session) -> None:
        user_id = make_user(session, "a@example.com")
        dataset_id = make_dataset(session, user_id)
        ids = [make_run(session, user_id, dataset_id, f"r{i}") for i in range(4)]
        requested = [ids[2], ids[0], ids[3], ids[1]]
        runs = compare_owned_backtests(session, current_user_id=user_id, backtest_ids=requested)
        assert [run.id for run in runs] == requested

    def test_single_query_used(self, engine: Engine, session: Session) -> None:
        user_id = make_user(session, "a@example.com")
        dataset_id = make_dataset(session, user_id)
        ids = [make_run(session, user_id, dataset_id, f"r{i}") for i in range(3)]
        session.expire_all()
        with QueryCounter(engine) as counter:
            compare_owned_backtests(session, current_user_id=user_id, backtest_ids=ids)
        assert counter.selects == 1

    def test_failed_and_null_metrics_included(self, session: Session) -> None:
        user_id = make_user(session, "a@example.com")
        dataset_id = make_dataset(session, user_id)
        completed = make_run(session, user_id, dataset_id, "ok", result_metrics={"x": "1"})
        failed = make_run(session, user_id, dataset_id, "bad", status="FAILED")
        runs = compare_owned_backtests(
            session, current_user_id=user_id, backtest_ids=[completed, failed]
        )
        assert runs[1].status == "FAILED"
        assert runs[1].result_metrics is None

    def test_missing_id_all_or_nothing(self, session: Session) -> None:
        user_id = make_user(session, "a@example.com")
        dataset_id = make_dataset(session, user_id)
        real = make_run(session, user_id, dataset_id, "real")
        with pytest.raises(ApiError) as excinfo:
            compare_owned_backtests(session, current_user_id=user_id, backtest_ids=[real, 999999])
        assert excinfo.value.status_code == 404
        assert excinfo.value.code == "BACKTEST_NOT_FOUND"
        assert "999999" not in str(excinfo.value.details)

    def test_wrong_owner_id_all_or_nothing_identical(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        alice_ds = make_dataset(session, alice)
        bob_ds = make_dataset(session, bob)
        alice_run = make_run(session, alice, alice_ds, "alice-run")
        alice_run_2 = make_run(session, alice, alice_ds, "alice-run-2")
        bob_run = make_run(session, bob, bob_ds, "bob-run")

        with pytest.raises(ApiError) as foreign:
            compare_owned_backtests(
                session, current_user_id=alice, backtest_ids=[alice_run, bob_run]
            )
        with pytest.raises(ApiError) as missing:
            compare_owned_backtests(
                session, current_user_id=alice, backtest_ids=[alice_run, 888888]
            )
        assert foreign.value.status_code == missing.value.status_code == 404
        assert foreign.value.code == missing.value.code == "BACKTEST_NOT_FOUND"
        assert foreign.value.message == missing.value.message
        # A valid all-owned comparison still works.
        runs = compare_owned_backtests(
            session, current_user_id=alice, backtest_ids=[alice_run, alice_run_2]
        )
        assert [run.id for run in runs] == [alice_run, alice_run_2]

    def test_does_not_commit(self, session: Session) -> None:
        user_id = make_user(session, "a@example.com")
        dataset_id = make_dataset(session, user_id)
        ids = [make_run(session, user_id, dataset_id, f"r{i}") for i in range(2)]

        def fail() -> None:
            raise AssertionError("compare must not commit")

        session.commit = fail  # type: ignore[method-assign]
        runs = compare_owned_backtests(session, current_user_id=user_id, backtest_ids=ids)
        assert len(runs) == 2

    def test_deterministic(self, session: Session) -> None:
        user_id = make_user(session, "a@example.com")
        dataset_id = make_dataset(session, user_id)
        ids = [
            make_run(session, user_id, dataset_id, f"r{i}", result_metrics={"x": str(i)})
            for i in range(3)
        ]
        first = compare_owned_backtests(session, current_user_id=user_id, backtest_ids=ids)
        second = compare_owned_backtests(session, current_user_id=user_id, backtest_ids=ids)
        assert [r.id for r in first] == [r.id for r in second]

    def test_comparison_module_does_not_import_engine(self) -> None:
        source = (
            Path(__file__).resolve().parents[2] / "app" / "backtests" / "comparison.py"
        ).read_text(encoding="utf-8")
        assert "app.engine" not in source
        assert "run_backtest" not in source
