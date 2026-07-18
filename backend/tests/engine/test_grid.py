"""Tests for baseline resolution, A/C boundaries, zone classification, and grids."""

import inspect
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import ValueMode, ZoneState
from app.domain.models import Bar
from app.engine.grid import (
    MAX_GRID_LEVELS,
    EmptyDatasetError,
    GridCollapsesAfterTickRoundingError,
    GridTooDenseError,
    InvalidZoneConfigError,
    NonPositiveBaselineError,
    NonPositiveDistanceError,
    NonPositiveGridStepError,
    NonPositiveTickSizeError,
    build_grid_setup,
    build_zone_boundaries,
    canonical_grid_levels,
    classify_zone,
    generate_raw_grid_levels,
    resolve_absolute_value,
    resolve_baseline,
    resolve_grid_step,
    round_to_tick,
)
from app.engine.grid_models import GridSetup, TickSizeConfig, ValueConfig, ZoneBoundaries


def bar(close: str, day: int = 1) -> Bar:
    return Bar(date=date(2024, 7, day), close=Decimal(close))


def fixed(value: str) -> ValueConfig:
    return ValueConfig(mode=ValueMode.FIXED, value=Decimal(value))


def percent(value: str) -> ValueConfig:
    return ValueConfig(mode=ValueMode.PERCENT, value=Decimal(value))


TICK_DISABLED = TickSizeConfig(enabled=False)

STANDARD_BOUNDARIES = build_zone_boundaries(Decimal("1.00"), fixed("0.10"), fixed("0.20"))


# ---------------------------------------------------------------------------
# Baseline resolution
# ---------------------------------------------------------------------------


def test_default_baseline_uses_first_bar_close() -> None:
    bars = [bar("0.639", 23), bar("0.720", 24)]
    assert resolve_baseline(bars) == Decimal("0.639")


def test_override_is_used_exactly_even_outside_historical_range() -> None:
    bars = [bar("0.639"), bar("0.720", 2)]
    assert resolve_baseline(bars, Decimal("5.00")) == Decimal("5.00")


def test_baseline_is_not_tick_rounded() -> None:
    assert str(resolve_baseline([bar("1.0007")])) == "1.0007"
    assert str(resolve_baseline([bar("1.00")], Decimal("0.9993"))) == "0.9993"


def test_zero_baseline_is_rejected() -> None:
    with pytest.raises(NonPositiveBaselineError):
        resolve_baseline([bar("1.00")], Decimal("0"))


def test_negative_baseline_is_rejected() -> None:
    with pytest.raises(NonPositiveBaselineError):
        resolve_baseline([bar("1.00")], Decimal("-1"))


def test_empty_bars_are_rejected() -> None:
    with pytest.raises(EmptyDatasetError):
        resolve_baseline([])
    with pytest.raises(EmptyDatasetError):
        resolve_baseline([], Decimal("1.00"))


def test_resolve_baseline_does_not_mutate_bars() -> None:
    bars = [bar("0.639")]
    resolve_baseline(bars)
    assert bars == [bar("0.639")]


# ---------------------------------------------------------------------------
# Distance conversion and A/C boundaries
# ---------------------------------------------------------------------------


def test_resolve_absolute_value_fixed_and_percent() -> None:
    assert resolve_absolute_value(Decimal("2.00"), fixed("0.10")) == Decimal("0.10")
    assert resolve_absolute_value(Decimal("2.00"), percent("0.10")) == Decimal("0.20")


def test_fixed_a_and_fixed_c_boundaries() -> None:
    boundaries = build_zone_boundaries(Decimal("1.00"), fixed("0.10"), fixed("0.20"))
    assert boundaries == ZoneBoundaries(
        baseline=Decimal("1.00"),
        a_lower=Decimal("0.90"),
        a_upper=Decimal("1.10"),
        c_lower=Decimal("0.80"),
        c_upper=Decimal("1.20"),
    )


def test_percent_a_and_percent_c_boundaries_use_decimal_fractions() -> None:
    boundaries = build_zone_boundaries(Decimal("100"), percent("0.02"), percent("0.04"))
    assert boundaries.a_lower == Decimal("98")
    assert boundaries.a_upper == Decimal("102")
    assert boundaries.c_lower == Decimal("96")
    assert boundaries.c_upper == Decimal("104")


