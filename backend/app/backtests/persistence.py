"""Persistence of engine BacktestResults into the normalized result tables.

Helpers here build and flush rows but NEVER commit — the service owns the
single transaction commit. No metric is recomputed; every persisted value
comes directly from the engine result.
"""

from datetime import datetime
from typing import assert_never

from sqlalchemy.orm import Session

from app.backtests.serialization import JsonValue, build_result_metrics
from app.db.models import (
    BacktestEvent,
    BacktestRun,
    DailyEquity,
    Dataset,
    EventEquity,
    Trade,
    ZoneEventRecord,
)
from app.engine import BacktestResult, TradeResult, ZoneEvent

__all__ = ["ResultIntegrityError", "persist_completed_run", "persist_failed_run"]


class ResultIntegrityError(Exception):
    """An engine-result invariant did not hold; nothing may be persisted."""


def _validate_event_alignment(result: BacktestResult) -> None:
    if len(result.actions) != len(result.event_equity):
        raise ResultIntegrityError(
            f"actions ({len(result.actions)}) and event_equity "
            f"({len(result.event_equity)}) lengths differ"
        )
    for index, (sequenced, equity_point) in enumerate(
        zip(result.actions, result.event_equity, strict=True)
    ):
        expected_sequence = index + 1  # engine contract: contiguous from 1
        if sequenced.event_sequence != expected_sequence:
            raise ResultIntegrityError(
                f"event_sequence {sequenced.event_sequence} at index {index}; "
                f"expected contiguous value {expected_sequence}"
            )
        if equity_point.event_sequence != sequenced.event_sequence:
            raise ResultIntegrityError(
                f"event_equity sequence {equity_point.event_sequence} does not match "
                f"action sequence {sequenced.event_sequence}"
            )
        action = sequenced.action
        if isinstance(action, TradeResult):
            action_date, market_price = action.event_date, action.grid_price
        elif isinstance(action, ZoneEvent):
            action_date, market_price = action.event_date, action.boundary_price
        else:
            assert_never(action)
        if equity_point.date != action_date:
            raise ResultIntegrityError(
                f"event_equity date {equity_point.date} does not match action date "
                f"{action_date} at sequence {sequenced.event_sequence}"
            )
        if equity_point.market_price != market_price:
            raise ResultIntegrityError(
                f"event_equity market price {equity_point.market_price} does not match "
                f"the action's canonical market price {market_price} "
                f"at sequence {sequenced.event_sequence}"
            )


def _validate_daily_alignment(result: BacktestResult, dataset: Dataset) -> None:
    points = result.daily_equity
    if not points:
        raise ResultIntegrityError("engine produced no daily equity points")
    dates = [point.date for point in points]
    if len(set(dates)) != len(dates):
        raise ResultIntegrityError("duplicate daily-equity dates")
    if dates != sorted(dates):
        raise ResultIntegrityError("daily-equity dates are not ascending")
    if dates[0] != dataset.start_date or dates[-1] != dataset.end_date:
        raise ResultIntegrityError(
            f"daily-equity range {dates[0]}..{dates[-1]} does not match dataset range "
            f"{dataset.start_date}..{dataset.end_date}"
        )


def persist_completed_run(
    session: Session,
    *,
    user_id: int,
    dataset: Dataset,
    name: str,
    configuration_json: dict[str, JsonValue],
    ohlc_path_mode: str | None,
    result: BacktestResult,
    completed_at: datetime,
) -> BacktestRun:
    """Build the COMPLETED run and its full result graph; flush, never commit."""
    _validate_event_alignment(result)
    _validate_daily_alignment(result, dataset)

    run = BacktestRun(
        user_id=user_id,
        dataset_id=dataset.id,
        name=name,
        status="COMPLETED",
        configuration=configuration_json,
        ohlc_path_mode=ohlc_path_mode,
        start_date=dataset.start_date,
        end_date=dataset.end_date,
        result_metrics=build_result_metrics(result),
        error_message=None,
        completed_at=completed_at,
    )
    session.add(run)
    session.flush()

    for sequenced, equity_point in zip(result.actions, result.event_equity, strict=True):
        action = sequenced.action
        if isinstance(action, TradeResult):
            event = BacktestEvent(
                backtest_run_id=run.id,
                event_sequence=sequenced.event_sequence,
                event_type="TRADE",
                date=action.event_date,
                market_price=action.grid_price,
            )
            Trade(
                event=event,
                side=action.side.value,
                grid_price=action.grid_price,
                execution_price=action.execution_price,
                shares=action.shares,
                notional=action.notional,
                commission=action.commission,
                slippage_cost=action.slippage_cost,
                cash_after=action.cash_after,
                shares_after=action.shares_after,
                equity_after=action.equity_after,
                status=action.status.value,
                skip_reason=None if action.skip_reason is None else action.skip_reason.value,
            )
        else:
            event = BacktestEvent(
                backtest_run_id=run.id,
                event_sequence=sequenced.event_sequence,
                event_type="ZONE_EVENT",
                date=action.event_date,
                market_price=action.boundary_price,
            )
            ZoneEventRecord(
                event=event, event_type=action.event_type.value, price=action.boundary_price
            )
        EventEquity(
            event=event,
            cash=equity_point.cash,
            shares=equity_point.shares,
            equity=equity_point.equity,
        )
        session.add(event)

    for point in result.daily_equity:
        session.add(
            DailyEquity(
                backtest_run_id=run.id,
                date=point.date,
                close=point.close,
                cash=point.cash,
                shares=point.shares,
                equity=point.equity,
                drawdown=point.drawdown,
                zone_at_close=point.zone_at_close.value,
            )
        )
    session.flush()
    return run


def persist_failed_run(
    session: Session,
    *,
    user_id: int,
    dataset: Dataset,
    name: str,
    configuration_json: dict[str, JsonValue],
    ohlc_path_mode: str | None,
    error_message: str,
    completed_at: datetime,
) -> BacktestRun:
    """Build only the FAILED run row (no result children); flush, never commit."""
    run = BacktestRun(
        user_id=user_id,
        dataset_id=dataset.id,
        name=name,
        status="FAILED",
        configuration=configuration_json,
        ohlc_path_mode=ohlc_path_mode,
        start_date=dataset.start_date,
        end_date=dataset.end_date,
        result_metrics=None,
        error_message=error_message,
        completed_at=completed_at,
    )
    session.add(run)
    session.flush()
    return run
