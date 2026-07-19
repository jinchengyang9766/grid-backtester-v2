"""BacktestRun persistence model (SPEC Section 23.4)."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.backtest_event import BacktestEvent
    from app.db.models.daily_equity import DailyEquity
    from app.db.models.dataset import Dataset
    from app.db.models.user import User

__all__ = ["BacktestRun"]

BIG_INT = BigInteger().with_variant(Integer(), "sqlite")
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_backtest_runs_status",
        ),
        CheckConstraint(
            "ohlc_path_mode IS NULL OR ohlc_path_mode IN ('HIGH_FIRST', 'LOW_FIRST', 'AUTO')",
            name="ck_backtest_runs_ohlc_path_mode",
        ),
        Index("ix_backtest_runs_user_id_created_at", "user_id", text("created_at DESC")),
        Index("ix_backtest_runs_dataset_id", "dataset_id"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_backtest_runs_user_id_users"),
        nullable=False,
    )
    # RESTRICT: a Dataset can never be deleted while runs reference it —
    # backtest history is only removed via the run itself or the owning user.
    dataset_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("datasets.id", ondelete="RESTRICT", name="fk_backtest_runs_dataset_id_datasets"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    ohlc_path_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    result_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="backtest_runs")
    dataset: Mapped[Dataset] = relationship(back_populates="backtest_runs")
    events: Mapped[list[BacktestEvent]] = relationship(
        back_populates="backtest_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BacktestEvent.event_sequence",
    )
    daily_equity_rows: Mapped[list[DailyEquity]] = relationship(
        back_populates="backtest_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DailyEquity.date",
    )
