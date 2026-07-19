"""User persistence model (SPEC Section 23.1)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.backtest_run import BacktestRun
    from app.db.models.dataset import Dataset

__all__ = ["User"]

# Logical BIGSERIAL: SQLite only autoincrements INTEGER PRIMARY KEY columns,
# so the BIGINT identity degrades to INTEGER on the SQLite test database.
BIG_INT = BigInteger().with_variant(Integer(), "sqlite")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    backtest_runs: Mapped[list[BacktestRun]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


# Case-insensitive uniqueness enforced at database level, on top of the exact
# uq_users_email constraint.
Index("ux_users_email_lower", func.lower(User.email), unique=True)
