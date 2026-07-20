"""Tests for the four normalized result-series projections."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.api.schemas.backtests import (
    DailyEquityProjectionModel,
    EventEquityProjectionModel,
    TradeProjectionModel,
    ZoneEventProjectionModel,
)
from app.backtests.persistence import persist_completed_run, persist_failed_run
from app.backtests.projections import (
    load_daily_equity_projection,
    load_event_equity_projection,
    load_trade_projection,
    load_zone_event_projection,
)
from app.db import Base
from app.db.models import BacktestRun, Dataset, PriceBar, User
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
from sqlalchemy.orm import Session

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
START = date(2026, 1, 5)


def mixed_result() -> BacktestResult:
    zero = CommissionConfig(
        rate_enabled=False,
        rate=Decimal("0"),
        minimum_enabled=False,
        minimum=Decimal("0"),
        fixed_enabled=False,
        fixed=Decimal("0"),
    )
    no_slip = SlippageConfig(mode=ValueMode.FIXED, value=Decimal("0"))
    config = BacktestConfig(
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
        initial_cash=Decimal("9"),
        initial_shares=0,
        annual_risk_free_rate=Decimal("0"),
    )
    bars = [
        Bar(date=START + timedelta(days=offset), close=Decimal(close))
        for offset, close in enumerate(["10", "7", "10"])
    ]
    return run_backtest(bars, config)


@pytest.fixture()
def context(tmp_path: Path) -> Iterator[tuple[Session, BacktestRun, BacktestResult, int]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'projections.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        user = User(email="proj@example.com", password_hash="hash")
        dataset = Dataset(
            user=user,
            name="proj-ds",
            source_type="CSV",
            original_filename="p.csv",
            security_name=None,
            security_code=None,
            data_mode="CLOSE_ONLY",
            start_date=START,
            end_date=START + timedelta(days=2),
            row_count=3,
            column_mapping={"date": "Date", "close": "Close"},
            cleaning_summary={"bad_rows": 0},
        )
        for offset, close in enumerate(["10", "7", "10"]):
            PriceBar(dataset=dataset, date=START + timedelta(days=offset), close=Decimal(close))
        session.add(user)
        session.commit()
        result = mixed_result()
        run = persist_completed_run(
            session,
            user_id=user.id,
            dataset=dataset,
            name="projection run",
            configuration_json={"c": True},
            ohlc_path_mode=None,
            result=result,
            completed_at=NOW,
        )
        empty = persist_failed_run(
            session,
            user_id=user.id,
            dataset=dataset,
            name="failed run",
            configuration_json={"c": True},
            ohlc_path_mode=None,
            error_message="boom",
            completed_at=NOW,
        )
        session.commit()
        yield session, run, result, empty.id
    engine.dispose()


class TestTradeProjection:
    def test_ordered_join_matches_engine(
        self, context: tuple[Session, BacktestRun, BacktestResult, int]
    ) -> None:
        session, run, result, _ = context
        rows = load_trade_projection(session, backtest_run_id=run.id)
        engine_trades = [
            (a.event_sequence, a.action)
            for a in result.actions
            if isinstance(a.action, TradeResult)
        ]
        assert len(rows) == len(engine_trades) == 3
        for (trade, event_date, sequence), (engine_sequence, engine_trade) in zip(
            rows, engine_trades, strict=True
        ):
            assert sequence == engine_sequence
            assert event_date == engine_trade.event_date
            assert trade.grid_price == engine_trade.grid_price

    def test_model_fields_and_skipped_nulls(
        self, context: tuple[Session, BacktestRun, BacktestResult, int]
    ) -> None:
        session, run, _, _ = context
        models = [
            TradeProjectionModel.from_row(trade, event_date, sequence)
            for trade, event_date, sequence in load_trade_projection(
                session, backtest_run_id=run.id
            )
        ]
        assert set(TradeProjectionModel.model_fields) == {
            "id",
            "date",
            "event_sequence",
            "side",
            "grid_price",
            "execution_price",
            "shares",
            "notional",
            "commission",
            "slippage_cost",
            "cash_after",
            "shares_after",
            "equity_after",
            "status",
            "skip_reason",
        }
        skipped = next(m for m in models if m.status == "SKIPPED")
        assert skipped.execution_price is None
        assert skipped.notional is None
        assert skipped.commission is None
        assert skipped.slippage_cost is None
        assert skipped.skip_reason == "INSUFFICIENT_CASH"
        assert isinstance(skipped.cash_after, str)
        executed = next(m for m in models if m.status == "EXECUTED")
        assert isinstance(executed.grid_price, str)
        dumped = json.dumps([m.model_dump(mode="json") for m in models])
        assert "event_id" not in dumped
        assert "backtest_run_id" not in dumped


class TestZoneEventProjection:
    def test_ordering_and_fields(
        self, context: tuple[Session, BacktestRun, BacktestResult, int]
    ) -> None:
        session, run, result, _ = context
        rows = load_zone_event_projection(session, backtest_run_id=run.id)
        engine_zones = [
            (a.event_sequence, a.action)
            for a in result.actions
            if not isinstance(a.action, TradeResult)
        ]
        assert len(rows) == len(engine_zones) == 2
        sequences = [sequence for _, _, sequence in rows]
        assert sequences == sorted(sequences)
        models = [
            ZoneEventProjectionModel.from_row(zone, event_date, sequence)
            for zone, event_date, sequence in rows
        ]
        assert set(ZoneEventProjectionModel.model_fields) == {
            "id",
            "date",
            "event_sequence",
            "event_type",
            "price",
        }
        assert models[0].event_type == "ENTER_C_ZONE"
        assert isinstance(models[0].price, str)


class TestDailyEquityProjection:
    def test_date_ordering_and_fields(
        self, context: tuple[Session, BacktestRun, BacktestResult, int]
    ) -> None:
        session, run, result, _ = context
        rows = load_daily_equity_projection(session, backtest_run_id=run.id)
        assert [row.date for row in rows] == [p.date for p in result.daily_equity]
        models = [DailyEquityProjectionModel.from_row(row) for row in rows]
        assert set(DailyEquityProjectionModel.model_fields) == {
            "id",
            "date",
            "close",
            "cash",
            "shares",
            "equity",
            "drawdown",
            "zone_at_close",
        }
        assert all(isinstance(m.equity, str) for m in models)


class TestEventEquityProjection:
    def test_joined_values_come_from_backtest_event(
        self, context: tuple[Session, BacktestRun, BacktestResult, int]
    ) -> None:
        session, run, result, _ = context
        rows = load_event_equity_projection(session, backtest_run_id=run.id)
        assert len(rows) == len(result.event_equity) == 5
        for (row, event_date, sequence, market_price), point in zip(
            rows, result.event_equity, strict=True
        ):
            assert sequence == point.event_sequence
            assert event_date == point.date
            assert market_price == point.market_price
            assert row.cash == point.cash
            assert row.equity == point.equity
        models = [
            EventEquityProjectionModel.from_row(row, event_date, sequence, market_price)
            for row, event_date, sequence, market_price in rows
        ]
        assert set(EventEquityProjectionModel.model_fields) == {
            "id",
            "date",
            "event_sequence",
            "market_price",
            "cash",
            "shares",
            "equity",
        }
        assert all(isinstance(m.market_price, str) for m in models)
        dumped = json.dumps([m.model_dump(mode="json") for m in models])
        assert "event_id" not in dumped


class TestEmptySeries:
    def test_failed_run_returns_empty_arrays(
        self, context: tuple[Session, BacktestRun, BacktestResult, int]
    ) -> None:
        session, _, _, failed_id = context
        assert load_trade_projection(session, backtest_run_id=failed_id) == []
        assert load_zone_event_projection(session, backtest_run_id=failed_id) == []
        assert load_daily_equity_projection(session, backtest_run_id=failed_id) == []
        assert load_event_equity_projection(session, backtest_run_id=failed_id) == []
