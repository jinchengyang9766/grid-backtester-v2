"""PriceBar persistence model (SPEC Section 23.3)."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.dataset import Dataset

__all__ = ["PriceBar"]

# Logical BIGSERIAL/BIGINT: SQLite only autoincrements INTEGER PRIMARY KEY.
BIG_INT = BigInteger().with_variant(Integer(), "sqlite")


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (
        CheckConstraint("close > 0", name="ck_price_bars_close_positive"),
        CheckConstraint("volume IS NULL OR volume >= 0", name="ck_price_bars_volume_non_negative"),
        UniqueConstraint("dataset_id", "date", name="uq_price_bars_dataset_id_date"),
        Index("ix_price_bars_dataset_id_date", "dataset_id", "date"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("datasets.id", ondelete="CASCADE", name="fk_price_bars_dataset_id_datasets"),
        nullable=False,
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="price_bars")