def test_fixed_a_with_percent_c() -> None:
    boundaries = build_zone_boundaries(Decimal("1.00"), fixed("0.10"), percent("0.20"))
    assert boundaries.a_lower == Decimal("0.90")
    assert boundaries.c_lower == Decimal("0.80")
    assert boundaries.c_upper == Decimal("1.20")


def test_percent_a_with_fixed_c() -> None:
    boundaries = build_zone_boundaries(Decimal("100"), percent("0.02"), fixed("5"))
    assert boundaries.a_upper == Decimal("102")
    assert boundaries.c_upper == Decimal("105")


def test_boundaries_remain_exact_unrounded_decimals() -> None:
    boundaries = build_zone_boundaries(Decimal("1.0007"), fixed("0.0003"), fixed("0.0009"))
    assert str(boundaries.a_lower) == "1.0004"
    assert str(boundaries.a_upper) == "1.0010"
    assert str(boundaries.c_lower) == "0.9998"
    assert str(boundaries.c_upper) == "1.0016"


@pytest.mark.parametrize("distance", ["0", "-0.10"])
def test_non_positive_a_distance_is_rejected(distance: str) -> None:
    with pytest.raises(NonPositiveDistanceError):
        build_zone_boundaries(Decimal("1.00"), fixed(distance), fixed("0.20"))


@pytest.mark.parametrize("distance", ["0", "-0.20"])
def test_non_positive_c_distance_is_rejected(distance: str) -> None:
    with pytest.raises(NonPositiveDistanceError):
        build_zone_boundaries(Decimal("1.00"), fixed("0.10"), fixed(distance))


def test_equal_absolute_distances_are_rejected() -> None:
    with pytest.raises(InvalidZoneConfigError):
        build_zone_boundaries(Decimal("1.00"), fixed("0.10"), percent("0.10"))


def test_smaller_absolute_c_distance_is_rejected() -> None:
    with pytest.raises(InvalidZoneConfigError):
        build_zone_boundaries(Decimal("1.00"), fixed("0.20"), fixed("0.10"))


def test_larger_absolute_c_distance_is_accepted_across_modes() -> None:
    boundaries = build_zone_boundaries(Decimal("1.00"), percent("0.10"), fixed("0.15"))
    assert boundaries.a_upper == Decimal("1.10")
    assert boundaries.c_upper == Decimal("1.15")


def test_build_zone_boundaries_rejects_non_positive_baseline_directly() -> None:
    with pytest.raises(NonPositiveBaselineError):
        build_zone_boundaries(Decimal("0"), fixed("0.10"), fixed("0.20"))


def test_no_invented_lower_boundary_positivity_rule() -> None:
    boundaries = build_zone_boundaries(Decimal("1.00"), fixed("0.90"), fixed("1.50"))
    assert boundaries.a_lower == Decimal("0.10")
    assert boundaries.c_lower == Decimal("-0.50")


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        ("1.00", ZoneState.IN_A),
        ("0.95", ZoneState.IN_A),
        ("0.90", ZoneState.IN_A),  # exactly A lower
        ("1.10", ZoneState.IN_A),  # exactly A upper
        ("0.85", ZoneState.IN_C),  # lower C region
        ("1.15", ZoneState.IN_C),  # upper C region
        ("0.80", ZoneState.IN_C),  # exactly C lower
        ("1.20", ZoneState.IN_C),  # exactly C upper
        ("0.79", ZoneState.OUTSIDE_C),  # below C
        ("1.21", ZoneState.OUTSIDE_C),  # above C
    ],
)
def test_zone_classification(price: str, expected: ZoneState) -> None:
    assert classify_zone(Decimal(price), STANDARD_BOUNDARIES) is expected


# ---------------------------------------------------------------------------
# Grid-step resolution
# ---------------------------------------------------------------------------


def test_fixed_grid_step() -> None:
    assert resolve_grid_step(Decimal("1.00"), fixed("0.03")) == Decimal("0.03")


def test_percent_grid_step_is_arithmetic_from_baseline() -> None:
    assert resolve_grid_step(Decimal("2.00"), percent("0.10")) == Decimal("0.20")


