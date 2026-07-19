"""DailyEquity persistence model (SPEC Section 23.8).

One row per Bar date — intentionally outside the backtest_events
sequencing model, so it has no event_id; backtest_run_id/date are this
table's own primary facts.
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
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.backtest_run import BacktestRun

__all__ = ["DailyEquity"]

BIG_INT = BigInteger().with_variant(Integer(), "sqlite")


class DailyEquity(Base):
    __tablename__ = "daily_equity"
    __table_args__ = (
        CheckConstraint(
            "zone_at_close IN ('IN_A', 'IN_C', 'OUTSIDE_C')",
            name="ck_daily_equity_zone_at_close",
        ),
        UniqueConstraint("backtest_run_id", "date", name="uq_daily_equity_run_date"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    backtest_run_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey(
            "backtest_runs.id", ondelete="CASCADE", name="fk_daily_equity_run_id_backtest_runs"
        ),
        nullable=False,
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    shares: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    drawdown: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    zone_at_close: Mapped[str] = mapped_column(Text, nullable=False)

    backtest_run: Mapped[BacktestRun] = relationship(back_populates="daily_equity_rows")
