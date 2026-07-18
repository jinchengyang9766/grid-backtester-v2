"""Tests for crossing detection and A/C/Outside-C segment transition planning."""

import inspect
from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import TradeSide, ZoneEventType, ZoneState
from app.domain.models import PathPoint
from app.engine.crossing import (
    boundary_kind,
    determine_segment_direction,
    eligible_grid_levels,
    is_strictly_between,
    plan_grid_crossings,
    transition_rule,
)
from app.engine.grid_models import ZoneBoundaries
from app.engine.path_models import InitialPathState, PathSegment
from app.engine.segment import (
    InvalidZoneTransitionError,
    apply_boundary_transition,
    create_traversal_state,
    plan_segment_actions,
)
from app.engine.segment_models import (
    BoundaryKind,
    PlannedGridCrossing,
    SegmentDirection,
    SegmentTraversalState,
    TransitionRule,
    ZoneEvent,
)

D = Decimal

BOUNDARIES = ZoneBoundaries(
    baseline=D("1.00"),
    a_lower=D("0.90"),
    a_upper=D("1.10"),
    c_lower=D("0.80"),
    c_upper=D("1.20"),
)

GRID = (D("0.90"), D("0.95"), D("1.00"), D("1.05"), D("1.10"))

DAY_2 = date(2026, 1, 2)
DAY_3 = date(2026, 1, 3)

BOUNDARY_PRICES = {
    BoundaryKind.A_UPPER: D("1.10"),
    BoundaryKind.A_LOWER: D("0.90"),
    BoundaryKind.C_UPPER: D("1.20"),
    BoundaryKind.C_LOWER: D("0.80"),
}

TRANSITION_CASES = [
    (
        BoundaryKind.A_UPPER,
        SegmentDirection.UP,
        ZoneState.IN_A,
        ZoneState.IN_C,
        ZoneEventType.ENTER_C_ZONE,
    ),
    (
        BoundaryKind.A_LOWER,
        SegmentDirection.DOWN,
        ZoneState.IN_A,
        ZoneState.IN_C,
        ZoneEventType.ENTER_C_ZONE,
    ),
    (
        BoundaryKind.C_UPPER,
        SegmentDirection.UP,
        ZoneState.IN_C,
        ZoneState.OUTSIDE_C,
        ZoneEventType.OUTSIDE_C_BOUNDARY,
    ),
    (
        BoundaryKind.C_LOWER,
        SegmentDirection.DOWN,
        ZoneState.IN_C,
        ZoneState.OUTSIDE_C,
        ZoneEventType.OUTSIDE_C_BOUNDARY,
    ),
    (
        BoundaryKind.A_UPPER,
        SegmentDirection.DOWN,
        ZoneState.IN_C,
        ZoneState.IN_A,
        ZoneEventType.EXIT_C_ZONE,
    ),
    (
        BoundaryKind.A_LOWER,
        SegmentDirection.UP,
        ZoneState.IN_C,
        ZoneState.IN_A,
        ZoneEventType.EXIT_C_ZONE,
    ),
    (
        BoundaryKind.C_UPPER,
        SegmentDirection.DOWN,
        ZoneState.OUTSIDE_C,
        ZoneState.IN_C,
        ZoneEventType.RETURN_INSIDE_C_BOUNDARY,
    ),
    (
        BoundaryKind.C_LOWER,
        SegmentDirection.UP,
        ZoneState.OUTSIDE_C,
        ZoneState.IN_C,
        ZoneEventType.RETURN_INSIDE_C_BOUNDARY,
    ),
]


def point(price: str, day: int = 2, final: bool = False) -> PathPoint:
    return PathPoint(price=D(price), date=date(2026, 1, day), is_bar_final=final)


def make_segment(start: str, end: str, *, start_day: int = 2, end_day: int = 2) -> PathSegment:
    return PathSegment(start=point(start, start_day), end=point(end, end_day))


def make_state(
    cursor: str = "1.00",
    anchor: str = "1.00",
    zone: ZoneState = ZoneState.IN_A,
) -> SegmentTraversalState:
    return SegmentTraversalState(market_cursor=D(cursor), trade_anchor=D(anchor), zone_state=zone)


