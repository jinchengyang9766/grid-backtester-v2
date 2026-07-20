"""Read-only projections of the normalized backtest result series (SPEC 25.3).

Every event-scoped projection joins through BacktestEvent — the sole owner
of date/event_sequence/market_price — preserving the single global
chronological order. Nothing here commits, mutates, or recomputes values.
"""

import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BacktestEvent, DailyEquity, EventEquity, Trade, ZoneEventRecord

__all__ = [
    "load_daily_equity_projection",
    "load_event_equity_projection",
    "load_trade_projection",
    "load_zone_event_projection",
]


def load_trade_projection(
    session: Session, *, backtest_run_id: int, limit: int | None = None
) -> list[tuple[Trade, datetime.date, int]]:
    """All trades of a run, or only the first ``limit`` by event sequence.

    ``limit`` lets a bounded consumer (the PDF report's first-20-trades
    table, SPEC 32) fetch just what it renders in the same single query,
    instead of loading the whole history and slicing it. ``None`` keeps the
    original full-series behaviour.
    """
    statement = (
        select(Trade, BacktestEvent.date, BacktestEvent.event_sequence)
        .join(BacktestEvent, Trade.event_id == BacktestEvent.id)
        .where(BacktestEvent.backtest_run_id == backtest_run_id)
        .order_by(BacktestEvent.event_sequence.asc(), Trade.id.asc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    rows = session.execute(statement).all()
    return [(row[0], row[1], row[2]) for row in rows]


def load_zone_event_projection(
    session: Session, *, backtest_run_id: int
) -> list[tuple[ZoneEventRecord, datetime.date, int]]:
    rows = session.execute(
        select(ZoneEventRecord, BacktestEvent.date, BacktestEvent.event_sequence)
        .join(BacktestEvent, ZoneEventRecord.event_id == BacktestEvent.id)
        .where(BacktestEvent.backtest_run_id == backtest_run_id)
        .order_by(BacktestEvent.event_sequence.asc(), ZoneEventRecord.id.asc())
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


def load_daily_equity_projection(session: Session, *, backtest_run_id: int) -> list[DailyEquity]:
    return list(
        session.execute(
            select(DailyEquity)
            .where(DailyEquity.backtest_run_id == backtest_run_id)
            .order_by(DailyEquity.date.asc(), DailyEquity.id.asc())
        ).scalars()
    )


def load_event_equity_projection(
    session: Session, *, backtest_run_id: int
) -> list[tuple[EventEquity, datetime.date, int, Decimal]]:
    rows = session.execute(
        select(
            EventEquity,
            BacktestEvent.date,
            BacktestEvent.event_sequence,
            BacktestEvent.market_price,
        )
        .join(BacktestEvent, EventEquity.event_id == BacktestEvent.id)
        .where(BacktestEvent.backtest_run_id == backtest_run_id)
        .order_by(BacktestEvent.event_sequence.asc(), EventEquity.id.asc())
    ).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows]
