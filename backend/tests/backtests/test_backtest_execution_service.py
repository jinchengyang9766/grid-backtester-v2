"""Tests for the synchronous backtest execution service."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import app.backtests.service as service_module
import pytest
import sqlalchemy as sa
from app.api.errors import ApiError
from app.api.schemas.backtests import BacktestCreateRequest
from app.backtests.service import create_backtest
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
from app.db.session import create_database_engine, create_session_factory
from sqlalchemy.orm import Session, sessionmaker

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
START = date(2026, 1, 5)


def base_configuration(**overrides: Any) -> dict[str, Any]:
    configuration: dict[str, Any] = {
        "initial_cash": "1000.00",
        "initial_shares": 0,
        "lot_size": 1,
        "trade_lots": 1,
        "baseline": None,
        "a_distance": {"mode": "FIXED", "value": "2"},
        "c_distance": {"mode": "FIXED", "value": "4"},
        "grid_step": {"mode": "FIXED", "value": "1"},
        "tick_size": {"enabled": False, "value": None},
        "ohlc_path_mode": None,
        "buy_commission": {
            "rate_enabled": False,
            "rate": "0",
            "minimum_enabled": False,
            "minimum": "0",
            "fixed_enabled": False,
            "fixed": "0",
        },
        "sell_commission": {
            "rate_enabled": False,
            "rate": "0",
            "minimum_enabled": False,
            "minimum": "0",
            "fixed_enabled": False,
            "fixed": "0",
        },
        "slippage": {"shared": True, "mode": "FIXED", "value": "0", "buy": None, "sell": None},
        "risk_free_rate_annual": "0.0",
    }
    configuration.update(overrides)
    return configuration


def make_request(
    dataset_id: int, name: str | None = None, **overrides: Any
) -> BacktestCreateRequest:
    return BacktestCreateRequest.model_validate(
        {
            "dataset_id": dataset_id,
            "name": name,
            "configuration": base_configuration(**overrides),
        }
    )


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'bt_service.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def seed_close_only(
    session: Session, closes: list[str], email: str = "svc@example.com"
) -> tuple[int, int]:
    user = User(email=email, password_hash="hash")
    dataset = Dataset(
        user=user,
        name="svc-ds",
        source_type="CSV",
        original_filename="s.csv",
        security_name=None,
        security_code="159999",
        data_mode="CLOSE_ONLY",
        start_date=START,
        end_date=START + timedelta(days=len(closes) - 1),
        row_count=len(closes),
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"bad_rows": 0},
    )
    for offset, close in enumerate(closes):
        PriceBar(dataset=dataset, date=START + timedelta(days=offset), close=Decimal(close))
    session.add(user)
    session.commit()
    return user.id, dataset.id


def seed_ohlcv(session: Session, email: str = "ohlcv@example.com") -> tuple[int, int]:
    user = User(email=email, password_hash="hash")
    dataset = Dataset(
        user=user,
        name="ohlcv-ds",
        source_type="TDX_XLS",
        original_filename="o.xls",
        security_name=None,
        security_code=None,
        data_mode="OHLCV",
        start_date=START,
        end_date=START + timedelta(days=1),
        row_count=2,
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"bad_rows": 0},
    )
    rows = [
        ("10.0", "10.5", "9.5", "10.2"),
        ("10.2", "10.6", "9.8", "10.0"),
    ]
    for offset, (open_, high, low, close) in enumerate(rows):
        PriceBar(
            dataset=dataset,
            date=START + timedelta(days=offset),
            open=Decimal(open_),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
        )
    session.add(user)
    session.commit()
    return user.id, dataset.id


def count(session: Session, model: type) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


class TestOwnership:
    def test_missing_and_wrong_owner_dataset_are_identical_404(self, session: Session) -> None:
        owner_id, dataset_id = seed_close_only(session, ["10", "9", "10"])
        with pytest.raises(ApiError) as missing:
            create_backtest(session, current_user_id=owner_id, request=make_request(99999), now=NOW)
        with pytest.raises(ApiError) as foreign:
            create_backtest(
                session, current_user_id=owner_id + 1, request=make_request(dataset_id), now=NOW
            )
        for excinfo in (missing, foreign):
            assert excinfo.value.status_code == 404
            assert excinfo.value.code == "DATASET_NOT_FOUND"
            assert excinfo.value.message == "Dataset not found."
        assert count(session, BacktestRun) == 0


class TestSuccess:
    def test_close_only_success_with_generated_name(self, session: Session) -> None:
        owner_id, dataset_id = seed_close_only(session, ["10", "9", "10"])
        run = create_backtest(
            session, current_user_id=owner_id, request=make_request(dataset_id), now=NOW
        )
        assert run.status == "COMPLETED"
        assert run.name == "159999 — A Grid 1 — 2026-07-19"
        assert run.ohlc_path_mode is None
        assert run.user_id == owner_id
        assert run.dataset_id == dataset_id
        assert run.start_date == START
        assert run.end_date == START + timedelta(days=2)
        assert run.completed_at is not None
        assert run.error_message is None
        assert run.result_metrics is not None
        assert run.result_metrics["grid_levels"]

    def test_ohlcv_success_with_supplied_name(self, session: Session) -> None:
        owner_id, dataset_id = seed_ohlcv(session)
        run = create_backtest(
            session,
            current_user_id=owner_id,
            request=make_request(dataset_id, name="My OHLCV Run", ohlc_path_mode="AUTO"),
            now=NOW,
        )
        assert run.status == "COMPLETED"
        assert run.name == "My OHLCV Run"
        assert run.ohlc_path_mode == "AUTO"
        assert run.configuration["ohlc_path_mode"] == "AUTO"

    def test_price_bars_load_in_date_order_despite_insertion_order(self, session: Session) -> None:
        user = User(email="order@example.com", password_hash="hash")
        dataset = Dataset(
            user=user,
            name="unordered",
            source_type="CSV",
            original_filename="u.csv",
            security_name=None,
            security_code=None,
            data_mode="CLOSE_ONLY",
            start_date=START,
            end_date=START + timedelta(days=2),
            row_count=3,
            column_mapping={"date": "Date", "close": "Close"},
            cleaning_summary={"bad_rows": 0},
        )
        session.add(user)
        session.flush()
        # Insert rows in reverse chronological order.
        for offset, close in [(2, "10"), (0, "10"), (1, "9")]:
            session.add(
                PriceBar(
                    dataset_id=dataset.id,
                    date=START + timedelta(days=offset),
                    close=Decimal(close),
                )
            )
        session.commit()
        run = create_backtest(
            session, current_user_id=user.id, request=make_request(dataset.id), now=NOW
        )
        assert run.status == "COMPLETED"
        daily = session.execute(sa.select(DailyEquity).order_by(DailyEquity.date)).scalars().all()
        assert [row.date for row in daily] == [START + timedelta(days=i) for i in range(3)]


class TestDatasetDataValidation:
    def test_zero_price_bars_rejected_without_run(self, session: Session) -> None:
        user = User(email="empty@example.com", password_hash="hash")
        dataset = Dataset(
            user=user,
            name="empty",
            source_type="CSV",
            original_filename="e.csv",
            security_name=None,
            security_code=None,
            data_mode="CLOSE_ONLY",
            start_date=START,
            end_date=START,
            row_count=0,
            column_mapping={"date": "Date", "close": "Close"},
            cleaning_summary={"bad_rows": 0},
        )
        session.add(user)
        session.commit()
        with pytest.raises(ApiError) as excinfo:
            create_backtest(
                session, current_user_id=user.id, request=make_request(dataset.id), now=NOW
            )
        assert excinfo.value.status_code == 422
        assert excinfo.value.code == "VALIDATION_ERROR"
        assert count(session, BacktestRun) == 0

    def test_malformed_ohlcv_row_rejected_without_run(self, session: Session) -> None:
        owner_id, dataset_id = seed_ohlcv(session)
        session.execute(
            sa.update(PriceBar).where(PriceBar.dataset_id == dataset_id).values(open=None)
        )
        session.commit()
        with pytest.raises(ApiError) as excinfo:
            create_backtest(
                session,
                current_user_id=owner_id,
                request=make_request(dataset_id, ohlc_path_mode="AUTO"),
                now=NOW,
            )
        assert excinfo.value.status_code == 422
        assert excinfo.value.code == "VALIDATION_ERROR"
        assert count(session, BacktestRun) == 0


class TestEngineValidationMapping:
    @pytest.mark.parametrize(
        ("overrides", "expected_code"),
        [
            ({"c_distance": {"mode": "FIXED", "value": "2"}}, "INVALID_ZONE_CONFIG"),
            ({"grid_step": {"mode": "FIXED", "value": "0"}}, "NON_POSITIVE_GRID_STEP"),
            ({"a_distance": {"mode": "FIXED", "value": "-1"}}, "NON_POSITIVE_DISTANCE"),
            ({"baseline": "-5"}, "NON_POSITIVE_BASELINE"),
            ({"lot_size": 0}, "INVALID_LOT_SIZE"),
            ({"trade_lots": 0}, "INVALID_TRADE_LOTS"),
            ({"initial_cash": "-1"}, "NEGATIVE_INITIAL_CASH"),
            ({"initial_shares": -1}, "NEGATIVE_INITIAL_SHARES"),
            ({"initial_cash": "0", "initial_shares": 0}, "ZERO_INITIAL_EQUITY"),
            (
                {
                    "buy_commission": {
                        "rate_enabled": True,
                        "rate": "-0.1",
                        "minimum_enabled": False,
                        "minimum": "0",
                        "fixed_enabled": False,
                        "fixed": "0",
                    }
                },
                "NEGATIVE_COMMISSION_COMPONENT",
            ),
            (
                {
                    "slippage": {
                        "shared": True,
                        "mode": "FIXED",
                        "value": "-0.1",
                        "buy": None,
                        "sell": None,
                    }
                },
                "NEGATIVE_SLIPPAGE",
            ),
            ({"tick_size": {"enabled": True, "value": "0"}}, "NON_POSITIVE_TICK_SIZE"),
            ({"risk_free_rate_annual": "-2"}, "INVALID_RISK_FREE_RATE"),
            (
                {
                    "a_distance": {"mode": "FIXED", "value": "100"},
                    "c_distance": {"mode": "FIXED", "value": "200"},
                    "grid_step": {"mode": "FIXED", "value": "0.001"},
                },
                "GRID_TOO_DENSE",
            ),
            (
                {
                    "a_distance": {"mode": "FIXED", "value": "0.3"},
                    "c_distance": {"mode": "FIXED", "value": "0.6"},
                    "grid_step": {"mode": "FIXED", "value": "0.1"},
                    "tick_size": {"enabled": True, "value": "1"},
                },
                "GRID_COLLAPSES_AFTER_TICK_ROUNDING",
            ),
        ],
    )
    def test_engine_validation_maps_to_spec_code_and_persists_nothing(
        self, session: Session, overrides: dict[str, Any], expected_code: str
    ) -> None:
        owner_id, dataset_id = seed_close_only(session, ["10", "9", "10"])
        with pytest.raises(ApiError) as excinfo:
            create_backtest(
                session,
                current_user_id=owner_id,
                request=make_request(dataset_id, **overrides),
                now=NOW,
            )
        assert excinfo.value.status_code == 422
        assert excinfo.value.code == expected_code
        assert count(session, BacktestRun) == 0
        assert count(session, BacktestEvent) == 0


class TestRuntimeFailure:
    def test_non_positive_execution_price_persists_failed_run(self, session: Session) -> None:
        owner_id, dataset_id = seed_close_only(session, ["10", "9", "10"])
        # Sell slippage larger than the sell grid price forces a runtime
        # NonPositiveExecutionPriceError once the sell executes.
        run = create_backtest(
            session,
            current_user_id=owner_id,
            request=make_request(
                dataset_id,
                slippage={
                    "shared": False,
                    "mode": None,
                    "value": None,
                    "buy": {"mode": "FIXED", "value": "0"},
                    "sell": {"mode": "FIXED", "value": "20"},
                },
            ),
            now=NOW,
        )
        assert run.status == "FAILED"
        assert run.result_metrics is None
        assert run.error_message is not None
        assert "not positive" in run.error_message
        assert "Traceback" not in run.error_message
        assert run.completed_at is not None
        assert count(session, BacktestRun) == 1
        for model in (BacktestEvent, Trade, ZoneEventRecord, EventEquity, DailyEquity):
            assert count(session, model) == 0


class TestUnexpectedFailure:
    def test_unexpected_persistence_error_rolls_back(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        owner_id, dataset_id = seed_close_only(session, ["10", "9", "10"])

        def broken_persist(*args: object, **kwargs: object) -> None:
            raise RuntimeError("unexpected persistence bug")

        monkeypatch.setattr(service_module, "persist_completed_run", broken_persist)
        with pytest.raises(RuntimeError):
            create_backtest(
                session, current_user_id=owner_id, request=make_request(dataset_id), now=NOW
            )
        assert count(session, BacktestRun) == 0
        # Session remains usable after the rollback.
        assert count(session, Dataset) == 1
