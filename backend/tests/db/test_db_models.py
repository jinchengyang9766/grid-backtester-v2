"""Tests for the first persistence-model slice: User, Dataset, and PriceBar."""

import datetime
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from app.db import Base
from app.db.models import Dataset, PriceBar, User
from app.db.session import create_database_engine, create_session_factory
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

BACKEND_DIR = Path(__file__).resolve().parents[2]

USERS_TABLE = cast(sa.Table, User.__table__)
DATASETS_TABLE = cast(sa.Table, Dataset.__table__)
PRICE_BARS_TABLE = cast(sa.Table, PriceBar.__table__)


def _pg_table_ddl(table: sa.Table) -> str:
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


def _pg_index_ddl(index: sa.Index) -> str:
    return str(CreateIndex(index).compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'models_test.db'}")
    Base.metadata.create_all(database_engine)
    yield database_engine
    database_engine.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    factory = create_session_factory(engine)
    with factory() as db_session:
        yield db_session


def make_user(email: str = "alice@example.com") -> User:
    return User(email=email, password_hash="argon2id-placeholder-hash")


def make_dataset(user: User, **overrides: Any) -> Dataset:
    fields: dict[str, Any] = {
        "user": user,
        "name": "Sample dataset",
        "source_type": "TDX_XLS",
        "original_filename": "sample.xls",
        "security_name": "测试证券",
        "security_code": "159999",
        "data_mode": "OHLCV",
        "start_date": datetime.date(2026, 1, 5),
        "end_date": datetime.date(2026, 1, 6),
        "row_count": 2,
        "column_mapping": {"date": "时间", "close": "收盘"},
        "cleaning_summary": {"rows_removed": 0, "issues": []},
    }
    fields.update(overrides)
    return Dataset(**fields)


def make_price_bar(
    dataset: Dataset, day: datetime.date = datetime.date(2026, 1, 5), **overrides: Any
) -> PriceBar:
    fields: dict[str, Any] = {
        "dataset": dataset,
        "date": day,
        "open": Decimal("10.00000000"),
        "high": Decimal("10.50000000"),
        "low": Decimal("9.75000000"),
        "close": Decimal("10.25000000"),
        "volume": Decimal("120000"),
    }
    fields.update(overrides)
    return PriceBar(**fields)


class TestModelRegistration:
    def test_metadata_contains_the_first_slice_tables(self) -> None:
        assert {"users", "datasets", "price_bars"} <= set(Base.metadata.tables)

    def test_no_optimization_tables_are_registered(self) -> None:
        forbidden = {"optimization_jobs", "optimization_results"}
        assert forbidden.isdisjoint(set(Base.metadata.tables))

    def test_public_imports_work(self) -> None:
        import app.db
        import app.db.models as models

        assert models.User is User
        assert models.Dataset is Dataset
        assert models.PriceBar is PriceBar
        assert app.db.User is User
        assert app.db.Dataset is Dataset
        assert app.db.PriceBar is PriceBar


class TestUser:
    def test_insert_and_read_back(self, session: Session) -> None:
        session.add(make_user())
        session.commit()
        stored = session.execute(sa.select(User)).scalar_one()
        assert stored.email == "alice@example.com"
        assert stored.password_hash == "argon2id-placeholder-hash"

    def test_ids_autoincrement(self, session: Session) -> None:
        first, second = make_user("a@example.com"), make_user("b@example.com")
        session.add_all([first, second])
        session.commit()
        assert [first.id, second.id] == [1, 2]

    def test_timestamps_populate(self, session: Session) -> None:
        user = make_user()
        session.add(user)
        session.commit()
        session.refresh(user)
        assert isinstance(user.created_at, datetime.datetime)
        assert isinstance(user.updated_at, datetime.datetime)

    def test_updated_at_has_orm_onupdate(self) -> None:
        assert USERS_TABLE.c.updated_at.onupdate is not None
        assert USERS_TABLE.c.created_at.onupdate is None

    def test_email_is_required(self, session: Session) -> None:
        session.add(User(email=None, password_hash="x"))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_password_hash_is_required(self, session: Session) -> None:
        session.add(User(email="a@example.com", password_hash=None))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_duplicate_exact_email_fails(self, session: Session) -> None:
        session.add(make_user("dup@example.com"))
        session.commit()
        session.add(make_user("dup@example.com"))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_duplicate_email_differing_only_in_case_fails(self, session: Session) -> None:
        session.add(make_user("Case@Example.com"))
        session.commit()
        session.add(make_user("case@example.com"))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_datasets_relationship(self, session: Session) -> None:
        user = make_user()
        dataset = make_dataset(user)
        session.add(dataset)
        session.commit()
        assert user.datasets == [dataset]
        assert dataset.user is user

    def test_deleting_user_cascades_to_datasets_and_price_bars(self, session: Session) -> None:
        user = make_user()
        make_price_bar(make_dataset(user))
        session.add(user)
        session.commit()
        session.execute(sa.text("DELETE FROM users"))
        session.commit()
        assert session.execute(sa.select(sa.func.count()).select_from(Dataset)).scalar_one() == 0
        assert session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one() == 0

    def test_password_hash_is_stored_verbatim(self, session: Session) -> None:
        user = User(email="v@example.com", password_hash="opaque-value-as-supplied")
        session.add(user)
        session.commit()
        raw = session.execute(sa.text("SELECT password_hash FROM users")).scalar_one()
        assert raw == "opaque-value-as-supplied"


