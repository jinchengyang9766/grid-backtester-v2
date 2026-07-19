"""Tests for transactional persistence of engine BacktestResults."""

import dataclasses
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from app.backtests.persistence import (
    ResultIntegrityError,
    persist_completed_run,
    persist_failed_run,
)
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
from app.domain.enums import DataMode, ValueMode
from app.domain.models import Bar
from app.engine import (
    BacktestConfig,
    BacktestResult,
    CommissionConfig,
    ExecutionConfig,
    SlippageConfig,
    TickSizeConfig,
    TradeResult,
    ValueConfig,
    run_backtest,
)
from sqlalchemy.orm import Session, sessionmaker

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
BAR_CLOSES = ["10", "7", "10"]
START = date(2026, 1, 5)


def make_bars() -> list[Bar]:
    return [
        Bar(date=START + timedelta(days=offset), close=Decimal(close))
        for offset, close in enumerate(BAR_CLOSES)
    ]


def mixed_config() -> BacktestConfig:
    zero = CommissionConfig(
        rate_enabled=False,
        rate=Decimal("0"),
        minimum_enabled=False,
        minimum=Decimal("0"),
        fixed_enabled=False,
        fixed=Decimal("0"),
    )
    no_slip = SlippageConfig(mode=ValueMode.FIXED, value=Decimal("0"))
    return BacktestConfig(
        data_mode=DataMode.CLOSE_ONLY,
        ohlc_path_mode=None,
        baseline_override=None,
        a_distance=ValueConfig(mode=ValueMode.FIXED, value=Decimal("2")),
        c_distance=ValueConfig(mode=ValueMode.FIXED, value=Decimal("4")),
        grid_step=ValueConfig(mode=ValueMode.FIXED, value=Decimal("1")),
        execution=ExecutionConfig(
            lot_size=1,
            trade_lots=1,
            buy_slippage=no_slip,
            sell_slippage=no_slip,
            buy_commission=zero,
            sell_commission=zero,
            tick_size=TickSizeConfig(enabled=False),
        ),
        # cash 9: BUY@9 executes, BUY@8 is skipped -> executed + skipped + zones
        initial_cash=Decimal("9"),
        initial_shares=0,
        annual_risk_free_rate=Decimal("0"),
    )


CONFIG_JSON: dict[str, Any] = {"canonical": True, "grid_step": {"mode": "FIXED", "value": "1"}}


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'bt_persist.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def seed_dataset(session: Session) -> Dataset:
    user = User(email="runner@example.com", password_hash="hash")
    dataset = Dataset(
        user=user,
        name="persist-ds",
        source_type="CSV",
        original_filename="p.csv",
        security_name=None,
        security_code="159999",
        data_mode="CLOSE_ONLY",
        start_date=START,
        end_date=START + timedelta(days=len(BAR_CLOSES) - 1),
        row_count=len(BAR_CLOSES),
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"bad_rows": 0},
    )
    for bar in make_bars():
        PriceBar(dataset=dataset, date=bar.date, close=bar.close)
    session.add(user)
    session.commit()
    return dataset


def run_engine() -> BacktestResult:
    return run_backtest(make_bars(), mixed_config())


def persist(session: Session, dataset: Dataset, result: BacktestResult) -> BacktestRun:
    return persist_completed_run(
        session,
        user_id=dataset.user_id,
        dataset=dataset,
        name="persisted run",
        configuration_json=dict(CONFIG_JSON),
        ohlc_path_mode=None,
        result=result,
        completed_at=NOW,
    )


def count(session: Session, model: type) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


