"""Crossing inclusivity, boundary identification, and the frozen transition table.

Implements SPEC Sections 12 (crossing inclusivity), 13.1 (ordering), 14.2
(the eight-row boundary-crossing transition table), and the betweenness
helper used by 14.3. Pure functions only; no state lives here.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.enums import TradeSide, ZoneEventType, ZoneState
from app.engine.grid_models import ZoneBoundaries
from app.engine.segment_models import (
    BoundaryKind,
    PlannedGridCrossing,
    SegmentDirection,
    TransitionRule,
)

__all__ = [
    "boundary_kind",
    "determine_segment_direction",
    "eligible_grid_levels",
    "is_strictly_between",
    "plan_grid_crossings",
    "transition_rule",
]


def determine_segment_direction(start: Decimal, end: Decimal) -> SegmentDirection | None:
    if end > start:
        return SegmentDirection.UP
    if end < start:
        return SegmentDirection.DOWN
    return None


def eligible_grid_levels(
    segment_start: Decimal,
    segment_end: Decimal,
    direction: SegmentDirection,
    grid_levels: Sequence[Decimal],
    trade_anchor: Decimal,
) -> tuple[Decimal, ...]:
    if direction is SegmentDirection.DOWN:
        candidates = [
            level
            for level in grid_levels
            if segment_end <= level < segment_start and level < trade_anchor
        ]
        candidates.sort(reverse=True)  # highest eligible level first
    else:
        candidates = [
            level
            for level in grid_levels
            if segment_start < level <= segment_end and level > trade_anchor
        ]
        candidates.sort()  # lowest eligible level first
    return tuple(candidates)


def plan_grid_crossings(
    segment_start: Decimal,
    segment_end: Decimal,
    direction: SegmentDirection,
    grid_levels: Sequence[Decimal],
    trade_anchor: Decimal,
    event_date: date,
) -> tuple[PlannedGridCrossing, ...]:
    side = TradeSide.BUY if direction is SegmentDirection.DOWN else TradeSide.SELL
    return tuple(
        PlannedGridCrossing(grid_level=level, side=side, event_date=event_date)
        for level in eligible_grid_levels(
            segment_start, segment_end, direction, grid_levels, trade_anchor
        )
    )


def is_strictly_between(start: Decimal, value: Decimal, end: Decimal) -> bool:
    if start < end:
        return start < value < end
    return end < value < start


def boundary_kind(price: Decimal, boundaries: ZoneBoundaries) -> BoundaryKind | None:
    if price == boundaries.a_upper:
        return BoundaryKind.A_UPPER
    if price == boundaries.a_lower:
        return BoundaryKind.A_LOWER
    if price == boundaries.c_upper:
        return BoundaryKind.C_UPPER
    if price == boundaries.c_lower:
        return BoundaryKind.C_LOWER
    return None


_TRANSITION_TABLE: dict[tuple[BoundaryKind, SegmentDirection], TransitionRule] = {
    (BoundaryKind.A_UPPER, SegmentDirection.UP): TransitionRule(
        old_zone=ZoneState.IN_A, new_zone=ZoneState.IN_C, event_type=ZoneEventType.ENTER_C_ZONE
    ),
    (BoundaryKind.A_LOWER, SegmentDirection.DOWN): TransitionRule(
        old_zone=ZoneState.IN_A, new_zone=ZoneState.IN_C, event_type=ZoneEventType.ENTER_C_ZONE
    ),
    (BoundaryKind.C_UPPER, SegmentDirection.UP): TransitionRule(
        old_zone=ZoneState.IN_C,
        new_zone=ZoneState.OUTSIDE_C,
        event_type=ZoneEventType.OUTSIDE_C_BOUNDARY,
    ),
    (BoundaryKind.C_LOWER, SegmentDirection.DOWN): TransitionRule(
        old_zone=ZoneState.IN_C,
        new_zone=ZoneState.OUTSIDE_C,
        event_type=ZoneEventType.OUTSIDE_C_BOUNDARY,
    ),
    (BoundaryKind.A_UPPER, SegmentDirection.DOWN): TransitionRule(
        old_zone=ZoneState.IN_C, new_zone=ZoneState.IN_A, event_type=ZoneEventType.EXIT_C_ZONE
    ),
    (BoundaryKind.A_LOWER, SegmentDirection.UP): TransitionRule(
        old_zone=ZoneState.IN_C, new_zone=ZoneState.IN_A, event_type=ZoneEventType.EXIT_C_ZONE
    ),
    (BoundaryKind.C_UPPER, SegmentDirection.DOWN): TransitionRule(
        old_zone=ZoneState.OUTSIDE_C,
        new_zone=ZoneState.IN_C,
        event_type=ZoneEventType.RETURN_INSIDE_C_BOUNDARY,
    ),
    (BoundaryKind.C_LOWER, SegmentDirection.UP): TransitionRule(
        old_zone=ZoneState.OUTSIDE_C,
        new_zone=ZoneState.IN_C,
        event_type=ZoneEventType.RETURN_INSIDE_C_BOUNDARY,
    ),
}


def transition_rule(boundary_kind: BoundaryKind, direction: SegmentDirection) -> TransitionRule:
    return _TRANSITION_TABLE[(boundary_kind, direction)]