def crossings_of(
    actions: tuple[PlannedGridCrossing | ZoneEvent, ...],
) -> list[PlannedGridCrossing]:
    return [action for action in actions if isinstance(action, PlannedGridCrossing)]


def events_of(actions: tuple[PlannedGridCrossing | ZoneEvent, ...]) -> list[ZoneEvent]:
    return [action for action in actions if isinstance(action, ZoneEvent)]


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------


def test_upward_direction() -> None:
    assert determine_segment_direction(D("1.00"), D("1.05")) is SegmentDirection.UP


def test_downward_direction() -> None:
    assert determine_segment_direction(D("1.05"), D("1.00")) is SegmentDirection.DOWN


def test_equal_prices_have_no_direction() -> None:
    assert determine_segment_direction(D("1.00"), D("1.00")) is None


# ---------------------------------------------------------------------------
# Crossing inclusivity
# ---------------------------------------------------------------------------


def test_downward_far_endpoint_included_and_start_excluded() -> None:
    levels = eligible_grid_levels(D("1.00"), D("0.90"), SegmentDirection.DOWN, GRID, D("1.05"))
    assert levels == (D("0.95"), D("0.90"))
    assert D("1.00") not in levels  # segment start never retriggers


def test_upward_far_endpoint_included_and_start_excluded() -> None:
    levels = eligible_grid_levels(D("1.00"), D("1.10"), SegmentDirection.UP, GRID, D("0.95"))
    assert levels == (D("1.05"), D("1.10"))
    assert D("1.00") not in levels


def test_anchor_itself_excluded_downward() -> None:
    levels = eligible_grid_levels(D("1.10"), D("0.90"), SegmentDirection.DOWN, GRID, D("1.00"))
    assert D("1.00") not in levels
    assert levels == (D("0.95"), D("0.90"))


def test_anchor_itself_excluded_upward() -> None:
    levels = eligible_grid_levels(D("0.90"), D("1.10"), SegmentDirection.UP, GRID, D("1.00"))
    assert D("1.00") not in levels
    assert levels == (D("1.05"), D("1.10"))


def test_downward_levels_must_be_below_anchor() -> None:
    levels = eligible_grid_levels(D("1.10"), D("0.90"), SegmentDirection.DOWN, GRID, D("0.95"))
    assert levels == (D("0.90"),)


def test_upward_levels_must_be_above_anchor() -> None:
    levels = eligible_grid_levels(D("0.90"), D("1.10"), SegmentDirection.UP, GRID, D("1.05"))
    assert levels == (D("1.10"),)


def test_downward_ordering_is_high_to_low() -> None:
    levels = eligible_grid_levels(D("1.11"), D("0.89"), SegmentDirection.DOWN, GRID, D("1.20"))
    assert levels == (D("1.10"), D("1.05"), D("1.00"), D("0.95"), D("0.90"))


def test_upward_ordering_is_low_to_high() -> None:
    levels = eligible_grid_levels(D("0.89"), D("1.11"), SegmentDirection.UP, GRID, D("0.80"))
    assert levels == (D("0.90"), D("0.95"), D("1.00"), D("1.05"), D("1.10"))


def test_no_eligible_levels_returns_empty_tuple() -> None:
    assert eligible_grid_levels(D("1.01"), D("1.02"), SegmentDirection.UP, GRID, D("1.00")) == ()


def test_exact_decimal_values_are_preserved() -> None:
    grid = (D("1.0500"),)
    levels = eligible_grid_levels(D("1.00"), D("1.10"), SegmentDirection.UP, grid, D("1.00"))
    assert str(levels[0]) == "1.0500"


def test_input_grid_sequence_is_not_mutated_or_reordered() -> None:
    grid = [D("1.10"), D("0.90"), D("1.00")]  # deliberately unsorted
    eligible_grid_levels(D("0.85"), D("1.15"), SegmentDirection.UP, grid, D("0.80"))
    assert grid == [D("1.10"), D("0.90"), D("1.00")]


def test_down_creates_buy_plans_with_event_date() -> None:
    plans = plan_grid_crossings(D("1.00"), D("0.90"), SegmentDirection.DOWN, GRID, D("1.05"), DAY_3)
    assert plans == (
        PlannedGridCrossing(grid_level=D("0.95"), side=TradeSide.BUY, event_date=DAY_3),
        PlannedGridCrossing(grid_level=D("0.90"), side=TradeSide.BUY, event_date=DAY_3),
    )


