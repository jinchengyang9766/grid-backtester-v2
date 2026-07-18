"""Tests for price-path construction, segmentation, and initial state."""

import inspect
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import DataMode, OHLCPathMode, ZoneState
from app.domain.models import Bar, PathPoint
from app.engine.grid import EmptyDatasetError
from app.engine.grid_models import ZoneBoundaries
from app.engine.path import (
    InvalidOhlcvBarError,
    OhlcPathModeRequiredError,
    build_close_only_path,
    build_ohlcv_path,
    build_path_segments,
    build_price_path,
    initialize_path_state,
    select_ohlc_midpoints,
)
from app.engine.path_models import InitialPathState, PathSegment


def ohlcv_bar(day: int, open_: str, high: str, low: str, close: str) -> Bar:
    return Bar(
        date=date(2026, 1, day),
        close=Decimal(close),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
    )


def close_bar(day: int, close: str) -> Bar:
    return Bar(date=date(2026, 1, day), close=Decimal(close))


BAR_1 = ohlcv_bar(2, "1.00", "1.10", "0.90", "1.05")  # up day: Close > Open
BAR_2 = ohlcv_bar(3, "1.08", "1.20", "1.00", "0.95")  # down day: Close < Open

BOUNDARIES = ZoneBoundaries(
    baseline=Decimal("1.00"),
    a_lower=Decimal("0.90"),
    a_upper=Decimal("1.10"),
    c_lower=Decimal("0.80"),
    c_upper=Decimal("1.20"),
)


# ---------------------------------------------------------------------------
# OHLC midpoint selection
# ---------------------------------------------------------------------------


def test_high_first_returns_high_then_low() -> None:
    assert select_ohlc_midpoints(BAR_1, OHLCPathMode.HIGH_FIRST) == (
        Decimal("1.10"),
        Decimal("0.90"),
    )


def test_low_first_returns_low_then_high() -> None:
    assert select_ohlc_midpoints(BAR_1, OHLCPathMode.LOW_FIRST) == (
        Decimal("0.90"),
        Decimal("1.10"),
    )


def test_auto_with_close_above_open_uses_low_then_high() -> None:
    assert select_ohlc_midpoints(BAR_1, OHLCPathMode.AUTO) == (Decimal("0.90"), Decimal("1.10"))


def test_auto_with_close_equal_to_open_uses_low_then_high() -> None:
    flat_bar = ohlcv_bar(2, "1.00", "1.10", "0.90", "1.00")
    assert select_ohlc_midpoints(flat_bar, OHLCPathMode.AUTO) == (Decimal("0.90"), Decimal("1.10"))


def test_auto_with_close_below_open_uses_high_then_low() -> None:
    assert select_ohlc_midpoints(BAR_2, OHLCPathMode.AUTO) == (Decimal("1.20"), Decimal("1.00"))


def test_auto_is_evaluated_independently_per_bar() -> None:
    assert select_ohlc_midpoints(BAR_1, OHLCPathMode.AUTO) == (Decimal("0.90"), Decimal("1.10"))
    assert select_ohlc_midpoints(BAR_2, OHLCPathMode.AUTO) == (Decimal("1.20"), Decimal("1.00"))


@pytest.mark.parametrize("missing_field", ["open", "high", "low"])
def test_missing_single_ohlc_field_raises(missing_field: str) -> None:
    values: dict[str, Decimal | None] = {
        "open": Decimal("1.00"),
        "high": Decimal("1.10"),
        "low": Decimal("0.90"),
    }
    values[missing_field] = None
    bar = Bar(date=date(2026, 1, 2), close=Decimal("1.05"), **values)
    with pytest.raises(InvalidOhlcvBarError) as exc_info:
        select_ohlc_midpoints(bar, OHLCPathMode.HIGH_FIRST, bar_index=4)
    assert exc_info.value.bar_index == 4
    assert exc_info.value.missing_fields == (missing_field,)


def test_multiple_missing_fields_preserve_canonical_order() -> None:
    bar = Bar(date=date(2026, 1, 2), close=Decimal("1.05"), high=Decimal("1.10"))
    with pytest.raises(InvalidOhlcvBarError) as exc_info:
        select_ohlc_midpoints(bar, OHLCPathMode.AUTO)
    assert exc_info.value.bar_index == 0
    assert exc_info.value.missing_fields == ("open", "low")


def test_all_missing_fields_are_reported_in_order() -> None:
    bar = close_bar(2, "1.05")
    with pytest.raises(InvalidOhlcvBarError) as exc_info:
        select_ohlc_midpoints(bar, OHLCPathMode.LOW_FIRST, bar_index=1)
    assert exc_info.value.missing_fields == ("open", "high", "low")


