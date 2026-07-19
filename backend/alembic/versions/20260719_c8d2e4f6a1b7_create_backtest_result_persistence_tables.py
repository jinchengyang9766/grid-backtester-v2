"""create backtest result persistence tables

Revision ID: c8d2e4f6a1b7
Revises: b7a1d2c3e4f5
Create Date: 2026-07-19

Backtest persistence slice (SPEC Sections 23.4-23.9): backtest_runs,
the shared backtest_events ordering backbone, trades, zone_events,
daily_equity, and event_equity. Deleting a User cascades through runs to
every result row; deleting a Dataset is RESTRICTed while runs reference it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c8d2e4f6a1b7"
down_revision: str | None = "b7a1d2c3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIG_INT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
JSON_DOCUMENT = sa.JSON().with_variant(JSONB(), "postgresql")
MONEY = sa.Numeric(20, 8)


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", BIG_INT, nullable=False),
        sa.Column("dataset_id", BIG_INT, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("configuration", JSON_DOCUMENT, nullable=False),
        sa.Column("ohlc_path_mode", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("result_metrics", JSON_DOCUMENT, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_backtest_runs_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name="fk_backtest_runs_dataset_id_datasets",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_backtest_runs_status",
        ),
        sa.CheckConstraint(
            "ohlc_path_mode IS NULL OR ohlc_path_mode IN ('HIGH_FIRST', 'LOW_FIRST', 'AUTO')",
            name="ck_backtest_runs_ohlc_path_mode",
        ),
    )
    op.create_index(
        "ix_backtest_runs_user_id_created_at",
        "backtest_runs",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_backtest_runs_dataset_id", "backtest_runs", ["dataset_id"])

    op.create_table(
        "backtest_events",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("backtest_run_id", BIG_INT, nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("market_price", MONEY, nullable=False),
        sa.ForeignKeyConstraint(
            ["backtest_run_id"],
            ["backtest_runs.id"],
            name="fk_backtest_events_run_id_backtest_runs",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "event_type IN ('TRADE', 'ZONE_EVENT')", name="ck_backtest_events_event_type"
        ),
        sa.UniqueConstraint(
            "backtest_run_id", "event_sequence", name="uq_backtest_events_run_sequence"
        ),
    )
    op.create_index(
        "ix_backtest_events_run_id_date", "backtest_events", ["backtest_run_id", "date"]
    )

    op.create_table(
        "trades",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("event_id", BIG_INT, nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("grid_price", MONEY, nullable=False),
        sa.Column("execution_price", MONEY, nullable=True),
        sa.Column("shares", BIG_INT, nullable=False),
        sa.Column("notional", MONEY, nullable=True),
        sa.Column("commission", MONEY, nullable=True),
        sa.Column("slippage_cost", MONEY, nullable=True),
        sa.Column("cash_after", MONEY, nullable=False),
        sa.Column("shares_after", BIG_INT, nullable=False),
        sa.Column("equity_after", MONEY, nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["backtest_events.id"],
            name="fk_trades_event_id_backtest_events",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_trades_side"),
        sa.CheckConstraint("status IN ('EXECUTED', 'SKIPPED')", name="ck_trades_status"),
        sa.CheckConstraint(
            "skip_reason IS NULL OR skip_reason IN "
            "('INSUFFICIENT_CASH', 'INSUFFICIENT_SHARES', "
            "'INSUFFICIENT_CASH_FOR_COMMISSION')",
            name="ck_trades_skip_reason",
        ),
        sa.UniqueConstraint("event_id", name="uq_trades_event_id"),
    )

    op.create_table(
        "zone_events",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("event_id", BIG_INT, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("price", MONEY, nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["backtest_events.id"],
            name="fk_zone_events_event_id_backtest_events",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "event_type IN ('ENTER_C_ZONE', 'EXIT_C_ZONE', "
            "'OUTSIDE_C_BOUNDARY', 'RETURN_INSIDE_C_BOUNDARY')",
            name="ck_zone_events_event_type",
        ),
        sa.UniqueConstraint("event_id", name="uq_zone_events_event_id"),
    )

    op.create_table(
        "daily_equity",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("backtest_run_id", BIG_INT, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("close", MONEY, nullable=False),
        sa.Column("cash", MONEY, nullable=False),
        sa.Column("shares", BIG_INT, nullable=False),
        sa.Column("equity", MONEY, nullable=False),
        sa.Column("drawdown", MONEY, nullable=False),
        sa.Column("zone_at_close", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["backtest_run_id"],
            ["backtest_runs.id"],
            name="fk_daily_equity_run_id_backtest_runs",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "zone_at_close IN ('IN_A', 'IN_C', 'OUTSIDE_C')",
            name="ck_daily_equity_zone_at_close",
        ),
        sa.UniqueConstraint("backtest_run_id", "date", name="uq_daily_equity_run_date"),
    )

    op.create_table(
        "event_equity",
        sa.Column("id", BIG_INT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("event_id", BIG_INT, nullable=False),
        sa.Column("cash", MONEY, nullable=False),
        sa.Column("shares", BIG_INT, nullable=False),
        sa.Column("equity", MONEY, nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["backtest_events.id"],
            name="fk_event_equity_event_id_backtest_events",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("event_id", name="uq_event_equity_event_id"),
    )


def downgrade() -> None:
    op.drop_table("event_equity")
    op.drop_table("daily_equity")
    op.drop_table("zone_events")
    op.drop_table("trades")
    op.drop_index("ix_backtest_events_run_id_date", table_name="backtest_events")
    op.drop_table("backtest_events")
    op.drop_index("ix_backtest_runs_dataset_id", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_user_id_created_at", table_name="backtest_runs")
    op.drop_table("backtest_runs")
