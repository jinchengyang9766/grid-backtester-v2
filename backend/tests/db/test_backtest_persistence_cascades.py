"""Cascade/RESTRICT deletion tests across the backtest persistence graph."""

import datetime
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from app.db import Base
from app.db.models import (
    BacktestEvent,
    BacktestRun,
    DailyEquity,
    Dataset,
    EventEquity,
    PriceBar,
    Trade,
    User,
    ZoneEventRecord,
)
from app.db.session import create_database_engine, create_session_factory, get_db_session
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

RESULT_MODELS = (BacktestRun, BacktestEvent, Trade, ZoneEventRecord, DailyEquity, EventEquity)


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'bt_cascades.db'}")
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


def count(session: Session, model: type) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


def build_full_graph(session: Session, email: str = "runner@example.com") -> dict[str, int]:
    """One User -> Dataset (2 bars) -> COMPLETED run with the full result graph."""
    user = User(email=email, password_hash="hash")
    dataset = Dataset(
        user=user,
        name="ds",
        source_type="CSV",
        original_filename="ds.csv",
        security_name=None,
        security_code=None,
        data_mode="CLOSE_ONLY",
        start_date=datetime.date(2026, 1, 5),
        end_date=datetime.date(2026, 1, 6),
        row_count=2,
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"bad_rows": 0},
    )
    for offset in range(2):
        PriceBar(
            dataset=dataset,
            date=datetime.date(2026, 1, 5) + datetime.timedelta(days=offset),
            close=Decimal("1.05000000"),
        )
    run = BacktestRun(
        user=user,
        dataset=dataset,
        name="run",
        status="COMPLETED",
        configuration={"a": 1},
        start_date=datetime.date(2026, 1, 5),
        end_date=datetime.date(2026, 1, 6),
        result_metrics={"net_profit": "1"},
    )
    trade_event = BacktestEvent(
        backtest_run=run,
        event_sequence=1,
        event_type="TRADE",
        date=datetime.date(2026, 1, 5),
        market_price=Decimal("1.05000000"),
    )
    zone_event_parent = BacktestEvent(
        backtest_run=run,
        event_sequence=2,
        event_type="ZONE_EVENT",
        date=datetime.date(2026, 1, 6),
        market_price=Decimal("1.10000000"),
    )
    Trade(
        event=trade_event,
        side="BUY",
        grid_price=Decimal("1.05000000"),
        execution_price=Decimal("1.05100000"),
        shares=100,
        notional=Decimal("105.10000000"),
        commission=Decimal("5.00000000"),
        slippage_cost=Decimal("0.10000000"),
        cash_after=Decimal("894.90000000"),
        shares_after=100,
        equity_after=Decimal("999.90000000"),
        status="EXECUTED",
        skip_reason=None,
    )
    ZoneEventRecord(event=zone_event_parent, event_type="ENTER_C_ZONE", price=Decimal("1.10"))
    EventEquity(event=trade_event, cash=Decimal("894.90"), shares=100, equity=Decimal("999.90"))
    EventEquity(
        event=zone_event_parent, cash=Decimal("894.90"), shares=100, equity=Decimal("1004.90")
    )
    for offset in range(2):
        DailyEquity(
            backtest_run=run,
            date=datetime.date(2026, 1, 5) + datetime.timedelta(days=offset),
            close=Decimal("1.05000000"),
            cash=Decimal("894.90000000"),
            shares=100,
            equity=Decimal("999.90000000"),
            drawdown=Decimal("0.00000000"),
            zone_at_close="IN_A",
        )
    session.add(user)
    session.commit()
    return {"user_id": user.id, "dataset_id": dataset.id, "run_id": run.id}


def assert_graph_counts(
    session: Session,
    *,
    runs: int,
    events: int,
    trades: int,
    zones: int,
    event_equity: int,
    daily: int,
) -> None:
    assert count(session, BacktestRun) == runs
    assert count(session, BacktestEvent) == events
    assert count(session, Trade) == trades
    assert count(session, ZoneEventRecord) == zones
    assert count(session, EventEquity) == event_equity
    assert count(session, DailyEquity) == daily


class TestUserCascade:
    def test_deleting_user_cascades_through_entire_graph(self, session: Session) -> None:
        build_full_graph(session)
        session.execute(sa.text("DELETE FROM users"))
        session.commit()
        assert_graph_counts(session, runs=0, events=0, trades=0, zones=0, event_equity=0, daily=0)
        assert count(session, Dataset) == 0
        assert count(session, PriceBar) == 0


