"""Trade persistence model (SPEC Section 23.6).

No backtest_run_id/date/event_sequence columns — those facts live only on
the parent BacktestEvent, reached through event_id.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.backtest_event import BacktestEvent

__all__ = ["Trade"]

BIG_INT = BigInteger().with_variant(Integer(), "sqlite")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_trades_side"),
        CheckConstraint("status IN ('EXECUTED', 'SKIPPED')", name="ck_trades_status"),
        CheckConstraint(
            "skip_reason IS NULL OR skip_reason IN "
            "('INSUFFICIENT_CASH', 'INSUFFICIENT_SHARES', "
            "'INSUFFICIENT_CASH_FOR_COMMISSION')",
            name="ck_trades_skip_reason",
        ),
        UniqueConstraint("event_id", name="uq_trades_event_id"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey(
            "backtest_events.id", ondelete="CASCADE", name="fk_trades_event_id_backtest_events"
        ),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(Text, nullable=False)
    grid_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    execution_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    shares: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    commission: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    slippage_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    cash_after: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    shares_after: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    equity_after: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped[BacktestEvent] = relationship(back_populates="trade")
