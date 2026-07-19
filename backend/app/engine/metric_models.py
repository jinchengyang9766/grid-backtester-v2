"""Immutable metric result models and their pure-domain exceptions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import ZoneEventType

__all__ = [
    "BacktestMetrics",
    "EmptyEquitySeriesError",
    "EquitySeriesMetrics",
    "FirstReturnMetrics",
    "InvalidRiskFreeRateError",
    "TradeCostMetrics",
    "TradeDateNotFoundError",
    "ZoneMetrics",
]


@dataclass(frozen=True, slots=True)
class EquitySeriesMetrics:
    initial_equity: Decimal
    final_equity: Decimal
    net_profit: Decimal
    total_return: Decimal
    annualized_return: Decimal | None
    maximum_drawdown: Decimal
    sharpe_ratio: Decimal | None


@dataclass(frozen=True, slots=True)
class TradeCostMetrics:
    total_commission: Decimal
    total_slippage_cost: Decimal
    executed_trades: int
    skipped_trades: int
    buy_count: int
    sell_count: int


@dataclass(frozen=True, slots=True)
class ZoneMetrics:
    days_closed_in_a_zone: int
    days_closed_in_c_zone: int
    days_closed_outside_c: int
    zone_event_counts: dict[ZoneEventType, int]


@dataclass(frozen=True, slots=True)
class FirstReturnMetrics:
    """equity and days are either both populated or both None."""

    equity: Decimal | None
    days: int | None


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    strategy: EquitySeriesMetrics
    trade_costs: TradeCostMetrics
    zones: ZoneMetrics
    first_return: FirstReturnMetrics
    benchmark1: EquitySeriesMetrics
    benchmark2: EquitySeriesMetrics
    benchmark2_day_one_commission: Decimal
    benchmark2_day_one_slippage_cost: Decimal


class EmptyEquitySeriesError(Exception):
    def __init__(self) -> None:
        super().__init__("Equity series must contain at least one point.")


class InvalidRiskFreeRateError(Exception):
    def __init__(self, value: Decimal) -> None:
        super().__init__(f"Annual risk-free rate must be > -1; got {value}.")
        self.value = value


class TradeDateNotFoundError(Exception):
    def __init__(self, event_date: date) -> None:
        super().__init__(f"Trade date {event_date} is not among the backtest's Bar dates.")
        self.event_date = event_date
