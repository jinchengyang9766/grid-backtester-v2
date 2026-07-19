"""Unit tests for the dataset management service (list/detail/delete)."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from app.datasets.management import (
    DatasetInUseError,
    delete_owned_dataset,
    get_owned_dataset,
    is_foreign_key_violation,
    list_owned_datasets,
)
from app.db import Base
from app.db.models import Dataset, PriceBar, User
from app.db.session import create_database_engine, create_session_factory
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'management_test.db'}")
    Base.metadata.create_all(database_engine)
    yield database_engine
    database_engine.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def make_user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="hash")
    session.add(user)
    session.commit()
    return user


def make_dataset(
    session: Session,
    user: User,
    name: str,
    *,
    created_at: datetime | None = None,
    bar_count: int = 0,
) -> Dataset:
    dataset = Dataset(
        user_id=user.id,
        name=name,
        source_type="CSV",
        original_filename=f"{name}.csv",
        security_name=None,
        security_code=None,
        data_mode="CLOSE_ONLY",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1) + timedelta(days=max(bar_count - 1, 0)),
        row_count=bar_count,
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"final_row_count": bar_count, "bad_rows": 0},
    )
    if created_at is not None:
        dataset.created_at = created_at
    session.add(dataset)
    for offset in range(bar_count):
        session.add(
            PriceBar(
                dataset=dataset,
                date=date(2024, 1, 1) + timedelta(days=offset),
                close=Decimal("1.50000000"),
            )
        )
    session.commit()
    return dataset


def forbid_commit(session: Session) -> None:
    def _fail() -> None:
        raise AssertionError("this operation must not commit")

    session.commit = _fail  # type: ignore[method-assign]


class TestList:
    def test_no_datasets_returns_empty_tuple(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        assert list_owned_datasets(session, owner_user_id=user.id) == ()

    def test_only_owned_datasets_returned(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        owned = make_dataset(session, alice, "mine")
        make_dataset(session, bob, "theirs")
        result = list_owned_datasets(session, owner_user_id=alice.id)
        assert [dataset.id for dataset in result] == [owned.id]

    def test_multiple_owned_newest_first(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        older = make_dataset(session, user, "older", created_at=datetime(2026, 1, 1, 10, 0))
        newer = make_dataset(session, user, "newer", created_at=datetime(2026, 1, 2, 10, 0))
        middle = make_dataset(session, user, "middle", created_at=datetime(2026, 1, 1, 18, 0))
        result = list_owned_datasets(session, owner_user_id=user.id)
        assert [dataset.id for dataset in result] == [newer.id, middle.id, older.id]

    def test_equal_created_at_breaks_ties_by_id_desc(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        same_moment = datetime(2026, 1, 1, 12, 0)
        first = make_dataset(session, user, "first", created_at=same_moment)
        second = make_dataset(session, user, "second", created_at=same_moment)
        result = list_owned_datasets(session, owner_user_id=user.id)
        assert [dataset.id for dataset in result] == [second.id, first.id]

    def test_price_bars_are_not_loaded(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        make_dataset(session, user, "with-bars", bar_count=3)
        session.expire_all()
        (dataset,) = list_owned_datasets(session, owner_user_id=user.id)
        assert "price_bars" in sa.inspect(dataset).unloaded

    def test_list_does_not_mutate_or_commit(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        make_dataset(session, user, "one")
        forbid_commit(session)
        list_owned_datasets(session, owner_user_id=user.id)
        assert not session.dirty
        assert not session.new
        assert not session.deleted


class TestDetail:
    def test_owned_dataset_found_with_structured_json(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        created = make_dataset(session, user, "mine")
        session.expire_all()
        found = get_owned_dataset(session, dataset_id=created.id, owner_user_id=user.id)
        assert found is not None
        assert found.column_mapping == {"date": "Date", "close": "Close"}
        assert found.cleaning_summary == {"final_row_count": 0, "bad_rows": 0}
        assert found.security_name is None
        assert found.security_code is None

    def test_missing_dataset_returns_none(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        assert get_owned_dataset(session, dataset_id=12345, owner_user_id=user.id) is None

    def test_other_users_dataset_returns_none(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        theirs = make_dataset(session, bob, "theirs")
        assert get_owned_dataset(session, dataset_id=theirs.id, owner_user_id=alice.id) is None

    def test_detail_does_not_mutate_or_commit(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        created = make_dataset(session, user, "mine")
        forbid_commit(session)
        get_owned_dataset(session, dataset_id=created.id, owner_user_id=user.id)
        assert not session.dirty
        assert not session.new
        assert not session.deleted


class TestDelete:
    def test_owned_delete_cascades_to_price_bars_only_for_that_dataset(
        self, session: Session
    ) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        target = make_dataset(session, alice, "target", bar_count=3)
        keeper = make_dataset(session, alice, "keeper", bar_count=2)
        foreign = make_dataset(session, bob, "foreign", bar_count=4)

        assert delete_owned_dataset(session, dataset_id=target.id, owner_user_id=alice.id)

        remaining_ids = set(session.execute(sa.select(Dataset.id)).scalars())
        assert remaining_ids == {keeper.id, foreign.id}
        remaining_bars = session.execute(
            sa.select(sa.func.count()).select_from(PriceBar)
        ).scalar_one()
        assert remaining_bars == 2 + 4
        assert session.execute(sa.select(sa.func.count()).select_from(User)).scalar_one() == 2

    def test_wrong_owner_and_missing_behave_as_not_found(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        theirs = make_dataset(session, bob, "theirs", bar_count=1)
        assert delete_owned_dataset(session, dataset_id=theirs.id, owner_user_id=alice.id) is False
        assert delete_owned_dataset(session, dataset_id=99999, owner_user_id=alice.id) is False
        # Bob's dataset untouched by the wrong-owner attempt.
        assert session.execute(sa.select(sa.func.count()).select_from(Dataset)).scalar_one() == 1

    def test_repeated_delete_is_not_found(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user, "once", bar_count=1)
        assert delete_owned_dataset(session, dataset_id=dataset.id, owner_user_id=user.id)
        assert delete_owned_dataset(session, dataset_id=dataset.id, owner_user_id=user.id) is False

    def test_successful_delete_commits_exactly_once(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user, "counted")
        commits: list[int] = []
        original_commit = session.commit

        def counting_commit() -> None:
            commits.append(1)
            original_commit()

        session.commit = counting_commit  # type: ignore[method-assign]
        assert delete_owned_dataset(session, dataset_id=dataset.id, owner_user_id=user.id)
        assert len(commits) == 1

    def test_no_manual_price_bar_deletion_loop(self) -> None:
        management_path = Path(__file__).resolve().parents[2] / "app" / "datasets" / "management.py"
        source = management_path.read_text(encoding="utf-8")
        # Cascade only: the module never imports or queries PriceBar rows.
        import_lines = [line for line in source.splitlines() if "import" in line]
        assert all("PriceBar" not in line for line in import_lines)
        assert "delete(PriceBar" not in source
        assert source.count("session.delete(") == 1  # the Dataset itself only


def create_restricting_reference(engine: Engine, dataset_id: int) -> None:
    """Test-only restricted reference table inside the isolated database.

    Simulates the future backtest_runs.dataset_id ON DELETE RESTRICT
    foreign key; never an ORM model, never in Base.metadata or Alembic.
    """
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS test_only_refs ("
            "id INTEGER PRIMARY KEY, "
            "dataset_id INTEGER NOT NULL "
            "REFERENCES datasets(id) ON DELETE RESTRICT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO test_only_refs (dataset_id) VALUES (?)", (dataset_id,)
        )


class TestRestrictedDelete:
    def test_restricted_delete_raises_rolls_back_and_keeps_rows(
        self, engine: Engine, session: Session
    ) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user, "referenced", bar_count=2)
        create_restricting_reference(engine, dataset.id)

        with pytest.raises(DatasetInUseError):
            delete_owned_dataset(session, dataset_id=dataset.id, owner_user_id=user.id)

        # Rolled back: the dataset and all bars remain, session stays usable.
        assert session.execute(sa.select(sa.func.count()).select_from(Dataset)).scalar_one() == 1
        assert session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one() == 2
        assert get_owned_dataset(session, dataset_id=dataset.id, owner_user_id=user.id) is not None

    def test_unrelated_integrity_error_propagates_unmapped(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user, "victim")
        unrelated = IntegrityError(
            "UPDATE ...", {}, Exception("UNIQUE constraint failed: users.email")
        )

        def failing_commit() -> None:
            raise unrelated

        monkeypatch.setattr(session, "commit", failing_commit)
        with pytest.raises(IntegrityError):
            delete_owned_dataset(session, dataset_id=dataset.id, owner_user_id=user.id)


class TestForeignKeyRecognition:
    def test_postgresql_sqlstate_23503_recognized(self) -> None:
        class FakeForeignKeyError(Exception):
            sqlstate = "23503"

        error = IntegrityError("DELETE FROM datasets", {}, FakeForeignKeyError())
        assert is_foreign_key_violation(error) is True

    def test_postgresql_pgcode_23503_recognized(self) -> None:
        class FakePsycopg2Error(Exception):
            pgcode = "23503"

        error = IntegrityError("DELETE FROM datasets", {}, FakePsycopg2Error())
        assert is_foreign_key_violation(error) is True

    def test_postgresql_unique_violation_not_recognized(self) -> None:
        class FakeUniqueError(Exception):
            sqlstate = "23505"

        error = IntegrityError("INSERT ...", {}, FakeUniqueError())
        assert is_foreign_key_violation(error) is False

    def test_sqlite_foreign_key_message_recognized(self) -> None:
        error = IntegrityError("DELETE ...", {}, Exception("FOREIGN KEY constraint failed"))
        assert is_foreign_key_violation(error) is True

    def test_sqlite_unique_message_not_recognized(self) -> None:
        error = IntegrityError("INSERT ...", {}, Exception("UNIQUE constraint failed: users.email"))
        assert is_foreign_key_violation(error) is False
