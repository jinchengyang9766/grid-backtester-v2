"""EventEquity persistence model (SPEC Section 23.9).

No backtest_run_id/date/event_sequence/market_price columns — all four are
obtained through the parent BacktestEvent via event_id.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.backtest_event import BacktestEvent

__all__ = ["EventEquity"]

BIG_INT = BigInteger().with_variant(Integer(), "sqlite")


class EventEquity(Base):
    __tablename__ = "event_equity"
    __table_args__ = (UniqueConstraint("event_id", name="uq_event_equity_event_id"),)

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey(
            "backtest_events.id",
            ondelete="CASCADE",
            name="fk_event_equity_event_id_backtest_events",
        ),
        nullable=False,
    )
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    shares: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)

    event: Mapped[BacktestEvent] = relationship(back_populates="event_equity")