# ---------------------------------------------------------------------------
# OHLCV path construction
# ---------------------------------------------------------------------------


def test_ohlcv_empty_input_is_rejected() -> None:
    with pytest.raises(EmptyDatasetError):
        build_ohlcv_path([], OHLCPathMode.AUTO)


def test_one_bar_creates_exactly_four_points() -> None:
    points = build_ohlcv_path([BAR_1], OHLCPathMode.AUTO)
    assert len(points) == 4


def test_high_first_exact_point_sequence() -> None:
    points = build_ohlcv_path([BAR_1], OHLCPathMode.HIGH_FIRST)
    assert [p.price for p in points] == [
        Decimal("1.00"),
        Decimal("1.10"),
        Decimal("0.90"),
        Decimal("1.05"),
    ]


def test_low_first_exact_point_sequence() -> None:
    points = build_ohlcv_path([BAR_1], OHLCPathMode.LOW_FIRST)
    assert [p.price for p in points] == [
        Decimal("1.00"),
        Decimal("0.90"),
        Decimal("1.10"),
        Decimal("1.05"),
    ]


def test_auto_exact_point_sequence_uses_per_day_direction() -> None:
    points = build_ohlcv_path([BAR_1, BAR_2], OHLCPathMode.AUTO)
    assert [p.price for p in points] == [
        Decimal("1.00"),  # day 1 Open (up day: Open -> Low -> High -> Close)
        Decimal("0.90"),
        Decimal("1.10"),
        Decimal("1.05"),
        Decimal("1.08"),  # day 2 Open (down day: Open -> High -> Low -> Close)
        Decimal("1.20"),
        Decimal("1.00"),
        Decimal("0.95"),
    ]


def test_first_day_uses_its_full_path() -> None:
    points = build_ohlcv_path([BAR_1], OHLCPathMode.AUTO)
    assert points[0].price == Decimal("1.00")
    assert len(points) == 4


def test_every_point_carries_its_bar_date() -> None:
    points = build_ohlcv_path([BAR_1, BAR_2], OHLCPathMode.AUTO)
    assert [p.date for p in points[:4]] == [date(2026, 1, 2)] * 4
    assert [p.date for p in points[4:]] == [date(2026, 1, 3)] * 4


def test_only_close_points_have_is_bar_final() -> None:
    points = build_ohlcv_path([BAR_1, BAR_2], OHLCPathMode.AUTO)
    assert [p.is_bar_final for p in points] == [
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        True,
    ]


def test_two_bars_create_eight_continuous_points() -> None:
    points = build_ohlcv_path([BAR_1, BAR_2], OHLCPathMode.AUTO)
    assert len(points) == 8
    assert points[3].price == Decimal("1.05")  # Close[0]
    assert points[4].price == Decimal("1.08")  # Open[1], immediately adjacent


def test_equal_consecutive_prices_are_preserved() -> None:
    flat_bar = ohlcv_bar(2, "1.00", "1.00", "1.00", "1.00")
    points = build_ohlcv_path([flat_bar], OHLCPathMode.AUTO)
    assert [p.price for p in points] == [Decimal("1.00")] * 4


def test_decimal_values_remain_exact() -> None:
    bar = ohlcv_bar(2, "1.0007", "1.1000", "0.9001", "1.0500")
    points = build_ohlcv_path([bar], OHLCPathMode.LOW_FIRST)
    assert [str(p.price) for p in points] == ["1.0007", "0.9001", "1.1000", "1.0500"]


def test_input_bars_are_not_mutated() -> None:
    bars = [BAR_1, BAR_2]
    build_ohlcv_path(bars, OHLCPathMode.AUTO)
    assert bars == [
        ohlcv_bar(2, "1.00", "1.10", "0.90", "1.05"),
        ohlcv_bar(3, "1.08", "1.20", "1.00", "0.95"),
    ]


# ---------------------------------------------------------------------------
# Close-only path construction
# ---------------------------------------------------------------------------


def test_close_only_empty_input_is_rejected() -> None:
    with pytest.raises(EmptyDatasetError):
        build_close_only_path([])


def test_close_only_one_bar_creates_one_final_point() -> None:
    points = build_close_only_path([close_bar(2, "1.05")])
    assert points == (PathPoint(price=Decimal("1.05"), date=date(2026, 1, 2), is_bar_final=True),)


def test_close_only_one_bar_creates_no_segment() -> None:
    points = build_close_only_path([close_bar(2, "1.05")])
    assert build_path_segments(points) == ()