def test_up_creates_sell_plans_with_event_date() -> None:
    plans = plan_grid_crossings(D("1.00"), D("1.10"), SegmentDirection.UP, GRID, D("0.95"), DAY_2)
    assert [plan.side for plan in plans] == [TradeSide.SELL, TradeSide.SELL]
    assert all(plan.event_date == DAY_2 for plan in plans)


# ---------------------------------------------------------------------------
# Strict betweenness
# ---------------------------------------------------------------------------


def test_upward_interior_accepted() -> None:
    assert is_strictly_between(D("1.00"), D("1.05"), D("1.10")) is True


def test_downward_interior_accepted() -> None:
    assert is_strictly_between(D("1.10"), D("1.05"), D("1.00")) is True


def test_start_endpoint_excluded() -> None:
    assert is_strictly_between(D("1.00"), D("1.00"), D("1.10")) is False


def test_end_endpoint_excluded() -> None:
    assert is_strictly_between(D("1.00"), D("1.10"), D("1.10")) is False


def test_outside_value_rejected() -> None:
    assert is_strictly_between(D("1.00"), D("1.15"), D("1.10")) is False


def test_equal_segment_rejected() -> None:
    assert is_strictly_between(D("1.00"), D("1.00"), D("1.00")) is False


# ---------------------------------------------------------------------------
# Boundary lookup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("expected", "price"), list(BOUNDARY_PRICES.items()))
def test_all_four_exact_boundaries_recognized(expected: BoundaryKind, price: Decimal) -> None:
    assert boundary_kind(price, BOUNDARIES) is expected


def test_non_boundary_returns_none() -> None:
    assert boundary_kind(D("1.00"), BOUNDARIES) is None


def test_no_tolerance_matching() -> None:
    assert boundary_kind(D("1.1001"), BOUNDARIES) is None
    assert boundary_kind(D("1.0999"), BOUNDARIES) is None


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("kind", "direction", "old", "new", "event_type"), TRANSITION_CASES)
def test_transition_table_rows(
    kind: BoundaryKind,
    direction: SegmentDirection,
    old: ZoneState,
    new: ZoneState,
    event_type: ZoneEventType,
) -> None:
    assert transition_rule(kind, direction) == TransitionRule(
        old_zone=old, new_zone=new, event_type=event_type
    )


# ---------------------------------------------------------------------------
# Applying transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("kind", "direction", "old", "new", "event_type"), TRANSITION_CASES)
def test_valid_transition_updates_state_and_returns_exact_event(
    kind: BoundaryKind,
    direction: SegmentDirection,
    old: ZoneState,
    new: ZoneState,
    event_type: ZoneEventType,
) -> None:
    state = make_state(cursor="1.00", anchor="0.97", zone=old)
    price = BOUNDARY_PRICES[kind]
    event = apply_boundary_transition(
        boundary_price=price, boundary=kind, direction=direction, event_date=DAY_3, state=state
    )
    assert event == ZoneEvent(
        event_type=event_type, boundary_price=price, event_date=DAY_3, old_zone=old, new_zone=new
    )
    assert state.zone_state is new
    assert state.market_cursor == price
    assert state.trade_anchor == D("0.97")  # never changed by a transition


def test_invalid_prior_zone_raises_with_all_fields() -> None:
    state = make_state(zone=ZoneState.OUTSIDE_C)
    with pytest.raises(InvalidZoneTransitionError) as exc_info:
        apply_boundary_transition(
            boundary_price=D("1.10"),
            boundary=BoundaryKind.A_UPPER,
            direction=SegmentDirection.UP,
            event_date=DAY_2,
            state=state,
        )
    error = exc_info.value
    assert error.boundary_kind is BoundaryKind.A_UPPER
    assert error.direction is SegmentDirection.UP
    assert error.expected_zone is ZoneState.IN_A
    assert error.actual_zone is ZoneState.OUTSIDE_C


