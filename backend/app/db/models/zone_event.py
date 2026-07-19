"""ZoneEvent persistence model (SPEC Section 23.7).

Named ZoneEventRecord to avoid confusion with the pure engine's ZoneEvent;
the table name remains zone_events. No backtest_run_id/date/event_sequence
columns — those live on the parent BacktestEvent.
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

__all__ = ["ZoneEventRecord"]

BIG_INT = BigInteger().with_variant(Integer(), "sqlite")


class ZoneEventRecord(Base):
    __tablename__ = "zone_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ENTER_C_ZONE', 'EXIT_C_ZONE', "
            "'OUTSIDE_C_BOUNDARY', 'RETURN_INSIDE_C_BOUNDARY')",
            name="ck_zone_events_event_type",
        ),
        UniqueConstraint("event_id", name="uq_zone_events_event_id"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey(
            "backtest_events.id",
            ondelete="CASCADE",
            name="fk_zone_events_event_id_backtest_events",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)

    event: Mapped[BacktestEvent] = relationship(back_populates="zone_event")
