"""Backtest export endpoints (SPEC Sections 25.4, 31).

Three read-only downloads per owned run: the Trade Log CSV, the Daily Close
Equity CSV, and the Complete Result JSON. Routes only authenticate, resolve
the owned run, call an export builder, and return the response -- no row
construction, serialization rule, or metric logic lives here.

``report.pdf`` (SPEC 32) is deliberately not registered yet.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.dependencies import get_current_user
from app.backtests.exports import (
    build_complete_result_document,
    build_daily_equity_csv,
    build_trades_csv,
)
from app.backtests.history import get_owned_backtest
from app.db.models import BacktestRun, User
from app.db.session import get_db_session

__all__ = ["router"]

router = APIRouter(prefix="/api/backtests", tags=["backtest-exports"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[Session, Depends(get_db_session)]

# Actual responses carry the charset; the class-level media type is what
# OpenAPI advertises for the route.
_CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


class CsvResponse(Response):
    media_type = "text/csv"


class JsonDownloadResponse(Response):
    media_type = "application/json"


def _backtest_not_found() -> ApiError:
    # Byte-identical for missing, wrong-owner, and already-deleted runs, and
    # identical to every other backtest route's 404 (SPEC 24.4): existence
    # and ownership are never leaked.
    return ApiError(status.HTTP_404_NOT_FOUND, "BACKTEST_NOT_FOUND", "Backtest not found.")


def _load_owned_run(session: Session, *, backtest_id: int, user: User) -> BacktestRun:
    run = get_owned_backtest(session, backtest_id=backtest_id, owner_user_id=user.id)
    if run is None:
        raise _backtest_not_found()
    return run


def _attachment_headers(filename: str) -> dict[str, str]:
    """Deterministic ASCII filename built from the numeric run id only.

    BacktestRun.name is user-editable and may contain Unicode, quotes,
    control characters, or path separators, so it never reaches a filename.
    """
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.get(
    "/{backtest_id}/exports/trades.csv",
    response_class=CsvResponse,
    responses={404: {"description": "Not found or not owned"}},
)
def export_trades_csv_endpoint(
    backtest_id: int,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> Response:
    run = _load_owned_run(session, backtest_id=backtest_id, user=current_user)
    content = build_trades_csv(session, backtest_run_id=run.id)
    return Response(
        content=content,
        media_type=_CSV_MEDIA_TYPE,
        headers=_attachment_headers(f"backtest-{run.id}-trades.csv"),
    )


@router.get(
    "/{backtest_id}/exports/equity.csv",
    response_class=CsvResponse,
    responses={404: {"description": "Not found or not owned"}},
)
def export_equity_csv_endpoint(
    backtest_id: int,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> Response:
    run = _load_owned_run(session, backtest_id=backtest_id, user=current_user)
    content = build_daily_equity_csv(session, backtest_run_id=run.id)
    return Response(
        content=content,
        media_type=_CSV_MEDIA_TYPE,
        headers=_attachment_headers(f"backtest-{run.id}-equity.csv"),
    )


@router.get(
    "/{backtest_id}/exports/result.json",
    response_class=JsonDownloadResponse,
    responses={404: {"description": "Not found or not owned"}},
)
def export_result_json_endpoint(
    backtest_id: int,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> Response:
    run = _load_owned_run(session, backtest_id=backtest_id, user=current_user)
    document = build_complete_result_document(run)
    # ensure_ascii=False keeps Chinese security metadata as real UTF-8 bytes;
    # insertion order is preserved so repeated requests are byte-identical.
    return Response(
        content=json.dumps(document, ensure_ascii=False),
        media_type="application/json",
        headers=_attachment_headers(f"backtest-{run.id}-result.json"),
    )