def test_close_only_creates_one_point_per_bar_all_final() -> None:
    bars = [close_bar(2, "1.05"), close_bar(3, "1.10"), close_bar(4, "0.95")]
    points = build_close_only_path(bars)
    assert len(points) == 3
    assert all(p.is_bar_final for p in points)
    assert [p.price for p in points] == [Decimal("1.05"), Decimal("1.10"), Decimal("0.95")]


def test_close_only_does_not_invent_baseline_to_first_close_point() -> None:
    points = build_close_only_path([close_bar(2, "1.05"), close_bar(3, "1.10")])
    assert points[0].price == Decimal("1.05")
    assert len(points) == 2


def test_close_only_ignores_ohlc_fields_entirely() -> None:
    bars = [close_bar(2, "1.05"), ohlcv_bar(3, "1.08", "1.20", "1.00", "0.95")]
    points = build_close_only_path(bars)
    assert [p.price for p in points] == [Decimal("1.05"), Decimal("0.95")]


def test_close_only_decimal_values_remain_exact() -> None:
    points = build_close_only_path([close_bar(2, "1.0500")])
    assert str(points[0].price) == "1.0500"


# ---------------------------------------------------------------------------
# Unified orchestration
# ---------------------------------------------------------------------------


def test_ohlcv_mode_requires_a_path_mode() -> None:
    with pytest.raises(OhlcPathModeRequiredError):
        build_price_path([BAR_1], DataMode.OHLCV)


def test_ohlcv_mode_routes_to_ohlcv_construction() -> None:
    points = build_price_path([BAR_1], DataMode.OHLCV, ohlc_path_mode=OHLCPathMode.HIGH_FIRST)
    assert points == build_ohlcv_path([BAR_1], OHLCPathMode.HIGH_FIRST)


def test_close_only_mode_routes_to_close_only_construction() -> None:
    bars = [close_bar(2, "1.05"), close_bar(3, "1.10")]
    assert build_price_path(bars, DataMode.CLOSE_ONLY) == build_close_only_path(bars)


def test_supplied_ohlc_mode_does_not_change_close_only_output() -> None:
    bars = [ohlcv_bar(2, "1.00", "1.10", "0.90", "1.05")]
    with_mode = build_price_path(bars, DataMode.CLOSE_ONLY, ohlc_path_mode=OHLCPathMode.AUTO)
    without_mode = build_price_path(bars, DataMode.CLOSE_ONLY)
    assert with_mode == without_mode == build_close_only_path(bars)


def test_explicit_data_mode_is_used_not_inferred() -> None:
    # Bars carry full OHLC data, but CLOSE_ONLY must still produce one point per Bar.
    points = build_price_path([BAR_1, BAR_2], DataMode.CLOSE_ONLY)
    assert len(points) == 2


# ---------------------------------------------------------------------------
# Adjacent segmentation
# ---------------------------------------------------------------------------


def test_segments_empty_points_are_rejected() -> None:
    with pytest.raises(EmptyDatasetError):
        build_path_segments([])


def test_one_point_gives_zero_segments() -> None:
    point = PathPoint(price=Decimal("1.00"), date=date(2026, 1, 2), is_bar_final=True)
    assert build_path_segments([point]) == ()


def test_n_points_give_n_minus_one_segments_in_exact_order() -> None:
    points = build_ohlcv_path([BAR_1, BAR_2], OHLCPathMode.AUTO)
    segments = build_path_segments(points)
    assert len(segments) == 7
    for index, segment in enumerate(segments):
        assert segment.start == points[index]
        assert segment.end == points[index + 1]


def test_equal_price_segment_is_retained_not_merged() -> None:
    flat_bar = ohlcv_bar(2, "1.00", "1.00", "1.00", "1.00")
    segments = build_path_segments(build_ohlcv_path([flat_bar], OHLCPathMode.AUTO))
    assert len(segments) == 3
    assert all(s.start.price == s.end.price == Decimal("1.00") for s in segments)


def test_overnight_close_to_open_segment_exists_with_next_day_event_date() -> None:
    points = build_ohlcv_path([BAR_1, BAR_2], OHLCPathMode.AUTO)
    overnight = build_path_segments(points)[3]
    assert overnight.start.price == Decimal("1.05")  # Close of day 1
    assert overnight.start.date == date(2026, 1, 2)
    assert overnight.start.is_bar_final is True
    assert overnight.end.price == Decimal("1.08")  # Open of day 2
    assert overnight.end.date == date(2026, 1, 3)  # event date convention: end.date
    assert overnight.end.is_bar_final is False


def test_close_only_segment_event_date_is_the_later_bars_date() -> None:
    points = build_close_only_path([close_bar(2, "1.05"), close_bar(3, "1.10")])
    (segment,) = build_path_segments(points)
    assert segment.end.date == date(2026, 1, 3)


