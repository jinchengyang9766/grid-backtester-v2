"""Immutable domain dataclasses shared by the pure backtest engine."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

__all__ = ["Bar", "PathPoint"]


@dataclass(frozen=True, slots=True)
class Bar:
    date: date
    close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PathPoint:
    price: Decimal
    date: date
    is_bar_final: bool
