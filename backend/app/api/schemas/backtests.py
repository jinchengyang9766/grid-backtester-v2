"""Backtest request/response schemas (SPEC Sections 25.3, 29, 30).

All monetary/rate values are Decimal end to end — never parsed through
float; every Decimal output serializes as a plain fixed-point string.
Every request model rejects unknown fields.
"""

import datetime as dt
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.db.models import BacktestRun, DailyEquity, EventEquity, Trade, ZoneEventRecord

__all__ = [
    "BacktestConfigurationInput",
    "BacktestCreateRequest",
    "BacktestCreateResponse",
    "BacktestDetailResponse",
    "BacktestListItem",
    "BacktestListResponse",
    "CommissionInput",
    "DailyEquityProjectionModel",
    "DatasetSummaryInBacktest",
    "EventEquityProjectionModel",
    "SlippageInput",
    "SlippageSideInput",
    "TickSizeInput",
    "TradeProjectionModel",
    "ValueInput",
    "ZoneEventProjectionModel",
]


def plain_decimal(value: Decimal) -> str:
    """Plain fixed-point rendering, never scientific notation, never float.

    Kept local (identical to app.backtests.serialization.plain_decimal)
    because the schemas layer must not import the services package.
    """
    return format(value, "f")


def _decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else plain_decimal(value)


ValueModeLiteral = Literal["PERCENT", "FIXED"]


class ValueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ValueModeLiteral
    value: Decimal


class TickSizeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    value: Decimal | None = None


class CommissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rate_enabled: bool
    rate: Decimal
    minimum_enabled: bool
    minimum: Decimal
    fixed_enabled: bool
    fixed: Decimal


class SlippageSideInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ValueModeLiteral
    value: Decimal


class SlippageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared: bool
    mode: ValueModeLiteral | None = None
    value: Decimal | None = None
    buy: SlippageSideInput | None = None
    sell: SlippageSideInput | None = None

    @model_validator(mode="after")
    def _canonical_shape(self) -> Self:
        # Exactly one representation: shared mode/value XOR separate buy/sell.
        if self.shared:
            if self.mode is None or self.value is None:
                raise ValueError("shared slippage requires mode and value")
            if self.buy is not None or self.sell is not None:
                raise ValueError("shared slippage must not include buy/sell overrides")
        else:
            if self.buy is None or self.sell is None:
                raise ValueError("separate slippage requires both buy and sell")
            if self.mode is not None or self.value is not None:
                raise ValueError("separate slippage must not include top-level mode/value")
        return self


class BacktestConfigurationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_cash: Decimal
    initial_shares: int
    lot_size: int
    trade_lots: int
    baseline: Decimal | None = None
    a_distance: ValueInput
    c_distance: ValueInput
    grid_step: ValueInput
    tick_size: TickSizeInput
    ohlc_path_mode: Literal["HIGH_FIRST", "LOW_FIRST", "AUTO"] | None = None
    buy_commission: CommissionInput
    sell_commission: CommissionInput
    slippage: SlippageInput
    risk_free_rate_annual: Decimal


class BacktestCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: int
    name: str | None = None
    configuration: BacktestConfigurationInput

    @field_validator("name")
    @classmethod
    def _trim_and_require_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("name must contain at least one non-whitespace character")
        return trimmed


class BacktestCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    name: str
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None
    result_metrics: dict[str, Any] | None

    @field_validator("created_at", "completed_at")
    @classmethod
    def _ensure_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class DatasetSummaryInBacktest(BaseModel):
    """Dataset metadata inside a backtest detail — never user_id or PriceBars."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: str
    original_filename: str
    security_name: str | None
    security_code: str | None
    data_mode: str
    start_date: dt.date
    end_date: dt.date
    row_count: int


class BacktestListItem(BaseModel):
    id: int
    dataset_id: int
    dataset_name: str
    name: str
    status: str
    start_date: dt.date
    end_date: dt.date
    ohlc_path_mode: str | None
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None
    result_metrics: dict[str, Any] | None

    @field_validator("created_at", "completed_at")
    @classmethod
    def _ensure_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def from_run(cls, run: BacktestRun, dataset_name: str) -> Self:
        return cls(
            id=run.id,
            dataset_id=run.dataset_id,
            dataset_name=dataset_name,
            name=run.name,
            status=run.status,
            start_date=run.start_date,
            end_date=run.end_date,
            ohlc_path_mode=run.ohlc_path_mode,
            created_at=run.created_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
            result_metrics=run.result_metrics,
        )


class BacktestListResponse(BaseModel):
    items: list[BacktestListItem]
    total: int
    limit: int
    offset: int


class TradeProjectionModel(BaseModel):
    id: int
    date: dt.date
    event_sequence: int
    side: str
    grid_price: str
    execution_price: str | None
    shares: int
    notional: str | None
    commission: str | None
    slippage_cost: str | None
    cash_after: str
    shares_after: int
    equity_after: str
    status: str
    skip_reason: str | None

    @classmethod
    def from_row(cls, trade: Trade, event_date: dt.date, event_sequence: int) -> Self:
        return cls(
            id=trade.id,
            date=event_date,
            event_sequence=event_sequence,
            side=trade.side,
            grid_price=plain_decimal(trade.grid_price),
            execution_price=_decimal_string(trade.execution_price),
            shares=trade.shares,
            notional=_decimal_string(trade.notional),
            commission=_decimal_string(trade.commission),
            slippage_cost=_decimal_string(trade.slippage_cost),
            cash_after=plain_decimal(trade.cash_after),
            shares_after=trade.shares_after,
            equity_after=plain_decimal(trade.equity_after),
            status=trade.status,
            skip_reason=trade.skip_reason,
        )


class ZoneEventProjectionModel(BaseModel):
    id: int
    date: dt.date
    event_sequence: int
    event_type: str
    price: str

    @classmethod
    def from_row(
        cls, zone_event: ZoneEventRecord, event_date: dt.date, event_sequence: int
    ) -> Self:
        return cls(
            id=zone_event.id,
            date=event_date,
            event_sequence=event_sequence,
            event_type=zone_event.event_type,
            price=plain_decimal(zone_event.price),
        )


class DailyEquityProjectionModel(BaseModel):
    id: int
    date: dt.date
    close: str
    cash: str
    shares: int
    equity: str
    drawdown: str
    zone_at_close: str

    @classmethod
    def from_row(cls, row: DailyEquity) -> Self:
        return cls(
            id=row.id,
            date=row.date,
            close=plain_decimal(row.close),
            cash=plain_decimal(row.cash),
            shares=row.shares,
            equity=plain_decimal(row.equity),
            drawdown=plain_decimal(row.drawdown),
            zone_at_close=row.zone_at_close,
        )


class EventEquityProjectionModel(BaseModel):
    id: int
    date: dt.date
    event_sequence: int
    market_price: str
    cash: str
    shares: int
    equity: str

    @classmethod
    def from_row(
        cls,
        row: EventEquity,
        event_date: dt.date,
        event_sequence: int,
        market_price: Decimal,
    ) -> Self:
        return cls(
            id=row.id,
            date=event_date,
            event_sequence=event_sequence,
            market_price=plain_decimal(market_price),
            cash=plain_decimal(row.cash),
            shares=row.shares,
            equity=plain_decimal(row.equity),
        )


class BacktestDetailResponse(BaseModel):
    """Base detail; the four series fields appear only when requested
    (routes use response_model_exclude_unset, so unset means absent)."""

    id: int
    dataset_id: int
    dataset: DatasetSummaryInBacktest
    name: str
    status: str
    configuration: dict[str, Any]
    ohlc_path_mode: str | None
    start_date: dt.date
    end_date: dt.date
    result_metrics: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    trades: list[TradeProjectionModel] = []
    zone_events: list[ZoneEventProjectionModel] = []
    daily_equity: list[DailyEquityProjectionModel] = []
    event_equity: list[EventEquityProjectionModel] = []

    @field_validator("created_at", "completed_at")
    @classmethod
    def _ensure_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def base_fields_from_run(cls, run: BacktestRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "dataset_id": run.dataset_id,
            "dataset": DatasetSummaryInBacktest.model_validate(run.dataset),
            "name": run.name,
            "status": run.status,
            "configuration": run.configuration,
            "ohlc_path_mode": run.ohlc_path_mode,
            "start_date": run.start_date,
            "end_date": run.end_date,
            "result_metrics": run.result_metrics,
            "error_message": run.error_message,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
        }