class TestRunCascade:
    def test_deleting_run_cascades_to_all_result_tables_only(self, session: Session) -> None:
        ids = build_full_graph(session)
        run = session.get(BacktestRun, ids["run_id"])
        assert run is not None
        session.delete(run)
        session.commit()
        assert_graph_counts(session, runs=0, events=0, trades=0, zones=0, event_equity=0, daily=0)
        # Dataset, its bars, and the user all survive.
        assert count(session, Dataset) == 1
        assert count(session, PriceBar) == 2
        assert count(session, User) == 1


class TestDatasetRestrict:
    def test_dataset_delete_blocked_while_run_exists(self, session: Session) -> None:
        ids = build_full_graph(session)
        with pytest.raises(IntegrityError):
            session.execute(
                sa.text("DELETE FROM datasets WHERE id = :id"), {"id": ids["dataset_id"]}
            )
        session.rollback()
        # Everything is preserved and the session remains usable.
        assert count(session, Dataset) == 1
        assert count(session, PriceBar) == 2
        assert_graph_counts(session, runs=1, events=2, trades=1, zones=1, event_equity=2, daily=2)

    def test_dataset_deletable_after_run_removed_and_unrelated_dataset_ok(
        self, session: Session
    ) -> None:
        ids = build_full_graph(session)
        unrelated = Dataset(
            user_id=ids["user_id"],
            name="unrelated",
            source_type="CSV",
            original_filename="u.csv",
            security_name=None,
            security_code=None,
            data_mode="CLOSE_ONLY",
            start_date=datetime.date(2026, 2, 1),
            end_date=datetime.date(2026, 2, 1),
            row_count=1,
            column_mapping={"date": "Date", "close": "Close"},
            cleaning_summary={"bad_rows": 0},
        )
        session.add(unrelated)
        session.commit()

        # Unrelated dataset deletes fine even while the run exists.
        session.delete(unrelated)
        session.commit()
        assert count(session, Dataset) == 1

        run = session.get(BacktestRun, ids["run_id"])
        assert run is not None
        session.delete(run)
        session.commit()
        referenced = session.get(Dataset, ids["dataset_id"])
        assert referenced is not None
        session.delete(referenced)
        session.commit()
        assert count(session, Dataset) == 0
        assert count(session, User) == 1


class TestDatasetApiRegression:
    def test_task17_delete_returns_409_for_real_backtest_run_reference(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Task 17's DELETE endpoint now hits the real production RESTRICT FK."""
        from app.main import create_app

        application = create_app()

        def override() -> Iterator[Session]:
            db_session = session_factory()
            try:
                yield db_session
            finally:
                db_session.close()

        application.dependency_overrides[get_db_session] = override
        with TestClient(application) as client:
            client.post(
                "/api/auth/register",
                json={"email": "runner@example.com", "password": "password123"},
            )
            client.post(
                "/api/auth/login",
                json={"email": "runner@example.com", "password": "password123"},
            )
            with session_factory() as seed_session:
                user = seed_session.execute(sa.select(User)).scalar_one()
                dataset = Dataset(
                    user_id=user.id,
                    name="referenced",
                    source_type="CSV",
                    original_filename="r.csv",
                    security_name=None,
                    security_code=None,
                    data_mode="CLOSE_ONLY",
                    start_date=datetime.date(2026, 1, 5),
                    end_date=datetime.date(2026, 1, 5),
                    row_count=1,
                    column_mapping={"date": "Date", "close": "Close"},
                    cleaning_summary={"bad_rows": 0},
                )
                seed_session.add(dataset)
                seed_session.flush()
                seed_session.add(
                    PriceBar(
                        dataset_id=dataset.id,
                        date=datetime.date(2026, 1, 5),
                        close=Decimal("1.05"),
                    )
                )
                seed_session.add(
                    BacktestRun(
                        user_id=user.id,
                        dataset_id=dataset.id,
                        name="blocking run",
                        status="COMPLETED",
                        configuration={},
                        start_date=datetime.date(2026, 1, 5),
                        end_date=datetime.date(2026, 1, 5),
                    )
                )
                seed_session.commit()
                dataset_id = dataset.id

            response = client.delete(f"/api/datasets/{dataset_id}")
            assert response.status_code == 409
            assert response.json() == {
                "error": {
                    "code": "DATASET_IN_USE",
                    "message": (
                        "Dataset is referenced by existing resources and cannot be deleted."
                    ),
                }
            }
            assert "FOREIGN KEY" not in response.text

        with session_factory() as check_session:
            assert count(check_session, Dataset) == 1
            assert count(check_session, PriceBar) == 1
            assert count(check_session, BacktestRun) == 1
