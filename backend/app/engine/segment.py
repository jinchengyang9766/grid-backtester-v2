"""Deterministic, non-recursive segment traversal and action planning.

Implements SPEC Sections 14.3 (segment processing), 10.3 (mutable zone_state),
11.6 (event-date attribution: always segment.end.date), and the Section 15
anchor invariants: nothing in this module ever writes trade_anchor.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.enums import ZoneState
from app.engine.crossing import (
    boundary_kind,
    determine_segment_direction,
    is_strictly_between,
    plan_grid_crossings,
    transition_rule,
)
from app.engine.grid import classify_zone
from app.engine.grid_models import ZoneBoundaries
from app.engine.path_models import InitialPathState, PathSegment
from app.engine.segment_models import (
    BoundaryKind,
    PlannedGridCrossing,
    SegmentDirection,
    SegmentTraversalState,
    ZoneEvent,
)

__all__ = [
    "InvalidZoneTransitionError",
    "apply_boundary_transition",
    "create_traversal_state",
    "plan_segment_actions",
]


class InvalidZoneTransitionError(Exception):
    def __init__(
        self,
        *,
        boundary_kind: BoundaryKind,
        direction: SegmentDirection,
        expected_zone: ZoneState,
        actual_zone: ZoneState,
    ) -> None:
        super().__init__(
            f"Transition {boundary_kind.value} {direction.value} requires zone "
            f"{expected_zone.value}, but the current zone is {actual_zone.value}."
        )
        self.boundary_kind = boundary_kind
        self.direction = direction
        self.expected_zone = expected_zone
        self.actual_zone = actual_zone


def create_traversal_state(initial_state: InitialPathState) -> SegmentTraversalState:
    return SegmentTraversalState(
        market_cursor=initial_state.market_cursor,
        trade_anchor=initial_state.trade_anchor,
        zone_state=initial_state.zone_state,
    )


def apply_boundary_transition(
    *,
    boundary_price: Decimal,
    boundary: BoundaryKind,
    direction: SegmentDirection,
    event_date: date,
    state: SegmentTraversalState,
) -> ZoneEvent:
    rule = transition_rule(boundary, direction)
    if state.zone_state is not rule.old_zone:
        raise InvalidZoneTransitionError(
            boundary_kind=boundary,
            direction=direction,
            expected_zone=rule.old_zone,
            actual_zone=state.zone_state,
        )
    event = ZoneEvent(
        event_type=rule.event_type,
        boundary_price=boundary_price,
        event_date=event_date,
        old_zone=rule.old_zone,
        new_zone=rule.new_zone,
    )
    state.zone_state = rule.new_zone
    state.market_cursor = boundary_price
    return event


def _interior_boundaries(
    seg_start: Decimal,
    seg_end: Decimal,
    direction: SegmentDirection,
    boundaries: ZoneBoundaries,
) -> list[tuple[Decimal, BoundaryKind]]:
    labeled = (
        (boundaries.a_upper, BoundaryKind.A_UPPER),
        (boundaries.a_lower, BoundaryKind.A_LOWER),
        (boundaries.c_upper, BoundaryKind.C_UPPER),
        (boundaries.c_lower, BoundaryKind.C_LOWER),
    )
    return sorted(
        (pair for pair in labeled if is_strictly_between(seg_start, pair[0], seg_end)),
        key=lambda pair: pair[0],
        reverse=direction is SegmentDirection.DOWN,
    )


def plan_segment_actions(
    segment: PathSegment,
    *,
    state: SegmentTraversalState,
    boundaries: ZoneBoundaries,
    grid_levels: Sequence[Decimal],
) -> tuple[PlannedGridCrossing | ZoneEvent, ...]:
    seg_start = segment.start.price
    seg_end = segment.end.price
    event_date = segment.end.date  # SPEC 11.6: every action is dated by the END point

    direction = determine_segment_direction(seg_start, seg_end)
    if direction is None:
        return ()  # equal-price segment: no movement, no direction, no actions

    actions: list[PlannedGridCrossing | ZoneEvent] = []

    # --- Starting exactly on a boundary: outward continuation transitions now;
    # inward continuation from the inner zone fires nothing (SPEC 14.3).
    starting_kind = boundary_kind(seg_start, boundaries)
    if starting_kind is not None:
        rule = transition_rule(starting_kind, direction)
        if state.zone_state is rule.old_zone:
            actions.append(
                apply_boundary_transition(
                    boundary_price=seg_start,
                    boundary=starting_kind,
                    direction=direction,
                    event_date=event_date,
                    state=state,
                )
            )

    # --- Interior boundaries, flat pass in price-travel order (never recursive).
    # is_strictly_between excludes both endpoints, so the starting/ending
    # boundary can never reappear here: at most one transition per boundary.
    sub_start = seg_start
    for boundary_price, kind in _interior_boundaries(seg_start, seg_end, direction, boundaries):
        if state.zone_state is ZoneState.IN_A:
            actions.extend(
                plan_grid_crossings(
                    sub_start,
                    boundary_price,
                    direction,
                    grid_levels,
                    state.trade_anchor,
                    event_date,
                )
            )
        actions.append(
            apply_boundary_transition(
                boundary_price=boundary_price,
                boundary=kind,
                direction=direction,
                event_date=event_date,
                state=state,
            )
        )
        sub_start = boundary_price

    # --- Final leg.
    if state.zone_state is ZoneState.IN_A:
        actions.extend(
            plan_grid_crossings(
                sub_start, seg_end, direction, grid_levels, state.trade_anchor, event_date
            )
        )
    state.market_cursor = seg_end

    # --- Ending exactly on a boundary: reaching from the outer side already
    # re-classifies inward (SPEC 7.5), so the inward event fires once; from
    # the inner side the resting zone is unchanged and nothing fires.
    ending_kind = boundary_kind(seg_end, boundaries)
    if ending_kind is not None:
        resting_zone = classify_zone(seg_end, boundaries)
        if state.zone_state is not resting_zone:
            inward_direction = (
                SegmentDirection.DOWN
                if ending_kind in (BoundaryKind.A_UPPER, BoundaryKind.C_UPPER)
                else SegmentDirection.UP
            )
            actions.append(
                apply_boundary_transition(
                    boundary_price=seg_end,
                    boundary=ending_kind,
                    direction=inward_direction,
                    event_date=event_date,
                    state=state,
                )
            )

    return tuple(actions)
