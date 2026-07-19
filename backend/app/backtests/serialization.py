"""Canonical JSON-safe serialization for backtest configuration and results.

Every Decimal becomes a plain fixed-point string (never scientific notation,
never float), enums become their values, dates become ISO strings, and
dataclasses serialize recursively. Unsupported objects fail loudly instead
of silently degrading to repr().
"""

import dataclasses
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from app.engine import BacktestResult

__all__ = ["build_result_metrics", "json_safe", "plain_decimal"]

JsonValue = None | bool | int | str | list["JsonValue"] | dict[str, "JsonValue"]


def plain_decimal(value: Decimal) -> str:
    """Fixed-point notation with no scientific notation and no float round-trip."""
    return format(value, "f")


def json_safe(value: object) -> JsonValue:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):  # before str: StrEnum members are str subclasses
        member_value = value.value
        if not isinstance(member_value, str | int):
            raise TypeError(f"Unsupported enum value type: {type(member_value).__name__}")
        return member_value
    if isinstance(value, int | str):
        return value
    if isinstance(value, Decimal):
        return plain_decimal(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: json_safe(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            safe_key = json_safe(key)
            if not isinstance(safe_key, str):
                raise TypeError(f"Unsupported mapping key type: {type(key).__name__}")
            result[safe_key] = json_safe(item)
        return result
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    raise TypeError(f"Unsupported type for JSON serialization: {type(value).__name__}")


def build_result_metrics(result: BacktestResult) -> dict[str, JsonValue]:
    """Deterministic result_metrics projection for a COMPLETED run.

    Engine dataclass field names are preserved; grid levels are exposed at
    the top-level ``grid_levels`` key (the dashboard contract). The
    normalized Trade/ZoneEvent/DailyEquity/EventEquity series are NOT
    duplicated here; benchmark daily points are included because no
    normalized benchmark table exists.
    """
    boundaries = result.grid_setup.boundaries
    return {
        "initial_equity": plain_decimal(result.initial_equity),
        "baseline": plain_decimal(result.grid_setup.baseline),
        "a_lower": plain_decimal(boundaries.a_lower),
        "a_upper": plain_decimal(boundaries.a_upper),
        "c_lower": plain_decimal(boundaries.c_lower),
        "c_upper": plain_decimal(boundaries.c_upper),
        "grid_step": plain_decimal(result.grid_setup.step_size),
        "grid_levels": [plain_decimal(level) for level in result.grid_setup.grid_levels],
        "metrics": json_safe(result.metrics),
        "benchmark1": json_safe(result.benchmark1),
        "benchmark2": json_safe(result.benchmark2),
        "final_state": json_safe(result.final_state),
    }