def test_percent_grid_step_has_no_geometric_compounding() -> None:
    step_size = resolve_grid_step(Decimal("1.00"), percent("0.10"))
    levels = generate_raw_grid_levels(Decimal("1.00"), Decimal("0.80"), Decimal("1.20"), step_size)
    assert levels == (
        Decimal("0.80"),
        Decimal("0.90"),
        Decimal("1.00"),
        Decimal("1.10"),
        Decimal("1.20"),
    )
    assert Decimal("1.21") not in levels


@pytest.mark.parametrize("value", ["0", "-0.03"])
def test_non_positive_grid_step_is_rejected(value: str) -> None:
    with pytest.raises(NonPositiveGridStepError):
        resolve_grid_step(Decimal("1.00"), fixed(value))


def test_percent_step_resolving_non_positive_is_rejected() -> None:
    with pytest.raises(NonPositiveGridStepError):
        resolve_grid_step(Decimal("-1.00"), percent("0.10"))


# ---------------------------------------------------------------------------
# Raw grid generation
# ---------------------------------------------------------------------------


def test_raw_grid_includes_baseline_and_sorts_ascending() -> None:
    levels = generate_raw_grid_levels(
        Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("0.03")
    )
    assert Decimal("1.00") in levels
    assert list(levels) == sorted(levels)


def test_non_divisible_distance_does_not_force_boundaries_onto_grid() -> None:
    levels = generate_raw_grid_levels(
        Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("0.03")
    )
    assert levels == (
        Decimal("0.91"),
        Decimal("0.94"),
        Decimal("0.97"),
        Decimal("1.00"),
        Decimal("1.03"),
        Decimal("1.06"),
        Decimal("1.09"),
    )
    assert Decimal("0.90") not in levels
    assert Decimal("1.10") not in levels


def test_exact_boundary_level_is_included_when_naturally_reached() -> None:
    levels = generate_raw_grid_levels(
        Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("0.05")
    )
    assert levels == (
        Decimal("0.90"),
        Decimal("0.95"),
        Decimal("1.00"),
        Decimal("1.05"),
        Decimal("1.10"),
    )


def test_full_decimal_precision_is_retained() -> None:
    levels = generate_raw_grid_levels(
        Decimal("1.00"), Decimal("0.99"), Decimal("1.01"), Decimal("0.005")
    )
    assert [str(level) for level in levels] == ["0.990", "0.995", "1.00", "1.005", "1.010"]


def test_zero_or_negative_step_raises_in_generation() -> None:
    with pytest.raises(NonPositiveGridStepError):
        generate_raw_grid_levels(Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("0"))
    with pytest.raises(NonPositiveGridStepError):
        generate_raw_grid_levels(
            Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("-0.01")
        )


def test_exactly_max_grid_levels_is_allowed_and_cap_includes_baseline() -> None:
    levels = generate_raw_grid_levels(
        Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("0.01"), max_grid_levels=21
    )
    assert len(levels) == 21
    assert Decimal("1.00") in levels


def test_one_level_beyond_the_cap_raises_grid_too_dense() -> None:
    with pytest.raises(GridTooDenseError) as exc_info:
        generate_raw_grid_levels(
            Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("0.01"), max_grid_levels=20
        )
    assert exc_info.value.limit == 20
    assert exc_info.value.attempted_count == 21


def test_default_cap_constant_is_ten_thousand() -> None:
    assert MAX_GRID_LEVELS == 10_000


def test_cap_is_enforced_before_tick_rounding() -> None:
    with pytest.raises(GridTooDenseError):
        canonical_grid_levels(
            Decimal("1.00"),
            Decimal("0.90"),
            Decimal("1.10"),
            Decimal("0.01"),
            TickSizeConfig(enabled=True, value=Decimal("0.5")),
            max_grid_levels=5,
        )


# ---------------------------------------------------------------------------
# Tick rounding
# ---------------------------------------------------------------------------


def test_below_half_rounds_down() -> None:
    assert round_to_tick(Decimal("1.014"), Decimal("0.01")) == Decimal("1.01")


def test_exact_half_rounds_up() -> None:
    assert round_to_tick(Decimal("1.015"), Decimal("0.01")) == Decimal("1.02")


