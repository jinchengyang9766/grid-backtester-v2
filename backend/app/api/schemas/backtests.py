"""Backtest create request/response schemas (SPEC Section 25.3).

All monetary/rate values are Decimal end to end — never parsed through
float. Every request model rejects unknown fields.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "BacktestConfigurationInput",
    "BacktestCreateRequest",
    "BacktestCreateResponse",
    "CommissionInput",
    "SlippageInput",
    "SlippageSideInput",
    "TickSizeInput",
    "ValueInput",
]

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