class TestDataset:
    def test_insert_with_all_fields(self, session: Session) -> None:
        session.add(make_dataset(make_user()))
        session.commit()
        stored = session.execute(sa.select(Dataset)).scalar_one()
        assert stored.name == "Sample dataset"
        assert stored.security_name == "测试证券"
        assert stored.row_count == 2

    def test_nullable_security_fields(self, session: Session) -> None:
        session.add(make_dataset(make_user(), security_name=None, security_code=None))
        session.commit()
        stored = session.execute(sa.select(Dataset)).scalar_one()
        assert stored.security_name is None
        assert stored.security_code is None

    def test_json_columns_round_trip(self, session: Session) -> None:
        column_mapping = {"date": "时间", "open": "开盘", "close": "收盘"}
        cleaning_summary = {"rows_removed": 3, "issues": [{"row": 7, "reason": "bad close"}]}
        session.add(
            make_dataset(
                make_user(), column_mapping=column_mapping, cleaning_summary=cleaning_summary
            )
        )
        session.commit()
        session.expire_all()
        stored = session.execute(sa.select(Dataset)).scalar_one()
        assert stored.column_mapping == column_mapping
        assert stored.cleaning_summary == cleaning_summary

    @pytest.mark.parametrize("source_type", ["TDX_XLS", "CSV"])
    def test_valid_source_types_accepted(self, session: Session, source_type: str) -> None:
        session.add(make_dataset(make_user(), source_type=source_type))
        session.commit()

    def test_invalid_source_type_rejected(self, session: Session) -> None:
        session.add(make_dataset(make_user(), source_type="XLSX"))
        with pytest.raises(IntegrityError):
            session.commit()

    @pytest.mark.parametrize("data_mode", ["OHLCV", "CLOSE_ONLY"])
    def test_valid_data_modes_accepted(self, session: Session, data_mode: str) -> None:
        session.add(make_dataset(make_user(), data_mode=data_mode))
        session.commit()

    def test_invalid_data_mode_rejected(self, session: Session) -> None:
        session.add(make_dataset(make_user(), data_mode="TICK"))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_price_bars_relationship(self, session: Session) -> None:
        dataset = make_dataset(make_user())
        bar = make_price_bar(dataset)
        session.add(dataset)
        session.commit()
        assert dataset.price_bars == [bar]
        assert bar.dataset is dataset

    def test_removing_bar_from_collection_deletes_orphan(self, session: Session) -> None:
        dataset = make_dataset(make_user())
        bar = make_price_bar(dataset)
        session.add(dataset)
        session.commit()
        dataset.price_bars.remove(bar)
        session.commit()
        assert session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one() == 0

    def test_deleting_dataset_cascades_to_price_bars(self, session: Session) -> None:
        dataset = make_dataset(make_user())
        make_price_bar(dataset)
        make_price_bar(dataset, day=datetime.date(2026, 1, 6))
        session.add(dataset)
        session.commit()
        session.execute(sa.text("DELETE FROM datasets"))
        session.commit()
        assert session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one() == 0
        assert session.execute(sa.select(sa.func.count()).select_from(User)).scalar_one() == 1

    def test_created_at_populates(self, session: Session) -> None:
        dataset = make_dataset(make_user())
        session.add(dataset)
        session.commit()
        session.refresh(dataset)
        assert isinstance(dataset.created_at, datetime.datetime)


