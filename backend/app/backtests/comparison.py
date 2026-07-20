"""Read-only backtest comparison service (SPEC Sections 25.3, 30).

All-or-nothing and request-order preserving: one ownership-scoped query loads
every requested run; if any id is missing or foreign the whole request is a
BACKTEST_NOT_FOUND, never revealing which id failed. Never commits, never runs
the engine, never loads child series. Stored result_metrics is returned
verbatim.
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.models import BacktestRun

__all__ = ["compare_owned_backtests"]


def compare_owned_backtests(
    session: Session, *, current_user_id: int, backtest_ids: Sequence[int]
) -> list[BacktestRun]:
    """Return the owned runs for backtest_ids in request order (all-or-nothing)."""
    runs = (
        session.execute(
            select(BacktestRun).where(
                BacktestRun.user_id == current_user_id,
                BacktestRun.id.in_(set(backtest_ids)),
            )
        )
        .scalars()
        .all()
    )
    runs_by_id = {run.id: run for run in runs}
    if len(runs_by_id) != len(set(backtest_ids)):
        raise ApiError(404, "BACKTEST_NOT_FOUND", "Backtest not found.")
    return [runs_by_id[backtest_id] for backtest_id in backtest_ids]