class TestCompletedPersistence:
    def test_full_result_graph_round_trips(
        self, session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        dataset = seed_dataset(session)
        result = run_engine()
        run = persist(session, dataset, result)
        session.commit()
        run_id = run.id

        trade_actions = [a for a in result.actions if isinstance(a.action, TradeResult)]
        zone_actions = [a for a in result.actions if not isinstance(a.action, TradeResult)]
        assert len(trade_actions) == 3 and len(zone_actions) == 2  # rich fixture sanity

        with session_factory() as fresh:
            stored = fresh.execute(sa.select(BacktestRun)).scalar_one()
            assert stored.status == "COMPLETED"
            assert stored.configuration == CONFIG_JSON
            assert stored.ohlc_path_mode is None
            assert stored.completed_at is not None
            metrics = stored.result_metrics
            assert metrics is not None
            assert metrics["grid_levels"] == ["8", "9", "10", "11", "12"]

            events = (
                fresh.execute(sa.select(BacktestEvent).order_by(BacktestEvent.event_sequence))
                .scalars()
                .all()
            )
            assert len(events) == len(result.actions)
            assert [event.event_sequence for event in events] == [
                a.event_sequence for a in result.actions
            ]
            assert [event.event_type for event in events] == [
                "TRADE" if isinstance(a.action, TradeResult) else "ZONE_EVENT"
                for a in result.actions
            ]
            assert count(fresh, Trade) == len(trade_actions)
            assert count(fresh, ZoneEventRecord) == len(zone_actions)
            assert count(fresh, EventEquity) == len(events)
            assert count(fresh, DailyEquity) == len(result.daily_equity)

            # Every event has exactly one child of the right kind + one equity.
            for event in events:
                children = [event.trade, event.zone_event]
                assert sum(child is not None for child in children) == 1
                assert event.event_equity is not None
                if event.event_type == "TRADE":
                    assert event.trade is not None
                    assert event.trade.event_id == event.event_equity.event_id == event.id
                else:
                    assert event.zone_event is not None
                    assert event.zone_event.event_id == event.event_equity.event_id == event.id

            # Skipped trade nullable contract; executed values stay Decimal.
            skipped = fresh.execute(sa.select(Trade).where(Trade.status == "SKIPPED")).scalar_one()
            assert skipped.execution_price is None
            assert skipped.notional is None
            assert skipped.commission is None
            assert skipped.slippage_cost is None
            assert skipped.skip_reason == "INSUFFICIENT_CASH"
            assert isinstance(skipped.cash_after, Decimal)
            assert isinstance(skipped.equity_after, Decimal)
            executed = fresh.execute(
                sa.select(Trade).where(Trade.status == "EXECUTED", Trade.side == "BUY")
            ).scalar_one()
            assert isinstance(executed.execution_price, Decimal)
            assert executed.grid_price == Decimal("9.00000000")

            daily = fresh.execute(sa.select(DailyEquity).order_by(DailyEquity.date)).scalars().all()
            assert [row.date for row in daily] == [p.date for p in result.daily_equity]
            assert daily[0].date == dataset.start_date
            assert daily[-1].date == dataset.end_date
            assert isinstance(daily[0].equity, Decimal)
            final_equity_metric = metrics["metrics"]["strategy"]["final_equity"]
            assert daily[-1].equity == Decimal(final_equity_metric)
            run_row = fresh.get(BacktestRun, run_id)
            assert run_row is not None
            assert run_row.user_id == dataset.user_id
            assert run_row.dataset_id == dataset.id

    def test_helper_does_not_commit(self, session: Session) -> None:
        dataset = seed_dataset(session)
        persist(session, dataset, run_engine())
        # Nothing was committed by the helper; rollback erases everything.
        session.rollback()
        assert count(session, BacktestRun) == 0
        assert count(session, BacktestEvent) == 0
        assert count(session, Trade) == 0
        assert count(session, ZoneEventRecord) == 0
        assert count(session, EventEquity) == 0
        assert count(session, DailyEquity) == 0
        # Dataset, PriceBars, and User survive (they were committed earlier).
        assert count(session, Dataset) == 1
        assert count(session, PriceBar) == 3
        assert count(session, User) == 1

    def test_failure_after_children_rolls_back_everything(self, session: Session) -> None:
        dataset = seed_dataset(session)
        persist(session, dataset, run_engine())  # rows pending, uncommitted
        # A later failure in the same transaction rolls back the entire graph.
        with pytest.raises(RuntimeError):
            raise RuntimeError("simulated post-persistence failure")
        session.rollback()
        for model in (BacktestRun, BacktestEvent, Trade, ZoneEventRecord, EventEquity, DailyEquity):
            assert count(session, model) == 0
        assert count(session, Dataset) == 1
        assert count(session, PriceBar) == 3


class TestFailedRunPersistence:
    def test_failed_run_has_no_children(self, session: Session) -> None:
        dataset = seed_dataset(session)
        run = persist_failed_run(
            session,
            user_id=dataset.user_id,
            dataset=dataset,
            name="failed run",
            configuration_json=dict(CONFIG_JSON),
            ohlc_path_mode=None,
            error_message="Execution price -1 for grid price 10 is not positive",
            completed_at=NOW,
        )
        session.commit()
        assert run.status == "FAILED"
        assert run.result_metrics is None
        assert run.error_message is not None
        assert run.completed_at is not None
        for model in (BacktestEvent, Trade, ZoneEventRecord, EventEquity, DailyEquity):
            assert count(session, model) == 0


class TestResultIntegrityValidation:
    def test_length_mismatch_rejected(self, session: Session) -> None:
        dataset = seed_dataset(session)
        result = run_engine()
        broken = dataclasses.replace(result, event_equity=result.event_equity[:-1])
        with pytest.raises(ResultIntegrityError):
            persist(session, dataset, broken)
        session.rollback()
        assert count(session, BacktestRun) == 0

    def test_sequence_mismatch_rejected(self, session: Session) -> None:
        dataset = seed_dataset(session)
        result = run_engine()
        tampered_point = dataclasses.replace(result.event_equity[0], event_sequence=99)
        broken = dataclasses.replace(
            result, event_equity=(tampered_point, *result.event_equity[1:])
        )
        with pytest.raises(ResultIntegrityError):
            persist(session, dataset, broken)
        session.rollback()
        assert count(session, BacktestRun) == 0

    def test_market_price_mismatch_rejected(self, session: Session) -> None:
        dataset = seed_dataset(session)
        result = run_engine()
        tampered_point = dataclasses.replace(result.event_equity[0], market_price=Decimal("123"))
        broken = dataclasses.replace(
            result, event_equity=(tampered_point, *result.event_equity[1:])
        )
        with pytest.raises(ResultIntegrityError):
            persist(session, dataset, broken)

    def test_daily_range_mismatch_rejected(self, session: Session) -> None:
        dataset = seed_dataset(session)
        result = run_engine()
        broken = dataclasses.replace(result, daily_equity=result.daily_equity[:-1])
        with pytest.raises(ResultIntegrityError):
            persist(session, dataset, broken)