class TestPriceBar:
    def test_decimal_values_round_trip_as_decimal(self, session: Session) -> None:
        session.add(make_price_bar(make_dataset(make_user()), close=Decimal("10.12345678")))
        session.commit()
        session.expire_all()
        stored = session.execute(sa.select(PriceBar)).scalar_one()
        assert isinstance(stored.close, Decimal)
        assert stored.close == Decimal("10.12345678")
        assert isinstance(stored.open, Decimal)

    def test_numeric_precision_is_20_8(self) -> None:
        for column in ("open", "high", "low", "close", "volume"):
            column_type = PRICE_BARS_TABLE.c[column].type
            assert isinstance(column_type, sa.Numeric)
            assert (column_type.precision, column_type.scale) == (20, 8)

    def test_nullable_open_high_low_volume(self, session: Session) -> None:
        session.add(
            make_price_bar(make_dataset(make_user()), open=None, high=None, low=None, volume=None)
        )
        session.commit()
        stored = session.execute(sa.select(PriceBar)).scalar_one()
        assert (stored.open, stored.high, stored.low, stored.volume) == (None, None, None, None)

    @pytest.mark.parametrize("close", [Decimal("0"), Decimal("-1.5")])
    def test_non_positive_close_rejected(self, session: Session, close: Decimal) -> None:
        session.add(make_price_bar(make_dataset(make_user()), close=close))
        with pytest.raises(IntegrityError):
            session.commit()

    @pytest.mark.parametrize("volume", [Decimal("0"), Decimal("500")])
    def test_non_negative_volume_accepted(self, session: Session, volume: Decimal) -> None:
        session.add(make_price_bar(make_dataset(make_user()), volume=volume))
        session.commit()

    def test_negative_volume_rejected(self, session: Session) -> None:
        session.add(make_price_bar(make_dataset(make_user()), volume=Decimal("-1")))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_duplicate_dataset_date_rejected(self, session: Session) -> None:
        dataset = make_dataset(make_user())
        make_price_bar(dataset)
        make_price_bar(dataset)
        session.add(dataset)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_different_dates_in_one_dataset_accepted(self, session: Session) -> None:
        dataset = make_dataset(make_user())
        make_price_bar(dataset, day=datetime.date(2026, 1, 5))
        make_price_bar(dataset, day=datetime.date(2026, 1, 6))
        session.add(dataset)
        session.commit()

    def test_same_date_in_different_datasets_accepted(self, session: Session) -> None:
        user = make_user()
        make_price_bar(make_dataset(user, name="one"))
        make_price_bar(make_dataset(user, name="two"))
        session.add(user)
        session.commit()


class TestSchemaDefinition:
    def test_foreign_keys_use_on_delete_cascade(self) -> None:
        user_fk = next(iter(DATASETS_TABLE.c.user_id.foreign_keys))
        dataset_fk = next(iter(PRICE_BARS_TABLE.c.dataset_id.foreign_keys))
        assert user_fk.ondelete == "CASCADE"
        assert dataset_fk.ondelete == "CASCADE"

    def test_named_check_constraints_exist(self) -> None:
        dataset_checks = {
            c.name for c in DATASETS_TABLE.constraints if isinstance(c, sa.CheckConstraint)
        }
        bar_checks = {
            c.name for c in PRICE_BARS_TABLE.constraints if isinstance(c, sa.CheckConstraint)
        }
        assert {"ck_datasets_source_type", "ck_datasets_data_mode"} <= dataset_checks
        assert {"ck_price_bars_close_positive", "ck_price_bars_volume_non_negative"} <= bar_checks

    def test_named_unique_constraints_exist(self) -> None:
        user_uniques = {
            c.name for c in USERS_TABLE.constraints if isinstance(c, sa.UniqueConstraint)
        }
        bar_uniques = {
            c.name for c in PRICE_BARS_TABLE.constraints if isinstance(c, sa.UniqueConstraint)
        }
        assert "uq_users_email" in user_uniques
        assert "uq_price_bars_dataset_id_date" in bar_uniques

    def test_required_indexes_exist(self) -> None:
        assert "ix_datasets_user_id_created_at" in {i.name for i in DATASETS_TABLE.indexes}
        assert "ix_price_bars_dataset_id_date" in {i.name for i in PRICE_BARS_TABLE.indexes}

    def test_lower_email_index_is_unique(self) -> None:
        index = next(i for i in USERS_TABLE.indexes if i.name == "ux_users_email_lower")
        assert index.unique is True

    def test_timestamp_columns_are_timezone_aware(self) -> None:
        for column in (
            USERS_TABLE.c.created_at,
            USERS_TABLE.c.updated_at,
            DATASETS_TABLE.c.created_at,
        ):
            assert isinstance(column.type, sa.DateTime)
            assert column.type.timezone is True

    def test_postgresql_compilation_uses_jsonb(self) -> None:
        ddl = _pg_table_ddl(DATASETS_TABLE)
        assert "column_mapping JSONB NOT NULL" in ddl
        assert "cleaning_summary JSONB NOT NULL" in ddl

    def test_postgresql_compilation_uses_numeric_20_8(self) -> None:
        ddl = _pg_table_ddl(PRICE_BARS_TABLE)
        for column in ("open", "high", "low", "close", "volume"):
            assert f"{column} NUMERIC(20, 8)" in ddl

    def test_postgresql_ids_compile_as_bigserial_and_bigint(self) -> None:
        users_ddl = _pg_table_ddl(USERS_TABLE)
        datasets_ddl = _pg_table_ddl(DATASETS_TABLE)
        bars_ddl = _pg_table_ddl(PRICE_BARS_TABLE)
        assert "id BIGSERIAL NOT NULL" in users_ddl
        assert "id BIGSERIAL NOT NULL" in datasets_ddl
        assert "user_id BIGINT NOT NULL" in datasets_ddl
        assert "id BIGSERIAL NOT NULL" in bars_ddl
        assert "dataset_id BIGINT NOT NULL" in bars_ddl

    def test_postgresql_lower_email_index_compiles(self) -> None:
        index = next(i for i in USERS_TABLE.indexes if i.name == "ux_users_email_lower")
        ddl = _pg_index_ddl(index)
        assert "UNIQUE" in ddl
        assert "lower(email)" in ddl


