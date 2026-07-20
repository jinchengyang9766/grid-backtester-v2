"""Owned-backtest history services: list, detail, rename, delete (SPEC 25.3, 30).

Ownership filtering lives inside every SQL query, so a non-owner's run never
enters application memory. Reads never commit; rename/delete own their
single commit. Deletion relies entirely on the database ON DELETE CASCADE
chain — no child rows are ever loaded or deleted manually.
"""

from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import BacktestRun, Dataset

__all__ = [
    "BACKTEST_STATUSES",
    "BacktestListPage",
    "delete_owned_backtest",
    "get_owned_backtest",
    "list_owned_backtests",
    "rename_owned_backtest",
]

BACKTEST_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED")


@dataclass(frozen=True, slots=True)
class BacktestListPage:
    items: list[tuple[BacktestRun, str]]  # (run, dataset_name)
    total: int
    limit: int
    offset: int


def _list_predicates(
    *,
    owner_user_id: int,
    search: str | None,
    dataset_id: int | None,
    status: str | None,
) -> list[ColumnElement[bool]]:
    predicates: list[ColumnElement[bool]] = [BacktestRun.user_id == owner_user_id]
    if search is not None:
        trimmed = search.strip()
        if trimmed:
            # Bound parameter, case-insensitive substring on the run name.
            predicates.append(BacktestRun.name.ilike(f"%{trimmed}%"))
    if dataset_id is not None:
        predicates.append(BacktestRun.dataset_id == dataset_id)
    if status is not None:
        predicates.append(BacktestRun.status == status)
    return predicates


def list_owned_backtests(
    session: Session,
    *,
    owner_user_id: int,
    search: str | None = None,
    dataset_id: int | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> BacktestListPage:
    """One filtered count query plus one paginated item query; never commits."""
    predicates = _list_predicates(
        owner_user_id=owner_user_id, search=search, dataset_id=dataset_id, status=status
    )
    total = session.execute(
        select(func.count()).select_from(BacktestRun).where(*predicates)
    ).scalar_one()
    rows = session.execute(
        select(BacktestRun, Dataset.name)
        .join(Dataset, BacktestRun.dataset_id == Dataset.id)
        .where(*predicates)
        .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [(row[0], row[1]) for row in rows]
    return BacktestListPage(items=items, total=total, limit=limit, offset=offset)


def get_owned_backtest(
    session: Session, *, backtest_id: int, owner_user_id: int
) -> BacktestRun | None:
    """The run only when it exists AND belongs to the user; Dataset eager-joined."""
    return session.execute(
        select(BacktestRun)
        .options(joinedload(BacktestRun.dataset))
        .where(BacktestRun.id == backtest_id, BacktestRun.user_id == owner_user_id)
    ).scalar_one_or_none()


def rename_owned_backtest(
    session: Session, *, backtest_id: int, owner_user_id: int, name: str
) -> BacktestRun | None:
    """Set only BacktestRun.name (already validated/trimmed); one commit."""
    run = get_owned_backtest(session, backtest_id=backtest_id, owner_user_id=owner_user_id)
    if run is None:
        return None
    run.name = name
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(run)
    return run


def delete_owned_backtest(session: Session, *, backtest_id: int, owner_user_id: int) -> bool:
    """Delete one owned run; children go via database CASCADE. One commit."""
    run = get_owned_backtest(session, backtest_id=backtest_id, owner_user_id=owner_user_id)
    if run is None:
        return False
    session.delete(run)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return True
