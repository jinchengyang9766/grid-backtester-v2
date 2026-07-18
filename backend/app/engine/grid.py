"""Baseline resolution, A/C boundaries, zone classification, and grid generation.

Implements SPEC Sections 7, 8, and 9: every calculation is pure Decimal
arithmetic with no rounding except the explicit tick-normalization step.
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from app.domain.enums import ValueMode, ZoneState
from app.domain.models import Bar
from app.engine.grid_models import GridSetup, TickSizeConfig, ValueConfig, ZoneBoundaries

__all__ = [
    "EmptyDatasetError",
    "GridCollapsesAfterTickRoundingError",
    "GridTooDenseError",
    "InvalidZoneConfigError",
    "MAX_GRID_LEVELS",
    "NonPositiveBaselineError",
    "NonPositiveDistanceError",
    "NonPositiveGridStepError",
    "NonPositiveTickSizeError",
    "build_grid_setup",
    "build_zone_boundaries",
    "canonical_grid_levels",
    "classify_zone",
    "generate_raw_grid_levels",
    "resolve_absolute_value",
    "resolve_baseline",
    "resolve_grid_step",
    "round_to_tick",
]

MAX_GRID_LEVELS = 10_000


class EmptyDatasetError(Exception):
    pass


class NonPositiveBaselineError(Exception):
    pass


class NonPositiveDistanceError(Exception):
    pass


class InvalidZoneConfigError(Exception):
    pass


class NonPositiveGridStepError(Exception):
    pass


class NonPositiveTickSizeError(Exception):
    pass


class GridTooDenseError(Exception):
    def __init__(self, limit: int, attempted_count: int) -> None:
        super().__init__(
            f"Grid generation would produce {attempted_count} levels; the limit is {limit}."
        )
        self.limit = limit
        self.attempted_count = attempted_count


class GridCollapsesAfterTickRoundingError(Exception):
    def __init__(self, raw_count: int, canonical_count: int) -> None:
        super().__init__(
            f"Tick rounding collapsed {raw_count} raw grid levels into "
            f"{canonical_count} canonical levels."
        )
        self.raw_count = raw_count
        self.canonical_count = canonical_count


def resolve_baseline(bars: Sequence[Bar], override: Decimal | None = None) -> Decimal:
    if not bars:
        raise EmptyDatasetError("Cannot resolve a baseline from an empty dataset.")
    baseline = override if override is not None else bars[0].close
    if baseline <= 0:
        raise NonPositiveBaselineError(f"Baseline must be positive; got {baseline}.")
    return baseline


def resolve_absolute_value(baseline: Decimal, config: ValueConfig) -> Decimal:
    if config.mode is ValueMode.FIXED:
        return config.value
    return baseline * config.value


def build_zone_boundaries(
    baseline: Decimal,
    a_distance: ValueConfig,
    c_distance: ValueConfig,
) -> ZoneBoundaries:
    if baseline <= 0:
        raise NonPositiveBaselineError(f"Baseline must be positive; got {baseline}.")
    if a_distance.value <= 0:
        raise NonPositiveDistanceError(f"A distance must be positive; got {a_distance.value}.")
    if c_distance.value <= 0:
        raise NonPositiveDistanceError(f"C distance must be positive; got {c_distance.value}.")

    a_absolute = resolve_absolute_value(baseline, a_distance)
    c_absolute = resolve_absolute_value(baseline, c_distance)
    if c_absolute <= a_absolute:
        raise InvalidZoneConfigError(
            f"C distance ({c_absolute}) must be strictly greater than A distance ({a_absolute})."
        )
    return ZoneBoundaries(
        baseline=baseline,
        a_lower=baseline - a_absolute,
        a_upper=baseline + a_absolute,
        c_lower=baseline - c_absolute,
        c_upper=baseline + c_absolute,
    )


def classify_zone(price: Decimal, boundaries: ZoneBoundaries) -> ZoneState:
    if boundaries.a_lower <= price <= boundaries.a_upper:
        return ZoneState.IN_A
    if boundaries.c_lower <= price <= boundaries.c_upper:
        return ZoneState.IN_C
    return ZoneState.OUTSIDE_C


def resolve_grid_step(baseline: Decimal, grid_step: ValueConfig) -> Decimal:
    if grid_step.value <= 0:
        raise NonPositiveGridStepError(f"Grid step must be positive; got {grid_step.value}.")
    step_size = resolve_absolute_value(baseline, grid_step)
    if step_size <= 0:
        raise NonPositiveGridStepError(f"Resolved step size must be positive; got {step_size}.")
    return step_size


def generate_raw_grid_levels(
    baseline: Decimal,
    a_lower: Decimal,
    a_upper: Decimal,
    step_size: Decimal,
    *,
    max_grid_levels: int = MAX_GRID_LEVELS,
) -> tuple[Decimal, ...]:
    if step_size <= 0:
        raise NonPositiveGridStepError(f"Grid step must be positive; got {step_size}.")

    levels: list[Decimal] = []

    def register(level: Decimal) -> None:
        if len(levels) >= max_grid_levels:
            raise GridTooDenseError(limit=max_grid_levels, attempted_count=len(levels) + 1)
        levels.append(level)

    if a_lower <= baseline <= a_upper:
        register(baseline)

    k = 1
    while True:
        level = baseline + k * step_size
        if level > a_upper:
            break
        if level >= a_lower:
            register(level)
        k += 1

    k = 1
    while True:
        level = baseline - k * step_size
        if level < a_lower:
            break
        if level <= a_upper:
            register(level)
        k += 1

    return tuple(sorted(levels))


def round_to_tick(value: Decimal, tick_size: Decimal) -> Decimal:
    if tick_size <= 0:
        raise NonPositiveTickSizeError(f"Tick size must be positive; got {tick_size}.")
    ticks = (value / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return ticks * tick_size


def canonical_grid_levels(
    baseline: Decimal,
    a_lower: Decimal,
    a_upper: Decimal,
    step_size: Decimal,
    tick_size: TickSizeConfig,
    *,
    max_grid_levels: int = MAX_GRID_LEVELS,
) -> tuple[Decimal, ...]:
    raw_levels = generate_raw_grid_levels(
        baseline, a_lower, a_upper, step_size, max_grid_levels=max_grid_levels
    )
    if not tick_size.enabled:
        return raw_levels

    if tick_size.value is None or tick_size.value <= 0:
        raise NonPositiveTickSizeError(
            f"Tick size must be a positive value when enabled; got {tick_size.value}."
        )

    rounded = [round_to_tick(level, tick_size.value) for level in raw_levels]
    canonical = sorted({level for level in rounded if a_lower <= level <= a_upper})
    if len(canonical) < len(raw_levels):
        raise GridCollapsesAfterTickRoundingError(
            raw_count=len(raw_levels), canonical_count=len(canonical)
        )
    return tuple(canonical)


def build_grid_setup(
    bars: Sequence[Bar],
    *,
    baseline_override: Decimal | None,
    a_distance: ValueConfig,
    c_distance: ValueConfig,
    grid_step: ValueConfig,
    tick_size: TickSizeConfig,
    max_grid_levels: int = MAX_GRID_LEVELS,
) -> GridSetup:
    baseline = resolve_baseline(bars, baseline_override)
    boundaries = build_zone_boundaries(baseline, a_distance, c_distance)
    step_size = resolve_grid_step(baseline, grid_step)
    grid_levels = canonical_grid_levels(
        baseline,
        boundaries.a_lower,
        boundaries.a_upper,
        step_size,
        tick_size,
        max_grid_levels=max_grid_levels,
    )
    return GridSetup(
        baseline=baseline,
        boundaries=boundaries,
        step_size=step_size,
        grid_levels=grid_levels,
    )