def test_create_traversal_state_copies_initial_values_exactly() -> None:
    initial = InitialPathState(
        market_cursor=D("1.0007"), trade_anchor=D("1.0007"), zone_state=ZoneState.IN_A
    )
    state = create_traversal_state(initial)
    assert state.market_cursor == D("1.0007")
    assert state.trade_anchor == D("1.0007")
    assert state.zone_state is ZoneState.IN_A
    state.market_cursor = D("2.00")  # mutable copy, snapshot unaffected
    assert initial.market_cursor == D("1.0007")


# ---------------------------------------------------------------------------
# Segment planning: basics
# ---------------------------------------------------------------------------


def test_equal_price_segment_produces_no_actions_and_no_state_change() -> None:
    state = make_state()
    actions = plan_segment_actions(
        make_segment("1.00", "1.00"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert actions == ()
    assert state.market_cursor == D("1.00")
    assert state.zone_state is ZoneState.IN_A
    assert state.trade_anchor == D("1.00")


def test_in_a_upward_segment_plans_sells() -> None:
    state = make_state(cursor="0.98", anchor="0.96")
    actions = plan_segment_actions(
        make_segment("0.98", "1.07"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert actions == (
        PlannedGridCrossing(grid_level=D("1.00"), side=TradeSide.SELL, event_date=DAY_2),
        PlannedGridCrossing(grid_level=D("1.05"), side=TradeSide.SELL, event_date=DAY_2),
    )
    assert state.market_cursor == D("1.07")


def test_in_a_downward_segment_plans_buys() -> None:
    state = make_state(cursor="1.02", anchor="1.00")
    actions = plan_segment_actions(
        make_segment("1.02", "0.93"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert actions == (
        PlannedGridCrossing(grid_level=D("0.95"), side=TradeSide.BUY, event_date=DAY_2),
    )


def test_no_crossings_planned_in_c() -> None:
    state = make_state(cursor="1.12", anchor="1.00", zone=ZoneState.IN_C)
    actions = plan_segment_actions(
        make_segment("1.12", "1.18"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert actions == ()


def test_no_crossings_planned_outside_c() -> None:
    state = make_state(cursor="1.25", anchor="1.00", zone=ZoneState.OUTSIDE_C)
    actions = plan_segment_actions(
        make_segment("1.25", "1.30"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert actions == ()


# ---------------------------------------------------------------------------
# Segment planning: single transitions in every direction
# ---------------------------------------------------------------------------


def test_a_to_c_upward_transition() -> None:
    state = make_state(cursor="1.08", anchor="1.20")
    actions = plan_segment_actions(
        make_segment("1.08", "1.12"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    events = events_of(actions)
    assert [e.event_type for e in events] == [ZoneEventType.ENTER_C_ZONE]
    assert events[0].boundary_price == D("1.10")
    assert state.zone_state is ZoneState.IN_C


def test_a_to_c_downward_transition_grid_action_before_enter_c() -> None:
    state = make_state(cursor="0.95", anchor="1.00")
    actions = plan_segment_actions(
        make_segment("0.95", "0.85"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    # 0.90 is both a grid level and A_Lower: BUY plan precedes ENTER_C_ZONE.
    assert actions == (
        PlannedGridCrossing(grid_level=D("0.90"), side=TradeSide.BUY, event_date=DAY_2),
        ZoneEvent(
            event_type=ZoneEventType.ENTER_C_ZONE,
            boundary_price=D("0.90"),
            event_date=DAY_2,
            old_zone=ZoneState.IN_A,
            new_zone=ZoneState.IN_C,
        ),
    )
    assert state.zone_state is ZoneState.IN_C


def test_c_to_a_downward_transition() -> None:
    state = make_state(cursor="1.15", anchor="1.00", zone=ZoneState.IN_C)
    actions = plan_segment_actions(
        make_segment("1.15", "1.05"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert [e.event_type for e in events_of(actions)] == [ZoneEventType.EXIT_C_ZONE]
    assert crossings_of(actions) == []  # anchor 1.00: no level below it is reached going down
    assert state.zone_state is ZoneState.IN_A


def test_c_to_a_upward_transition() -> None:
    state = make_state(cursor="0.85", anchor="0.95", zone=ZoneState.IN_C)
    actions = plan_segment_actions(
        make_segment("0.85", "0.92"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    events = events_of(actions)
    assert [e.event_type for e in events] == [ZoneEventType.EXIT_C_ZONE]
    assert events[0].boundary_price == D("0.90")
    assert state.zone_state is ZoneState.IN_A


def test_c_to_outside_upward_transition() -> None:
    state = make_state(cursor="1.15", anchor="1.00", zone=ZoneState.IN_C)
    actions = plan_segment_actions(
        make_segment("1.15", "1.22"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert [e.event_type for e in events_of(actions)] == [ZoneEventType.OUTSIDE_C_BOUNDARY]
    assert state.zone_state is ZoneState.OUTSIDE_C


def test_c_to_outside_downward_transition() -> None:
    state = make_state(cursor="0.85", anchor="1.00", zone=ZoneState.IN_C)
    actions = plan_segment_actions(
        make_segment("0.85", "0.78"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert [e.event_type for e in events_of(actions)] == [ZoneEventType.OUTSIDE_C_BOUNDARY]
    assert state.zone_state is ZoneState.OUTSIDE_C


def test_outside_to_c_downward_transition() -> None:
    state = make_state(cursor="1.25", anchor="1.00", zone=ZoneState.OUTSIDE_C)
    actions = plan_segment_actions(
        make_segment("1.25", "1.15"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert [e.event_type for e in events_of(actions)] == [ZoneEventType.RETURN_INSIDE_C_BOUNDARY]
    assert state.zone_state is ZoneState.IN_C


def test_outside_to_c_upward_transition() -> None:
    state = make_state(cursor="0.75", anchor="1.00", zone=ZoneState.OUTSIDE_C)
    actions = plan_segment_actions(
        make_segment("0.75", "0.85"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert [e.event_type for e in events_of(actions)] == [ZoneEventType.RETURN_INSIDE_C_BOUNDARY]
    assert state.zone_state is ZoneState.IN_C


# ---------------------------------------------------------------------------
# Segment planning: multi-boundary gaps and boundary edge cases
# ---------------------------------------------------------------------------


def test_gap_crossing_a_and_c_boundaries_emits_both_events_in_travel_order() -> None:
    state = make_state()
    actions = plan_segment_actions(
        make_segment("1.00", "1.25", end_day=3),
        state=state,
        boundaries=BOUNDARIES,
        grid_levels=GRID,
    )
    assert actions == (
        PlannedGridCrossing(grid_level=D("1.05"), side=TradeSide.SELL, event_date=DAY_3),
        PlannedGridCrossing(grid_level=D("1.10"), side=TradeSide.SELL, event_date=DAY_3),
        ZoneEvent(
            event_type=ZoneEventType.ENTER_C_ZONE,
            boundary_price=D("1.10"),
            event_date=DAY_3,
            old_zone=ZoneState.IN_A,
            new_zone=ZoneState.IN_C,
        ),
        ZoneEvent(
            event_type=ZoneEventType.OUTSIDE_C_BOUNDARY,
            boundary_price=D("1.20"),
            event_date=DAY_3,
            old_zone=ZoneState.IN_C,
            new_zone=ZoneState.OUTSIDE_C,
        ),
    )
    assert state.zone_state is ZoneState.OUTSIDE_C
    assert state.market_cursor == D("1.25")


def test_downward_multi_boundary_events_use_descending_travel_order() -> None:
    state = make_state()
    actions = plan_segment_actions(
        make_segment("1.00", "0.75"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert actions == (
        PlannedGridCrossing(grid_level=D("0.95"), side=TradeSide.BUY, event_date=DAY_2),
        PlannedGridCrossing(grid_level=D("0.90"), side=TradeSide.BUY, event_date=DAY_2),
        ZoneEvent(
            event_type=ZoneEventType.ENTER_C_ZONE,
            boundary_price=D("0.90"),
            event_date=DAY_2,
            old_zone=ZoneState.IN_A,
            new_zone=ZoneState.IN_C,
        ),
        ZoneEvent(
            event_type=ZoneEventType.OUTSIDE_C_BOUNDARY,
            boundary_price=D("0.80"),
            event_date=DAY_2,
            old_zone=ZoneState.IN_C,
            new_zone=ZoneState.OUTSIDE_C,
        ),
    )


def test_starting_exactly_at_a_boundary_moving_outward_transitions_immediately() -> None:
    state = make_state(cursor="1.10", anchor="1.00")
    actions = plan_segment_actions(
        make_segment("1.10", "1.15"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert len(actions) == 1
    (event,) = events_of(actions)
    assert event.event_type is ZoneEventType.ENTER_C_ZONE
    assert event.boundary_price == D("1.10")
    assert state.zone_state is ZoneState.IN_C


def test_starting_exactly_at_a_boundary_moving_inward_does_not_transition() -> None:
    state = make_state(cursor="1.10", anchor="1.00")
    actions = plan_segment_actions(
        make_segment("1.10", "1.05"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert events_of(actions) == []
    assert state.zone_state is ZoneState.IN_A


def test_ending_exactly_at_a_boundary_from_inside_plans_grid_but_stays_in_a() -> None:
    state = make_state(cursor="1.02", anchor="1.00")
    actions = plan_segment_actions(
        make_segment("1.02", "1.10"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert actions == (
        PlannedGridCrossing(grid_level=D("1.05"), side=TradeSide.SELL, event_date=DAY_2),
        PlannedGridCrossing(grid_level=D("1.10"), side=TradeSide.SELL, event_date=DAY_2),
    )
    assert state.zone_state is ZoneState.IN_A  # reached, not passed: no ENTER_C_ZONE


def test_ending_exactly_at_c_boundary_from_outside_emits_return_event() -> None:
    state = make_state(cursor="1.25", anchor="1.00", zone=ZoneState.OUTSIDE_C)
    actions = plan_segment_actions(
        make_segment("1.25", "1.20"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert [e.event_type for e in events_of(actions)] == [ZoneEventType.RETURN_INSIDE_C_BOUNDARY]
    assert events_of(actions)[0].boundary_price == D("1.20")
    assert state.zone_state is ZoneState.IN_C


def test_each_boundary_emits_at_most_one_event_per_segment() -> None:
    state = make_state(cursor="1.10", anchor="1.00")
    actions = plan_segment_actions(
        make_segment("1.10", "1.25"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    prices = [e.boundary_price for e in events_of(actions)]
    assert prices == [D("1.10"), D("1.20")]  # each boundary exactly once, travel order
    assert len(set(prices)) == len(prices)


def test_ending_boundary_crossed_from_outer_zone_chains_after_interior() -> None:
    state = make_state(cursor="1.30", anchor="1.00", zone=ZoneState.OUTSIDE_C)
    actions = plan_segment_actions(
        make_segment("1.30", "1.10"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert [e.event_type for e in events_of(actions)] == [
        ZoneEventType.RETURN_INSIDE_C_BOUNDARY,  # interior C_Upper at 1.20
        ZoneEventType.EXIT_C_ZONE,  # ending exactly on A_Upper from outside
    ]
    assert state.zone_state is ZoneState.IN_A


def test_final_cursor_anchor_and_inputs_after_planning() -> None:
    state = make_state(cursor="1.00", anchor="1.00")
    segment = make_segment("1.00", "1.25", end_day=3)
    grid = GRID
    plan_segment_actions(segment, state=state, boundaries=BOUNDARIES, grid_levels=grid)
    assert state.market_cursor == D("1.25")
    assert state.trade_anchor == D("1.00")  # unchanged through all transitions
    assert segment == make_segment("1.00", "1.25", end_day=3)
    assert grid == (D("0.90"), D("0.95"), D("1.00"), D("1.05"), D("1.10"))
    assert BOUNDARIES.a_upper == D("1.10")


def test_all_actions_use_segment_end_date_for_overnight_segments() -> None:
    state = make_state()
    actions = plan_segment_actions(
        make_segment("1.00", "1.25", start_day=2, end_day=3),
        state=state,
        boundaries=BOUNDARIES,
        grid_levels=GRID,
    )
    assert len(actions) == 4
    assert all(action.event_date == DAY_3 for action in actions)


def test_plan_segment_actions_is_not_recursive() -> None:
    source = inspect.getsource(plan_segment_actions)
    assert source.count("plan_segment_actions") == 1  # its own def line only


# ---------------------------------------------------------------------------
# No-backfill invariants
# ---------------------------------------------------------------------------


def test_returning_from_c_preserves_anchor_and_plans_no_trade() -> None:
    state = make_state(cursor="0.85", anchor="0.95", zone=ZoneState.IN_C)
    actions = plan_segment_actions(
        make_segment("0.85", "0.92"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert crossings_of(actions) == []  # re-entry alone plans nothing
    assert [e.event_type for e in events_of(actions)] == [ZoneEventType.EXIT_C_ZONE]
    assert state.trade_anchor == D("0.95")
    assert state.zone_state is ZoneState.IN_A


def test_levels_crossed_only_within_c_never_appear() -> None:
    # 0.85 -> 0.92 passes grid level 0.90 while IN_C until the boundary;
    # 0.90 is the A boundary itself and the exit is an event, not a trade.
    state = make_state(cursor="0.85", anchor="0.95", zone=ZoneState.IN_C)
    actions = plan_segment_actions(
        make_segment("0.85", "0.92"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert all(not isinstance(action, PlannedGridCrossing) for action in actions)


def test_later_in_a_movement_uses_preserved_anchor() -> None:
    state = make_state(cursor="0.85", anchor="0.95", zone=ZoneState.IN_C)
    plan_segment_actions(
        make_segment("0.85", "0.92"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    actions = plan_segment_actions(
        make_segment("0.92", "1.00"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    # First grid strictly above the preserved 0.95 anchor is 1.00; nothing below
    # or equal to the anchor is backfilled.
    assert actions == (
        PlannedGridCrossing(grid_level=D("1.00"), side=TradeSide.SELL, event_date=DAY_2),
    )
    assert state.trade_anchor == D("0.95")


def test_anchor_itself_is_never_retriggered() -> None:
    state = make_state(cursor="0.92", anchor="0.95", zone=ZoneState.IN_A)
    actions = plan_segment_actions(
        make_segment("0.92", "0.95"), state=state, boundaries=BOUNDARIES, grid_levels=GRID
    )
    assert actions == ()


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def test_public_imports_work_from_app_engine() -> None:
    import app.engine as engine_pkg

    assert engine_pkg.SegmentDirection is SegmentDirection
    assert engine_pkg.BoundaryKind is BoundaryKind
    assert engine_pkg.SegmentTraversalState is SegmentTraversalState
    assert engine_pkg.TransitionRule is TransitionRule
    assert engine_pkg.PlannedGridCrossing is PlannedGridCrossing
    assert engine_pkg.ZoneEvent is ZoneEvent
    assert engine_pkg.InvalidZoneTransitionError is InvalidZoneTransitionError
    assert engine_pkg.create_traversal_state is create_traversal_state
    assert engine_pkg.determine_segment_direction is determine_segment_direction
    assert engine_pkg.eligible_grid_levels is eligible_grid_levels
    assert engine_pkg.plan_grid_crossings is plan_grid_crossings
    assert engine_pkg.is_strictly_between is is_strictly_between
    assert engine_pkg.boundary_kind is boundary_kind
    assert engine_pkg.transition_rule is transition_rule
    assert engine_pkg.apply_boundary_transition is apply_boundary_transition
    assert engine_pkg.plan_segment_actions is plan_segment_actions


def test_prior_task_exports_remain_available() -> None:
    import app.engine as engine_pkg

    assert callable(engine_pkg.build_grid_setup)
    assert callable(engine_pkg.classify_zone)
    assert callable(engine_pkg.build_price_path)
    assert callable(engine_pkg.build_path_segments)
    assert callable(engine_pkg.initialize_path_state)
    assert engine_pkg.MAX_GRID_LEVELS == 10_000


def test_segment_modules_have_no_framework_or_portfolio_dependencies() -> None:
    import app.engine.crossing
    import app.engine.segment
    import app.engine.segment_models

    modules = (app.engine.crossing, app.engine.segment, app.engine.segment_models)
    for module in modules:
        source = inspect.getsource(module).lower()
        for forbidden in (
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "app.importing",
            "cash",
            "shares",
            "commission",
            "slippage",
            "portfolio",
            "metric",
        ):
            assert forbidden not in source, f"{module.__name__} contains {forbidden!r}"


def test_no_database_trade_model_is_introduced() -> None:
    # Task 9 later adds the pure TradeResult value object; a persistence-style
    # Trade entity must still never appear in the pure engine package.
    import app.engine as engine_pkg

    assert not hasattr(engine_pkg, "Trade")
