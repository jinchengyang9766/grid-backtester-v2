"""create users datasets and price bars

Revision ID: b7a1d2c3e4f5
Revises:
Create Date: 2026-07-19

First persistence slice (SPEC Sections 23.1-23.3): users, datasets, and
price_bars, with ON DELETE CASCADE from users to datasets and from datasets
to price_bars.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "b7a1d2c3e4f5"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Logical BIGSERIAL/BIGINT on PostgreSQL; SQLite only autoincrements
# INTEGER PRIMARY KEY, so the identity degrades to INTEGER there.
BIG_INT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

# JSONB on PostgreSQL; SQLite has no JSONB and uses plain JSON.
JSON_DOCUMENT = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ux_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "datasets",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", BIG_INT, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("security_name", sa.Text(), nullable=True),
        sa.Column("security_code", sa.Text(), nullable=True),
        sa.Column("data_mode", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_mapping", JSON_DOCUMENT, nullable=False),
        sa.Column("cleaning_summary", JSON_DOCUMENT, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_datasets_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("source_type IN ('TDX_XLS', 'CSV')", name="ck_datasets_source_type"),
        sa.CheckConstraint("data_mode IN ('OHLCV', 'CLOSE_ONLY')", name="ck_datasets_data_mode"),
    )
    op.create_index(
        "ix_datasets_user_id_created_at", "datasets", ["user_id", sa.text("created_at DESC")]
    )

    op.create_table(
        "price_bars",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("dataset_id", BIG_INT, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=True),
        sa.Column("high", sa.Numeric(20, 8), nullable=True),
        sa.Column("low", sa.Numeric(20, 8), nullable=True),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(20, 8), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name="fk_price_bars_dataset_id_datasets",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("close > 0", name="ck_price_bars_close_positive"),
        sa.CheckConstraint(
            "volume IS NULL OR volume >= 0", name="ck_price_bars_volume_non_negative"
        ),
        sa.UniqueConstraint("dataset_id", "date", name="uq_price_bars_dataset_id_date"),
    )
    op.create_index("ix_price_bars_dataset_id_date", "price_bars", ["dataset_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_price_bars_dataset_id_date", table_name="price_bars")
    op.drop_table("price_bars")
    op.drop_index("ix_datasets_user_id_created_at", table_name="datasets")
    op.drop_table("datasets")
    op.drop_index("ux_users_email_lower", table_name="users")
    op.drop_table("users")