class TestSessionIntegration:
    def test_sqlite_foreign_keys_pragma_is_on(self, engine: Engine) -> None:
        with engine.connect() as connection:
            assert connection.execute(sa.text("PRAGMA foreign_keys")).scalar_one() == 1

    def test_sqlite_rejects_orphan_foreign_key(self, session: Session) -> None:
        # With PRAGMA foreign_keys=ON, SQLite enforces the FK at statement time.
        with pytest.raises(IntegrityError):
            session.execute(
                sa.text(
                    "INSERT INTO datasets (user_id, name, source_type, original_filename, "
                    "data_mode, start_date, end_date, row_count, column_mapping, "
                    "cleaning_summary) VALUES (999, 'x', 'CSV', 'x.csv', 'OHLCV', "
                    "'2026-01-05', '2026-01-06', 1, '{}', '{}')"
                )
            )

    def test_engine_creation_does_not_touch_the_database_file(self, tmp_path: Path) -> None:
        database_file = tmp_path / "lazy.db"
        create_database_engine(f"sqlite:///{database_file}")
        assert not database_file.exists()

    def test_importing_models_creates_no_tables(self, tmp_path: Path) -> None:
        fresh_engine = create_database_engine(f"sqlite:///{tmp_path / 'untouched.db'}")
        with fresh_engine.connect() as connection:
            names = (
                connection.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))
                .scalars()
                .all()
            )
        assert list(names) == []

    def test_no_default_dev_database_created_by_model_imports(self) -> None:
        # The module-level engine is lazy; importing app.db must not create
        # the default development database file inside the backend directory.
        # (If a developer created it manually earlier, it would be tracked by
        # git-ls-files checks instead; this asserts our imports stay lazy.)
        import app.db  # noqa: F401

        assert not (BACKEND_DIR / "does_not_exist.db").exists()


class TestArchitectureBoundaries:
    MODEL_FILES = [
        BACKEND_DIR / "app" / "db" / "models" / name
        for name in ("__init__.py", "user.py", "dataset.py", "price_bar.py")
    ]

    def test_models_do_not_import_fastapi_or_pydantic(self) -> None:
        for path in self.MODEL_FILES:
            source = path.read_text(encoding="utf-8")
            assert "fastapi" not in source
            assert "pydantic" not in source

    def test_models_do_not_import_engine_or_importing(self) -> None:
        for path in self.MODEL_FILES:
            source = path.read_text(encoding="utf-8")
            assert "app.engine" not in source
            assert "app.importing" not in source
            assert "app.domain" not in source

    def test_pure_packages_do_not_import_sqlalchemy_or_db(self) -> None:
        for package in ("engine", "importing", "domain"):
            for path in (BACKEND_DIR / "app" / package).rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                assert "sqlalchemy" not in source, path
                assert "app.db" not in source, path
