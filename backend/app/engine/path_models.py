"""Immutable value objects for price-path segmentation and initial engine state."""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import ZoneState
from app.domain.models import PathPoint

__all__ = [
    "InitialPathState",
    "PathSegment",
]


@dataclass(frozen=True, slots=True)
class PathSegment:
    """One adjacent point pair; every future event it produces is dated end.date."""

    start: PathPoint
    end: PathPoint


@dataclass(frozen=True, slots=True)
class InitialPathState:
    """Initialization snapshot only; later state transitions live elsewhere."""

    market_cursor: Decimal
    trade_anchor: Decimal
    zone_state: ZoneState
