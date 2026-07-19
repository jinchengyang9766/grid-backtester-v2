"""Tests for the first Alembic migration (users, datasets, price_bars)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.base import Base
from app.db.session import create_database_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]

APPLICATION_TABLES = {"users", "datasets", "price_bars"}


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture()
def migrated(tmp_path: Path) -> Iterator[tuple[Config, Engine]]:
    database_url = f"sqlite:///{tmp_path / 'migration_test.db'}"
    config = _alembic_config(database_url)
    command.upgrade(config, "head")
    database_engine = create_database_engine(database_url)
    yield config, database_engine
    database_engine.dispose()


class TestUpgrade:
    def test_creates_application_tables_and_version_table(
        self, migrated: tuple[Config, Engine]
    ) -> None:
        _, database_engine = migrated
        names = set(sa.inspect(database_engine).get_table_names())
        assert names == APPLICATION_TABLES | {"alembic_version"}

    def test_foreign_keys_cascade(self, migrated: tuple[Config, Engine]) -> None:
        _, database_engine = migrated
        inspector = sa.inspect(database_engine)
        (datasets_fk,) = inspector.get_foreign_keys("datasets")
        (bars_fk,) = inspector.get_foreign_keys("price_bars")
        assert datasets_fk["referred_table"] == "users"
        assert datasets_fk["options"].get("ondelete") == "CASCADE"
        assert bars_fk["referred_table"] == "datasets"
        assert bars_fk["options"].get("ondelete") == "CASCADE"

    def test_indexes_present(self, migrated: tuple[Config, Engine]) -> None:
        _, database_engine = migrated
        inspector = sa.inspect(database_engine)
        dataset_indexes = {i["name"] for i in inspector.get_indexes("datasets")}
        assert "ix_datasets_user_id_created_at" in dataset_indexes
        bar_indexes = {i["name"] for i in inspector.get_indexes("price_bars")}
        assert "ix_price_bars_dataset_id_date" in bar_indexes

    def test_lower_email_index_is_unique_and_functional(
        self, migrated: tuple[Config, Engine]
    ) -> None:
        # SQLAlchemy's SQLite inspector skips expression-based indexes, so the
        # functional index is verified straight from sqlite_master DDL.
        _, database_engine = migrated
        with database_engine.connect() as connection:
            ddl = connection.execute(
                sa.text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='index' AND name='ux_users_email_lower'"
                )
            ).scalar_one()
        assert "UNIQUE" in ddl
        assert "lower(email)" in ddl

    def test_unique_constraints_present(self, migrated: tuple[Config, Engine]) -> None:
        _, database_engine = migrated
        inspector = sa.inspect(database_engine)
        user_uniques = {c["name"] for c in inspector.get_unique_constraints("users")}
        bar_uniques = {c["name"] for c in inspector.get_unique_constraints("price_bars")}
        assert "uq_users_email" in user_uniques
        assert "uq_price_bars_dataset_id_date" in bar_uniques

    def test_check_constraints_present(self, migrated: tuple[Config, Engine]) -> None:
        _, database_engine = migrated
        inspector = sa.inspect(database_engine)
        dataset_checks = {c["name"] for c in inspector.get_check_constraints("datasets")}
        bar_checks = {c["name"] for c in inspector.get_check_constraints("price_bars")}
        assert {"ck_datasets_source_type", "ck_datasets_data_mode"} <= dataset_checks
        assert {"ck_price_bars_close_positive", "ck_price_bars_volume_non_negative"} <= bar_checks

    def test_no_sample_data_inserted(self, migrated: tuple[Config, Engine]) -> None:
        _, database_engine = migrated
        with database_engine.connect() as connection:
            for table in APPLICATION_TABLES:
                count = connection.execute(
                    sa.text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                ).scalar_one()
                assert count == 0

    def test_upgrading_twice_is_a_no_op(self, migrated: tuple[Config, Engine]) -> None:
        config, database_engine = migrated
        command.upgrade(config, "head")
        names = set(sa.inspect(database_engine).get_table_names())
        assert names >= APPLICATION_TABLES

    def test_lower_email_uniqueness_enforced_after_migration(
        self, migrated: tuple[Config, Engine]
    ) -> None:
        _, database_engine = migrated
        insert = sa.text("INSERT INTO users (email, password_hash) VALUES (:email, 'h')")
        with database_engine.connect() as connection:
            connection.execute(insert, {"email": "Mixed@Example.com"})
            connection.commit()
            with pytest.raises(IntegrityError):
                connection.execute(insert, {"email": "mixed@example.com"})

    def test_cascade_enforced_on_migrated_schema(self, migrated: tuple[Config, Engine]) -> None:
        _, database_engine = migrated
        with database_engine.begin() as connection:
            connection.execute(
                sa.text("INSERT INTO users (email, password_hash) VALUES ('c@e.com', 'h')")
            )
            connection.execute(
                sa.text(
                    "INSERT INTO datasets (user_id, name, source_type, original_filename, "
                    "data_mode, start_date, end_date, row_count, column_mapping, "
                    "cleaning_summary) VALUES (1, 'd', 'CSV', 'd.csv', 'CLOSE_ONLY', "
                    "'2026-01-05', '2026-01-06', 1, '{}', '{}')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO price_bars (dataset_id, date, close) "
                    "VALUES (1, '2026-01-05', 10.0)"
                )
            )
            connection.execute(sa.text("DELETE FROM users"))
            remaining_datasets = connection.execute(
                sa.text("SELECT COUNT(*) FROM datasets")
            ).scalar_one()
            remaining_bars = connection.execute(
                sa.text("SELECT COUNT(*) FROM price_bars")
            ).scalar_one()
        assert remaining_datasets == 0
        assert remaining_bars == 0


class TestDowngrade:
    def test_downgrade_base_removes_application_tables(
        self, migrated: tuple[Config, Engine]
    ) -> None:
        config, database_engine = migrated
        command.downgrade(config, "base")
        names = set(sa.inspect(database_engine).get_table_names())
        assert APPLICATION_TABLES.isdisjoint(names)


class TestRevisionChain:
    def test_exactly_one_revision_exists(self, tmp_path: Path) -> None:
        config = _alembic_config(f"sqlite:///{tmp_path / 'chain.db'}")
        script = ScriptDirectory.from_config(config)
        revisions = list(script.walk_revisions())
        assert len(revisions) == 1
        assert revisions[0].doc.splitlines()[0] == "create users datasets and price bars"

    def test_target_metadata_contains_all_model_tables(self) -> None:
        import app.db.models  # noqa: F401

        assert set(Base.metadata.tables) == APPLICATION_TABLES

    def test_env_imports_models_for_registration(self) -> None:
        env_source = (BACKEND_DIR / "alembic" / "env.py").read_text(encoding="utf-8")
        assert "import app.db.models" in env_source
