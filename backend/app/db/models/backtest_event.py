"""BacktestEvent persistence model — the global event-ordering backbone
(SPEC Section 23.5).

Every Trade and ZoneEvent (and each one's EventEquity row) hangs off
exactly one row here via event_id; UNIQUE (backtest_run_id,
event_sequence) makes the chronological order a single cross-table
database guarantee.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.backtest_run import BacktestRun
    from app.db.models.event_equity import EventEquity
    from app.db.models.trade import Trade
    from app.db.models.zone_event import ZoneEventRecord

__all__ = ["BacktestEvent"]

BIG_INT = BigInteger().with_variant(Integer(), "sqlite")


class BacktestEvent(Base):
    __tablename__ = "backtest_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('TRADE', 'ZONE_EVENT')", name="ck_backtest_events_event_type"
        ),
        UniqueConstraint(
            "backtest_run_id", "event_sequence", name="uq_backtest_events_run_sequence"
        ),
        Index("ix_backtest_events_run_id_date", "backtest_run_id", "date"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    backtest_run_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey(
            "backtest_runs.id",
            ondelete="CASCADE",
            name="fk_backtest_events_run_id_backtest_runs",
        ),
        nullable=False,
    )
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    market_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)

    backtest_run: Mapped[BacktestRun] = relationship(back_populates="events")
    trade: Mapped[Trade | None] = relationship(
        back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )
    zone_event: Mapped[ZoneEventRecord | None] = relationship(
        back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )
    event_equity: Mapped[EventEquity | None] = relationship(
        back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )
