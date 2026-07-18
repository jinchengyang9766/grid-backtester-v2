"""Immutable value objects for baseline, zone-boundary, and grid configuration."""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import ValueMode

__all__ = [
    "GridSetup",
    "TickSizeConfig",
    "ValueConfig",
    "ZoneBoundaries",
]


@dataclass(frozen=True, slots=True)
class ValueConfig:
    """A Percent-or-Fixed amount; Percent values are decimal fractions (0.02 = 2%)."""

    mode: ValueMode
    value: Decimal


@dataclass(frozen=True, slots=True)
class TickSizeConfig:
    enabled: bool
    value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ZoneBoundaries:
    baseline: Decimal
    a_lower: Decimal
    a_upper: Decimal
    c_lower: Decimal
    c_upper: Decimal


@dataclass(frozen=True, slots=True)
class GridSetup:
    baseline: Decimal
    boundaries: ZoneBoundaries
    step_size: Decimal
    grid_levels: tuple[Decimal, ...]
