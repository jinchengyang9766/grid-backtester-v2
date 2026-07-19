"""Backtest creation endpoint (SPEC Section 25.3): synchronous execution.

The route only wires authentication, the request schema, and the service —
no engine formula, persistence rule, or metric computation lives here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.schemas.backtests import BacktestCreateRequest, BacktestCreateResponse
from app.auth.dependencies import get_current_user
from app.backtests.service import create_backtest
from app.db.models import BacktestRun, User
from app.db.session import get_db_session

__all__ = ["router"]

router = APIRouter(prefix="/api/backtests", tags=["backtests"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BacktestCreateResponse)
def create_backtest_endpoint(
    payload: BacktestCreateRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> BacktestRun:
    return create_backtest(session, current_user_id=current_user.id, request=payload)
