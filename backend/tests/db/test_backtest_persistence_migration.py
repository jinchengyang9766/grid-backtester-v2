"""Tests for the second Alembic migration (backtest persistence tables)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.session import create_database_engine
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parents[2]

FIRST_REVISION = "b7a1d2c3e4f5"
SECOND_REVISION = "c8d2e4f6a1b7"
FIRST_SLICE_TABLES = {"users", "datasets", "price_bars"}
BACKTEST_TABLES = {
    "backtest_runs",
    "backtest_events",
    "trades",
    "zone_events",
    "daily_equity",
    "event_equity",
}
ALL_TABLES = FIRST_SLICE_TABLES | BACKTEST_TABLES


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture()
def migrated(tmp_path: Path) -> Iterator[tuple[Config, Engine]]:
    database_url = f"sqlite:///{tmp_path / 'bt_migration.db'}"
    config = _alembic_config(database_url)
    command.upgrade(config, "head")
    engine = create_database_engine(database_url)
    yield config, engine
    engine.dispose()


class TestRevisionChain:
    def test_two_revisions_with_correct_down_revision(self, tmp_path: Path) -> None:
        config = _alembic_config(f"sqlite:///{tmp_path / 'chain.db'}")
        script = ScriptDirectory.from_config(config)
        revisions = list(script.walk_revisions())  # newest first
        assert [revision.revision for revision in revisions] == [
            SECOND_REVISION,
            FIRST_REVISION,
        ]
        assert revisions[0].down_revision == FIRST_REVISION
        assert revisions[0].doc.splitlines()[0] == "create backtest result persistence tables"


class TestUpgrade:
    def test_head_creates_exactly_nine_application_tables(
        self, migrated: tuple[Config, Engine]
    ) -> None:
        _, engine = migrated
        names = set(sa.inspect(engine).get_table_names())
        assert names == ALL_TABLES | {"alembic_version"}

    def test_constraints_and_indexes_present(self, migrated: tuple[Config, Engine]) -> None:
        _, engine = migrated
        inspector = sa.inspect(engine)

        event_uniques = {c["name"] for c in inspector.get_unique_constraints("backtest_events")}
        assert "uq_backtest_events_run_sequence" in event_uniques
        assert "uq_daily_equity_run_date" in {
            c["name"] for c in inspector.get_unique_constraints("daily_equity")
        }
        for table in ("trades", "zone_events", "event_equity"):
            assert f"uq_{table}_event_id" in {
                c["name"] for c in inspector.get_unique_constraints(table)
            }

        run_fks = {fk["name"]: fk for fk in inspector.get_foreign_keys("backtest_runs")}
        assert run_fks["fk_backtest_runs_user_id_users"]["options"]["ondelete"] == "CASCADE"
        assert run_fks["fk_backtest_runs_dataset_id_datasets"]["options"]["ondelete"] == "RESTRICT"
        for table, fk_name in (
            ("backtest_events", "fk_backtest_events_run_id_backtest_runs"),
            ("trades", "fk_trades_event_id_backtest_events"),
            ("zone_events", "fk_zone_events_event_id_backtest_events"),
            ("daily_equity", "fk_daily_equity_run_id_backtest_runs"),
            ("event_equity", "fk_event_equity_event_id_backtest_events"),
        ):
            fks = {fk["name"]: fk for fk in inspector.get_foreign_keys(table)}
            assert fks[fk_name]["options"]["ondelete"] == "CASCADE"

        run_checks = {c["name"] for c in inspector.get_check_constraints("backtest_runs")}
        assert {"ck_backtest_runs_status", "ck_backtest_runs_ohlc_path_mode"} <= run_checks
        run_indexes = {index["name"] for index in inspector.get_indexes("backtest_runs")}
        assert {"ix_backtest_runs_user_id_created_at", "ix_backtest_runs_dataset_id"} <= (
            run_indexes
        )
        assert "ix_backtest_events_run_id_date" in {
            index["name"] for index in inspector.get_indexes("backtest_events")
        }

    def test_no_seed_rows(self, migrated: tuple[Config, Engine]) -> None:
        _, engine = migrated
        with engine.connect() as connection:
            for table in sorted(ALL_TABLES):
                total = connection.execute(
                    sa.text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                ).scalar_one()
                assert total == 0

    def test_upgrading_twice_is_a_no_op(self, migrated: tuple[Config, Engine]) -> None:
        config, engine = migrated
        command.upgrade(config, "head")
        assert set(sa.inspect(engine).get_table_names()) >= ALL_TABLES


class TestDowngrade:
    def test_partial_downgrade_removes_only_backtest_tables(
        self, migrated: tuple[Config, Engine]
    ) -> None:
        config, engine = migrated
        command.downgrade(config, FIRST_REVISION)
        names = set(sa.inspect(engine).get_table_names())
        assert names == FIRST_SLICE_TABLES | {"alembic_version"}
        # And back up to head again.
        command.upgrade(config, "head")
        assert set(sa.inspect(engine).get_table_names()) == ALL_TABLES | {"alembic_version"}

    def test_downgrade_base_removes_all_application_tables(
        self, migrated: tuple[Config, Engine]
    ) -> None:
        config, engine = migrated
        command.downgrade(config, "base")
        assert set(sa.inspect(engine).get_table_names()).isdisjoint(ALL_TABLES)


class TestPostgresqlCompilation:
    def test_offline_upgrade_sql_compiles_for_postgresql(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = _alembic_config(
            "postgresql+psycopg://user:placeholder@localhost:5432/compile_only"
        )
        command.upgrade(config, "head", sql=True)  # offline: never connects
        ddl = capsys.readouterr().out
        assert "configuration JSONB NOT NULL" in ddl
        assert "market_price NUMERIC(20, 8) NOT NULL" in ddl
        assert "ON DELETE RESTRICT" in ddl
        assert "ON DELETE CASCADE" in ddl
        assert "BIGSERIAL" in ddl
        assert "CONSTRAINT uq_backtest_events_run_sequence UNIQUE" in ddl
