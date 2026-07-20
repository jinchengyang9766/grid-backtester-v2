"""Backtest endpoints (SPEC Sections 25.3, 30): create, list, detail,
rename, delete.

Routes only wire authentication, schemas, and services — no engine
formula, persistence rule, or metric computation lives here.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas.backtests import (
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestListResponse,
    DailyEquityProjectionModel,
    EventEquityProjectionModel,
    TradeProjectionModel,
    ZoneEventProjectionModel,
)
from app.auth.dependencies import get_current_user
from app.backtests.history import (
    BACKTEST_STATUSES,
    delete_owned_backtest,
    get_owned_backtest,
    list_owned_backtests,
    rename_owned_backtest,
)
from app.backtests.projections import (
    load_daily_equity_projection,
    load_event_equity_projection,
    load_trade_projection,
    load_zone_event_projection,
)
from app.backtests.service import create_backtest
from app.db.models import BacktestRun, User
from app.db.session import get_db_session

__all__ = ["router"]

router = APIRouter(prefix="/api/backtests", tags=["backtests"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[Session, Depends(get_db_session)]

_INCLUDE_VALUES = ("trades", "zone_events", "daily_equity", "event_equity")


def _backtest_not_found() -> ApiError:
    # Identical for missing, wrong-owner, and already-deleted runs.
    return ApiError(status.HTTP_404_NOT_FOUND, "BACKTEST_NOT_FOUND", "Backtest not found.")


def _parse_include(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    requested = {token.strip() for token in raw.split(",") if token.strip()}
    invalid = sorted(requested - set(_INCLUDE_VALUES))
    if invalid:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Unknown include value(s).",
            {"invalid_includes": invalid, "allowed": list(_INCLUDE_VALUES)},
        )
    return requested


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BacktestCreateResponse)
def create_backtest_endpoint(
    payload: BacktestCreateRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> BacktestRun:
    return create_backtest(session, current_user_id=current_user.id, request=payload)


@router.get("", response_model=BacktestListResponse)
def list_backtests_endpoint(
    session: SessionDep,
    current_user: CurrentUserDep,
    search: str | None = None,
    dataset_id: int | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BacktestListResponse:
    if status_filter is not None and status_filter not in BACKTEST_STATUSES:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Invalid status filter.",
            {"field": "status", "allowed": list(BACKTEST_STATUSES)},
        )
    page = list_owned_backtests(
        session,
        owner_user_id=current_user.id,
        search=search,
        dataset_id=dataset_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return BacktestListResponse(
        items=[BacktestListItem.from_run(run, dataset_name) for run, dataset_name in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{backtest_id}",
    response_model=BacktestDetailResponse,
    response_model_exclude_unset=True,
)
def get_backtest_endpoint(
    backtest_id: int,
    session: SessionDep,
    current_user: CurrentUserDep,
    include: str | None = None,
) -> BacktestDetailResponse:
    requested = _parse_include(include)
    run = get_owned_backtest(session, backtest_id=backtest_id, owner_user_id=current_user.id)
    if run is None:
        raise _backtest_not_found()
    fields = BacktestDetailResponse.base_fields_from_run(run)
    if "trades" in requested:
        fields["trades"] = [
            TradeProjectionModel.from_row(trade, event_date, sequence)
            for trade, event_date, sequence in load_trade_projection(
                session, backtest_run_id=run.id
            )
        ]
    if "zone_events" in requested:
        fields["zone_events"] = [
            ZoneEventProjectionModel.from_row(zone_event, event_date, sequence)
            for zone_event, event_date, sequence in load_zone_event_projection(
                session, backtest_run_id=run.id
            )
        ]
    if "daily_equity" in requested:
        fields["daily_equity"] = [
            DailyEquityProjectionModel.from_row(row)
            for row in load_daily_equity_projection(session, backtest_run_id=run.id)
        ]
    if "event_equity" in requested:
        fields["event_equity"] = [
            EventEquityProjectionModel.from_row(row, event_date, sequence, market_price)
            for row, event_date, sequence, market_price in load_event_equity_projection(
                session, backtest_run_id=run.id
            )
        ]
    return BacktestDetailResponse(**fields)


@router.patch(
    "/{backtest_id}",
    response_model=BacktestDetailResponse,
    response_model_exclude_unset=True,
)
def rename_backtest_endpoint(
    backtest_id: int,
    payload: Annotated[dict[str, Any], Body()],
    session: SessionDep,
    current_user: CurrentUserDep,
) -> BacktestDetailResponse:
    # Rename-only: any other field is a deliberate IMMUTABLE_FIELD error,
    # never a generic extra_forbidden VALIDATION_ERROR.
    immutable = sorted(set(payload) - {"name"})
    if immutable:
        raise ApiError(
            422,
            "IMMUTABLE_FIELD",
            "Only 'name' may be modified.",
            {"fields": immutable},
        )
    raw_name = payload.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "name must contain at least one non-whitespace character.",
            {"field": "name"},
        )
    run = rename_owned_backtest(
        session,
        backtest_id=backtest_id,
        owner_user_id=current_user.id,
        name=raw_name.strip(),
    )
    if run is None:
        raise _backtest_not_found()
    return BacktestDetailResponse(**BacktestDetailResponse.base_fields_from_run(run))


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backtest_endpoint(
    backtest_id: int,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> None:
    if not delete_owned_backtest(session, backtest_id=backtest_id, owner_user_id=current_user.id):
        raise _backtest_not_found()
