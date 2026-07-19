"""Immutable value objects for the two Buy-and-Hold benchmark series."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

__all__ = [
    "BenchmarkDayOnePurchase",
    "BenchmarkEquityPoint",
    "BenchmarkSeries",
]


@dataclass(frozen=True, slots=True)
class BenchmarkEquityPoint:
    date: date
    close: Decimal
    cash: Decimal
    shares: int
    equity: Decimal


@dataclass(frozen=True, slots=True)
class BenchmarkDayOnePurchase:
    """Benchmark 2's single day-one buy; prices stay populated even at zero lots."""

    reference_price: Decimal
    tick_price: Decimal
    execution_price: Decimal
    lots: int
    shares_purchased: int
    notional: Decimal
    commission: Decimal
    slippage_cost: Decimal
    cash_after: Decimal
    shares_after: int


@dataclass(frozen=True, slots=True)
class BenchmarkSeries:
    """Benchmark 1 carries day_one_purchase=None; Benchmark 2 always carries one."""

    points: tuple[BenchmarkEquityPoint, ...]
    day_one_purchase: BenchmarkDayOnePurchase | None
