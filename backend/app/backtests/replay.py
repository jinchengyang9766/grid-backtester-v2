"""Rerun and duplicate-and-execute services (SPEC Sections 25.3, 30).

Both reconstruct the source run's stored canonical configuration back through
the strict BacktestConfigurationInput schema (never trusting raw stored JSON),
then reuse the existing synchronous create_backtest path so ownership,
PriceBar loading, engine execution, exception mapping, and persistence are
never re-implemented here.
"""

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas.backtests import (
    BacktestConfigurationInput,
    BacktestCreateRequest,
)
from app.backtests.history import get_owned_backtest
from app.backtests.service import create_backtest
from app.db.models import BacktestRun

__all__ = [
    "configuration_request_from_stored",
    "deep_merge_configuration",
    "duplicate_backtest",
    "rerun_backtest",
]


def _backtest_not_found() -> ApiError:
    return ApiError(404, "BACKTEST_NOT_FOUND", "Backtest not found.")


def _stored_configuration_invalid() -> ApiError:
    # A persisted-data problem: never leak the raw configuration or the
    # Pydantic error internals to the client.
    return ApiError(
        422,
        "VALIDATION_ERROR",
        "Stored backtest configuration is invalid.",
        {"field": "configuration", "reason": "Stored backtest configuration is invalid."},
    )


def configuration_request_from_stored(
    stored_configuration: Mapping[str, object],
) -> BacktestConfigurationInput:
    """Validate stored canonical JSON back into the strict request schema.

    Decimal strings become Decimal and enum strings are checked here; unknown
    or missing keys and invalid slippage shapes are rejected. The stored
    mapping is never mutated.
    """
    try:
        return BacktestConfigurationInput.model_validate(dict(stored_configuration))
    except ValidationError as error:
        raise _stored_configuration_invalid() from error


def deep_merge_configuration(
    base: Mapping[str, object], overrides: Mapping[str, object]
) -> dict[str, object]:
    """Recursively merge overrides onto base without mutating either.

    Mapping onto mapping merges recursively; any non-mapping override value
    (including null and lists) replaces the base value wholesale. Untouched
    sibling and nested fields are preserved.
    """
    merged: dict[str, object] = deepcopy(dict(base))
    for key, override_value in overrides.items():
        base_value = merged.get(key)
        if (
            key in merged
            and isinstance(base_value, Mapping)
            and isinstance(override_value, Mapping)
        ):
            merged[key] = deep_merge_configuration(base_value, override_value)
        else:
            merged[key] = deepcopy(override_value)
    return merged


def rerun_backtest(
    session: Session,
    *,
    current_user_id: int,
    backtest_id: int,
    now: datetime | None = None,
) -> BacktestRun:
    """Execute the source run's exact stored configuration as a new run."""
    source = get_owned_backtest(session, backtest_id=backtest_id, owner_user_id=current_user_id)
    if source is None:
        raise _backtest_not_found()
    configuration = configuration_request_from_stored(source.configuration)
    request = BacktestCreateRequest(dataset_id=source.dataset_id, configuration=configuration)
    return create_backtest(session, current_user_id=current_user_id, request=request, now=now)


def duplicate_backtest(
    session: Session,
    *,
    current_user_id: int,
    backtest_id: int,
    configuration_overrides: Mapping[str, object],
    now: datetime | None = None,
) -> BacktestRun:
    """Deep-merge overrides onto the source configuration and execute anew."""
    source = get_owned_backtest(session, backtest_id=backtest_id, owner_user_id=current_user_id)
    if source is None:
        raise _backtest_not_found()
    merged = deep_merge_configuration(source.configuration, configuration_overrides)
    configuration = configuration_request_from_stored(merged)
    request = BacktestCreateRequest(dataset_id=source.dataset_id, configuration=configuration)
    return create_backtest(session, current_user_id=current_user_id, request=request, now=now)