def test_value_already_on_tick_is_unchanged() -> None:
    assert round_to_tick(Decimal("1.02"), Decimal("0.01")) == Decimal("1.02")


def test_non_power_of_ten_tick_size() -> None:
    assert round_to_tick(Decimal("1.13"), Decimal("0.25")) == Decimal("1.25")
    assert round_to_tick(Decimal("1.10"), Decimal("0.25")) == Decimal("1.00")


def test_output_remains_decimal() -> None:
    result = round_to_tick(Decimal("1.014"), Decimal("0.01"))
    assert type(result) is Decimal


@pytest.mark.parametrize("tick", ["0", "-0.01"])
def test_non_positive_tick_size_is_rejected(tick: str) -> None:
    with pytest.raises(NonPositiveTickSizeError):
        round_to_tick(Decimal("1.00"), Decimal(tick))


# ---------------------------------------------------------------------------
# Canonical grid levels
# ---------------------------------------------------------------------------


def test_disabled_tick_returns_raw_levels_exactly_and_allows_none_value() -> None:
    raw = generate_raw_grid_levels(
        Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("0.03")
    )
    canonical = canonical_grid_levels(
        Decimal("1.00"),
        Decimal("0.90"),
        Decimal("1.10"),
        Decimal("0.03"),
        TickSizeConfig(enabled=False, value=None),
    )
    assert canonical == raw


@pytest.mark.parametrize("value", [None, "0", "-0.01"])
def test_enabled_tick_requires_positive_value(value: str | None) -> None:
    tick = TickSizeConfig(enabled=True, value=None if value is None else Decimal(value))
    with pytest.raises(NonPositiveTickSizeError):
        canonical_grid_levels(
            Decimal("1.00"), Decimal("0.90"), Decimal("1.10"), Decimal("0.03"), tick
        )


def test_enabled_tick_returns_rounded_levels_sorted_never_raw() -> None:
    canonical = canonical_grid_levels(
        Decimal("1.000"),
        Decimal("0.976"),
        Decimal("1.024"),
        Decimal("0.012"),
        TickSizeConfig(enabled=True, value=Decimal("0.010")),
    )
    assert canonical == (
        Decimal("0.98"),
        Decimal("0.99"),
        Decimal("1.00"),
        Decimal("1.01"),
        Decimal("1.02"),
    )
    raw = generate_raw_grid_levels(
        Decimal("1.000"), Decimal("0.976"), Decimal("1.024"), Decimal("0.012")
    )
    assert canonical != raw
    assert all(Decimal("0.976") <= level <= Decimal("1.024") for level in canonical)


def test_duplicate_rounded_ticks_cause_collapse_rejection() -> None:
    # Raw levels 0.988..1.012 step 0.004 all stay inside [0.985, 1.015] after
    # rounding to 0.01 ticks, so the only collapse cause here is deduplication:
    # 7 raw levels round to just {0.99, 1.00, 1.01}.
    with pytest.raises(GridCollapsesAfterTickRoundingError) as exc_info:
        canonical_grid_levels(
            Decimal("1.000"),
            Decimal("0.985"),
            Decimal("1.015"),
            Decimal("0.004"),
            TickSizeConfig(enabled=True, value=Decimal("0.01")),
        )
    assert exc_info.value.raw_count == 7
    assert exc_info.value.canonical_count == 3


def test_rounded_level_outside_unrounded_a_boundary_causes_collapse_rejection() -> None:
    with pytest.raises(GridCollapsesAfterTickRoundingError) as exc_info:
        canonical_grid_levels(
            Decimal("1.000"),
            Decimal("0.985"),
            Decimal("1.014"),
            Decimal("0.013"),
            TickSizeConfig(enabled=True, value=Decimal("0.005")),
        )
    assert exc_info.value.raw_count == 3
    assert exc_info.value.canonical_count == 2


# ---------------------------------------------------------------------------
# Full setup integration
# ---------------------------------------------------------------------------


