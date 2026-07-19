"""Dataset persistence model (SPEC Section 23.2)."""

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
    from app.db.models.price_bar import PriceBar
    from app.db.models.user import User

__all__ = ["Dataset"]

# Logical BIGSERIAL/BIGINT: SQLite only autoincrements INTEGER PRIMARY KEY.
BIG_INT = BigInteger().with_variant(Integer(), "sqlite")

# JSONB in PostgreSQL; SQLite has no JSONB, so tests use plain JSON.
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint("source_type IN ('TDX_XLS', 'CSV')", name="ck_datasets_source_type"),
        CheckConstraint("data_mode IN ('OHLCV', 'CLOSE_ONLY')", name="ck_datasets_data_mode"),
        Index("ix_datasets_user_id_created_at", "user_id", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_datasets_user_id_users"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    security_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    security_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_mode: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_mapping: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    cleaning_summary: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="datasets")
    price_bars: Mapped[list[PriceBar]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )
