"""Models for segment traversal: directions, boundaries, and planned actions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.enums import TradeSide, ZoneEventType, ZoneState

__all__ = [
    "BoundaryKind",
    "PlannedGridCrossing",
    "SegmentDirection",
    "SegmentTraversalState",
    "TransitionRule",
    "ZoneEvent",
]


class SegmentDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class BoundaryKind(StrEnum):
    A_UPPER = "A_UPPER"
    A_LOWER = "A_LOWER"
    C_UPPER = "C_UPPER"
    C_LOWER = "C_LOWER"


@dataclass(slots=True)
class SegmentTraversalState:
    """Deliberately mutable: market_cursor and zone_state evolve during traversal.

    trade_anchor is carried here but must never change during Task 8 planning;
    it only ever changes after a successful execution in a later layer.
    """

    market_cursor: Decimal
    trade_anchor: Decimal
    zone_state: ZoneState


@dataclass(frozen=True, slots=True)
class PlannedGridCrossing:
    grid_level: Decimal
    side: TradeSide
    event_date: date


@dataclass(frozen=True, slots=True)
class ZoneEvent:
    event_type: ZoneEventType
    boundary_price: Decimal
    event_date: date
    old_zone: ZoneState
    new_zone: ZoneState


@dataclass(frozen=True, slots=True)
class TransitionRule:
    old_zone: ZoneState
    new_zone: ZoneState
    event_type: ZoneEventType