def test_build_grid_setup_with_mixed_modes() -> None:
    setup = build_grid_setup(
        [bar("1.00")],
        baseline_override=None,
        a_distance=fixed("0.10"),
        c_distance=percent("0.20"),
        grid_step=fixed("0.03"),
        tick_size=TICK_DISABLED,
    )
    assert setup.baseline == Decimal("1.00")
    assert setup.boundaries == ZoneBoundaries(
        baseline=Decimal("1.00"),
        a_lower=Decimal("0.90"),
        a_upper=Decimal("1.10"),
        c_lower=Decimal("0.80"),
        c_upper=Decimal("1.20"),
    )
    assert setup.step_size == Decimal("0.03")
    assert setup.grid_levels == (
        Decimal("0.91"),
        Decimal("0.94"),
        Decimal("0.97"),
        Decimal("1.00"),
        Decimal("1.03"),
        Decimal("1.06"),
        Decimal("1.09"),
    )


def test_build_grid_setup_with_tick_enabled_never_rounds_boundaries() -> None:
    setup = build_grid_setup(
        [bar("1.000")],
        baseline_override=None,
        a_distance=fixed("0.024"),
        c_distance=fixed("0.050"),
        grid_step=fixed("0.012"),
        tick_size=TickSizeConfig(enabled=True, value=Decimal("0.010")),
    )
    assert str(setup.boundaries.a_lower) == "0.976"
    assert str(setup.boundaries.a_upper) == "1.024"
    assert setup.grid_levels == (
        Decimal("0.98"),
        Decimal("0.99"),
        Decimal("1.00"),
        Decimal("1.01"),
        Decimal("1.02"),
    )


def test_build_grid_setup_uses_override_and_percent_step() -> None:
    setup = build_grid_setup(
        [bar("0.639")],
        baseline_override=Decimal("100"),
        a_distance=percent("0.02"),
        c_distance=fixed("5"),
        grid_step=percent("0.01"),
        tick_size=TICK_DISABLED,
    )
    assert setup.baseline == Decimal("100")
    assert setup.step_size == Decimal("1.00")
    assert setup.grid_levels == (
        Decimal("98"),
        Decimal("99"),
        Decimal("100"),
        Decimal("101"),
        Decimal("102"),
    )


def test_grid_setup_is_immutable_and_levels_are_a_tuple() -> None:
    setup = build_grid_setup(
        [bar("1.00")],
        baseline_override=None,
        a_distance=fixed("0.10"),
        c_distance=fixed("0.20"),
        grid_step=fixed("0.05"),
        tick_size=TICK_DISABLED,
    )
    assert isinstance(setup, GridSetup)
    assert isinstance(setup.grid_levels, tuple)
    with pytest.raises(FrozenInstanceError):
        setup.baseline = Decimal("2.00")  # type: ignore[misc]


def test_public_imports_work_from_app_engine() -> None:
    import app.engine as engine_pkg

    assert engine_pkg.build_grid_setup is build_grid_setup
    assert engine_pkg.build_zone_boundaries is build_zone_boundaries
    assert engine_pkg.canonical_grid_levels is canonical_grid_levels
    assert engine_pkg.classify_zone is classify_zone
    assert engine_pkg.generate_raw_grid_levels is generate_raw_grid_levels
    assert engine_pkg.resolve_absolute_value is resolve_absolute_value
    assert engine_pkg.resolve_baseline is resolve_baseline
    assert engine_pkg.resolve_grid_step is resolve_grid_step
    assert engine_pkg.round_to_tick is round_to_tick
    assert engine_pkg.MAX_GRID_LEVELS == MAX_GRID_LEVELS
    assert engine_pkg.ValueConfig is ValueConfig
    assert engine_pkg.TickSizeConfig is TickSizeConfig
    assert engine_pkg.ZoneBoundaries is ZoneBoundaries
    assert engine_pkg.GridSetup is GridSetup
    assert engine_pkg.EmptyDatasetError is EmptyDatasetError
    assert engine_pkg.GridTooDenseError is GridTooDenseError


def test_engine_has_no_framework_or_importing_dependency() -> None:
    import app.engine
    import app.engine.grid
    import app.engine.grid_models

    for module in (app.engine, app.engine.grid, app.engine.grid_models):
        source = inspect.getsource(module)
        for forbidden in ("fastapi", "pydantic", "sqlalchemy", "importing"):
            assert forbidden not in source.lower()