def test_path_segment_is_immutable() -> None:
    points = build_close_only_path([close_bar(2, "1.05"), close_bar(3, "1.10")])
    (segment,) = build_path_segments(points)
    with pytest.raises(FrozenInstanceError):
        segment.end = segment.start  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Initial cursor/anchor state
# ---------------------------------------------------------------------------


def test_initialization_rejects_empty_points() -> None:
    with pytest.raises(EmptyDatasetError):
        initialize_path_state([], BOUNDARIES)


def test_ohlcv_initializes_at_first_open() -> None:
    points = build_ohlcv_path([BAR_1, BAR_2], OHLCPathMode.AUTO)
    state = initialize_path_state(points, BOUNDARIES)
    assert state.market_cursor == Decimal("1.00")
    assert state.trade_anchor == Decimal("1.00")


def test_close_only_initializes_at_first_close() -> None:
    points = build_close_only_path([close_bar(2, "1.05"), close_bar(3, "1.10")])
    state = initialize_path_state(points, BOUNDARIES)
    assert state.market_cursor == Decimal("1.05")
    assert state.trade_anchor == Decimal("1.05")


def test_baseline_differing_from_first_point_does_not_replace_cursor_or_anchor() -> None:
    points = build_close_only_path([close_bar(2, "1.05")])
    state = initialize_path_state(points, BOUNDARIES)  # baseline is 1.00
    assert state.market_cursor == Decimal("1.05")
    assert state.trade_anchor == Decimal("1.05")


def test_initial_price_inside_a_gives_in_a() -> None:
    points = build_close_only_path([close_bar(2, "1.05")])
    assert initialize_path_state(points, BOUNDARIES).zone_state is ZoneState.IN_A


def test_initial_price_in_c_gives_in_c() -> None:
    points = build_close_only_path([close_bar(2, "1.15")])
    assert initialize_path_state(points, BOUNDARIES).zone_state is ZoneState.IN_C


def test_initial_price_outside_c_gives_outside_c() -> None:
    points = build_close_only_path([close_bar(2, "1.25")])
    assert initialize_path_state(points, BOUNDARIES).zone_state is ZoneState.OUTSIDE_C


def test_initialization_does_not_process_any_segment() -> None:
    # A path that crosses many levels still initializes purely from points[0].
    points = build_ohlcv_path([BAR_1, BAR_2], OHLCPathMode.AUTO)
    state = initialize_path_state(points, BOUNDARIES)
    assert state == InitialPathState(
        market_cursor=Decimal("1.00"),
        trade_anchor=Decimal("1.00"),
        zone_state=ZoneState.IN_A,
    )


def test_initial_path_state_is_immutable() -> None:
    points = build_close_only_path([close_bar(2, "1.05")])
    state = initialize_path_state(points, BOUNDARIES)
    with pytest.raises(FrozenInstanceError):
        state.market_cursor = Decimal("2.00")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def test_public_imports_work_from_app_engine() -> None:
    import app.engine as engine_pkg

    assert engine_pkg.PathSegment is PathSegment
    assert engine_pkg.InitialPathState is InitialPathState
    assert engine_pkg.InvalidOhlcvBarError is InvalidOhlcvBarError
    assert engine_pkg.OhlcPathModeRequiredError is OhlcPathModeRequiredError
    assert engine_pkg.select_ohlc_midpoints is select_ohlc_midpoints
    assert engine_pkg.build_ohlcv_path is build_ohlcv_path
    assert engine_pkg.build_close_only_path is build_close_only_path
    assert engine_pkg.build_price_path is build_price_path
    assert engine_pkg.build_path_segments is build_path_segments
    assert engine_pkg.initialize_path_state is initialize_path_state


def test_existing_task_6_exports_remain_available() -> None:
    import app.engine as engine_pkg

    assert callable(engine_pkg.build_grid_setup)
    assert callable(engine_pkg.classify_zone)
    assert callable(engine_pkg.round_to_tick)
    assert engine_pkg.MAX_GRID_LEVELS == 10_000
    assert engine_pkg.ValueConfig is not None
    assert engine_pkg.GridSetup is not None


def test_path_modules_have_no_framework_or_trading_dependencies() -> None:
    import app.engine.path
    import app.engine.path_models

    for module in (app.engine.path, app.engine.path_models):
        source = inspect.getsource(module).lower()
        for forbidden in (
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "app.importing",
            "commission",
            "slippage",
            "portfolio",
            "equity",
            "metric",
        ):
            assert forbidden not in source
