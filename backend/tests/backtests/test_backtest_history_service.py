"""Tests for the backtest history service (list/detail/rename/delete)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from app.backtests.history import (
    delete_owned_backtest,
    get_owned_backtest,
    list_owned_backtests,
    rename_owned_backtest,
)
from app.backtests.persistence import persist_completed_run
from app.db import Base
from app.db.models import (
    BacktestEvent,
    BacktestRun,
    DailyEquity,
    Dataset,
    EventEquity,
    PriceBar,
    Trade,
    User,
    ZoneEventRecord,
)
from app.db.session import create_database_engine, create_session_factory
from app.domain.enums import DataMode, ValueMode
from app.domain.models import Bar
from app.engine import (
    BacktestConfig,
    CommissionConfig,
    ExecutionConfig,
    SlippageConfig,
    TickSizeConfig,
    ValueConfig,
    run_backtest,
)
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
START = date(2026, 1, 5)
CHILD_TABLES = ("trades", "zone_events", "daily_equity", "event_equity", "backtest_events")


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'history_svc.db'}")
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


class QueryRecorder:
    """Records SQL statements issued against the engine."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.statements: list[str] = []

    def __enter__(self) -> "QueryRecorder":
        sa_event.listen(self.engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *args: object) -> None:
        sa_event.remove(self.engine, "before_cursor_execute", self._record)

    def _record(self, conn: object, cursor: object, statement: str, *args: object) -> None:
        self.statements.append(statement)

    @property
    def selects(self) -> list[str]:
        return [s for s in self.statements if s.lstrip().upper().startswith("SELECT")]


def make_user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="hash")
    session.add(user)
    session.commit()
    return user


def make_dataset(session: Session, user: User, name: str = "history-ds") -> Dataset:
    dataset = Dataset(
        user_id=user.id,
        name=name,
        source_type="CSV",
        original_filename=f"{name}.csv",
        security_name=None,
        security_code=None,
        data_mode="CLOSE_ONLY",
        start_date=START,
        end_date=START + timedelta(days=2),
        row_count=3,
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"bad_rows": 0},
    )
    for offset, close in enumerate(["10", "7", "10"]):
        PriceBar(dataset=dataset, date=START + timedelta(days=offset), close=Decimal(close))
    session.add(dataset)
    session.commit()
    return dataset


def make_run(
    session: Session,
    user: User,
    dataset: Dataset,
    name: str,
    *,
    status: str = "COMPLETED",
    created_at: datetime | None = None,
    **overrides: Any,
) -> BacktestRun:
    fields: dict[str, Any] = {
        "user_id": user.id,
        "dataset_id": dataset.id,
        "name": name,
        "status": status,
        "configuration": {"grid_step": {"mode": "FIXED", "value": "1"}},
        "ohlc_path_mode": None,
        "start_date": START,
        "end_date": START + timedelta(days=2),
        "result_metrics": {"grid_levels": ["8"]} if status == "COMPLETED" else None,
        "error_message": None if status == "COMPLETED" else "engine failure",
    }
    fields.update(overrides)
    run = BacktestRun(**fields)
    if created_at is not None:
        run.created_at = created_at
    session.add(run)
    session.commit()
    return run


def make_run_with_children(session: Session, user: User, dataset: Dataset) -> BacktestRun:
    """A real engine result (executed+skipped trades, zone events) persisted."""
    zero = CommissionConfig(
        rate_enabled=False,
        rate=Decimal("0"),
        minimum_enabled=False,
        minimum=Decimal("0"),
        fixed_enabled=False,
        fixed=Decimal("0"),
    )
    no_slip = SlippageConfig(mode=ValueMode.FIXED, value=Decimal("0"))
    config = BacktestConfig(
        data_mode=DataMode.CLOSE_ONLY,
        ohlc_path_mode=None,
        baseline_override=None,
        a_distance=ValueConfig(mode=ValueMode.FIXED, value=Decimal("2")),
        c_distance=ValueConfig(mode=ValueMode.FIXED, value=Decimal("4")),
        grid_step=ValueConfig(mode=ValueMode.FIXED, value=Decimal("1")),
        execution=ExecutionConfig(
            lot_size=1,
            trade_lots=1,
            buy_slippage=no_slip,
            sell_slippage=no_slip,
            buy_commission=zero,
            sell_commission=zero,
            tick_size=TickSizeConfig(enabled=False),
        ),
        initial_cash=Decimal("9"),
        initial_shares=0,
        annual_risk_free_rate=Decimal("0"),
    )
    bars = [
        Bar(date=START + timedelta(days=offset), close=Decimal(close))
        for offset, close in enumerate(["10", "7", "10"])
    ]
    result = run_backtest(bars, config)
    run = persist_completed_run(
        session,
        user_id=user.id,
        dataset=dataset,
        name="run with children",
        configuration_json={"c": True},
        ohlc_path_mode=None,
        result=result,
        completed_at=NOW,
    )
    session.commit()
    return run


def count(session: Session, model: type) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


def forbid_commit(session: Session) -> None:
    def _fail() -> None:
        raise AssertionError("read operation must not commit")

    session.commit = _fail  # type: ignore[method-assign]


class TestList:
    def test_empty_list(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        page = list_owned_backtests(session, owner_user_id=user.id)
        assert page.items == []
        assert page.total == 0

    def test_owned_only_with_deterministic_order(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        dataset_a = make_dataset(session, alice, "ds-a")
        dataset_b = make_dataset(session, bob, "ds-b")
        older = make_run(session, alice, dataset_a, "older", created_at=datetime(2026, 1, 1, 10, 0))
        tied_low = make_run(
            session, alice, dataset_a, "tied-low", created_at=datetime(2026, 1, 2, 10, 0)
        )
        tied_high = make_run(
            session, alice, dataset_a, "tied-high", created_at=datetime(2026, 1, 2, 10, 0)
        )
        make_run(session, bob, dataset_b, "foreign")

        page = list_owned_backtests(session, owner_user_id=alice.id)
        assert [run.id for run, _ in page.items] == [tied_high.id, tied_low.id, older.id]
        assert page.total == 3
        assert all(name == "ds-a" for _, name in page.items)

    def test_search_is_case_insensitive_substring(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        target = make_run(session, user, dataset, "Grid Alpha 2%")
        make_run(session, user, dataset, "unrelated")
        page = list_owned_backtests(session, owner_user_id=user.id, search="grid alpha")
        assert [run.id for run, _ in page.items] == [target.id]
        assert page.total == 1

    def test_whitespace_search_means_no_filter(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        make_run(session, user, dataset, "one")
        make_run(session, user, dataset, "two")
        page = list_owned_backtests(session, owner_user_id=user.id, search="   ")
        assert page.total == 2

    def test_dataset_and_status_filters_combined(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        first = make_dataset(session, user, "first")
        second = make_dataset(session, user, "second")
        completed = make_run(session, user, first, "completed run")
        make_run(session, user, first, "failed run", status="FAILED")
        make_run(session, user, second, "other dataset run")

        by_dataset = list_owned_backtests(session, owner_user_id=user.id, dataset_id=first.id)
        assert by_dataset.total == 2
        by_status = list_owned_backtests(session, owner_user_id=user.id, status="FAILED")
        assert by_status.total == 1
        combined = list_owned_backtests(
            session, owner_user_id=user.id, dataset_id=first.id, status="COMPLETED"
        )
        assert [run.id for run, _ in combined.items] == [completed.id]

    def test_total_counts_before_pagination_and_slicing(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        runs = [
            make_run(
                session,
                user,
                dataset,
                f"run-{index}",
                created_at=datetime(2026, 1, 1, 10, 0) + timedelta(hours=index),
            )
            for index in range(5)
        ]
        page = list_owned_backtests(session, owner_user_id=user.id, limit=2, offset=1)
        assert page.total == 5
        assert page.limit == 2
        assert page.offset == 1
        # Newest first: run-4, run-3, run-2, ... → offset 1, limit 2.
        assert [run.id for run, _ in page.items] == [runs[3].id, runs[2].id]

    def test_list_does_not_commit_load_children_or_n_plus_one(
        self, engine: Engine, session: Session
    ) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        make_run_with_children(session, user, dataset)
        make_run(session, user, dataset, "plain")
        owner_id = user.id
        session.expire_all()
        forbid_commit(session)
        with QueryRecorder(engine) as recorder:
            page = list_owned_backtests(session, owner_user_id=owner_id)
        assert page.total == 2
        assert len(recorder.selects) == 2  # one count + one item query, no N+1
        combined_sql = "\n".join(recorder.selects).lower()
        for child_table in CHILD_TABLES:
            assert f"from {child_table}" not in combined_sql
            assert f"join {child_table}" not in combined_sql


class TestDetail:
    def test_owned_found_with_dataset_and_exact_json(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        created = make_run(session, user, dataset, "detail run")
        session.expire_all()
        run = get_owned_backtest(session, backtest_id=created.id, owner_user_id=user.id)
        assert run is not None
        assert run.dataset.name == "history-ds"
        assert run.configuration == {"grid_step": {"mode": "FIXED", "value": "1"}}
        assert run.result_metrics == {"grid_levels": ["8"]}

    def test_missing_and_wrong_owner_return_none(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        dataset = make_dataset(session, bob)
        run = make_run(session, bob, dataset, "bobs run")
        assert get_owned_backtest(session, backtest_id=99999, owner_user_id=alice.id) is None
        assert get_owned_backtest(session, backtest_id=run.id, owner_user_id=alice.id) is None

    def test_failed_run_supported(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        failed = make_run(session, user, dataset, "failed", status="FAILED")
        run = get_owned_backtest(session, backtest_id=failed.id, owner_user_id=user.id)
        assert run is not None
        assert run.result_metrics is None
        assert run.error_message == "engine failure"

    def test_detail_queries_no_result_series(self, engine: Engine, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        run = make_run_with_children(session, user, dataset)
        run_id = run.id
        owner_id = user.id
        session.expire_all()
        forbid_commit(session)
        with QueryRecorder(engine) as recorder:
            loaded = get_owned_backtest(session, backtest_id=run_id, owner_user_id=owner_id)
            assert loaded is not None
            _ = loaded.dataset.name  # joined eagerly, no extra query
        assert len(recorder.selects) == 1
        combined_sql = "\n".join(recorder.selects).lower()
        for child_table in CHILD_TABLES:
            assert f"from {child_table}" not in combined_sql
        assert "price_bars" not in combined_sql


class TestRename:
    def test_rename_modifies_name_only_and_commits_once(
        self, session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        run = make_run_with_children(session, user, dataset)
        before_children = count(session, BacktestEvent)
        before_configuration = dict(run.configuration)
        before_metrics = run.result_metrics

        commits: list[int] = []
        original_commit = session.commit

        def counting_commit() -> None:
            commits.append(1)
            original_commit()

        session.commit = counting_commit  # type: ignore[method-assign]
        renamed = rename_owned_backtest(
            session, backtest_id=run.id, owner_user_id=user.id, name="Renamed Run"
        )
        assert renamed is not None
        assert renamed.name == "Renamed Run"
        assert len(commits) == 1

        with session_factory() as fresh:
            stored = fresh.get(BacktestRun, run.id)
            assert stored is not None
            assert stored.name == "Renamed Run"
            assert stored.configuration == before_configuration
            assert stored.result_metrics == before_metrics
            assert (
                fresh.execute(sa.select(sa.func.count()).select_from(BacktestEvent)).scalar_one()
                == before_children
            )

    def test_missing_and_wrong_owner_return_none(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        dataset = make_dataset(session, bob)
        run = make_run(session, bob, dataset, "bobs")
        assert (
            rename_owned_backtest(
                session, backtest_id=run.id, owner_user_id=alice.id, name="stolen"
            )
            is None
        )
        assert (
            rename_owned_backtest(session, backtest_id=987654, owner_user_id=alice.id, name="ghost")
            is None
        )
        session.expire_all()
        assert run.name == "bobs"

    def test_rollback_on_commit_failure(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset, "original")

        def failing_commit() -> None:
            raise RuntimeError("db down")

        monkeypatch.setattr(session, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            rename_owned_backtest(session, backtest_id=run.id, owner_user_id=user.id, name="never")
        with session_factory() as fresh:
            stored = fresh.get(BacktestRun, run.id)
            assert stored is not None
            assert stored.name == "original"


class TestDelete:
    def test_delete_cascades_and_spares_everything_else(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        dataset = make_dataset(session, alice)
        bob_dataset = make_dataset(session, bob, "bob-ds")
        target = make_run_with_children(session, alice, dataset)
        keeper = make_run(session, alice, dataset, "keeper")
        foreign = make_run(session, bob, bob_dataset, "foreign")

        commits: list[int] = []
        original_commit = session.commit

        def counting_commit() -> None:
            commits.append(1)
            original_commit()

        session.commit = counting_commit  # type: ignore[method-assign]
        assert delete_owned_backtest(session, backtest_id=target.id, owner_user_id=alice.id)
        assert len(commits) == 1

        for model in (BacktestEvent, Trade, ZoneEventRecord, EventEquity, DailyEquity):
            assert count(session, model) == 0
        remaining = set(session.execute(sa.select(BacktestRun.id)).scalars())
        assert remaining == {keeper.id, foreign.id}
        assert count(session, Dataset) == 2
        assert count(session, PriceBar) == 6
        assert count(session, User) == 2

    def test_missing_wrong_owner_and_repeat_return_false(self, session: Session) -> None:
        alice = make_user(session, "alice@example.com")
        bob = make_user(session, "bob@example.com")
        dataset = make_dataset(session, bob)
        run = make_run(session, bob, dataset, "bobs")
        assert delete_owned_backtest(session, backtest_id=run.id, owner_user_id=alice.id) is False
        assert delete_owned_backtest(session, backtest_id=555555, owner_user_id=alice.id) is False
        assert delete_owned_backtest(session, backtest_id=run.id, owner_user_id=bob.id) is True
        assert delete_owned_backtest(session, backtest_id=run.id, owner_user_id=bob.id) is False

    def test_deleted_run_unblocks_dataset_deletion(self, session: Session) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        run = make_run_with_children(session, user, dataset)
        with pytest.raises(sa.exc.IntegrityError):
            session.execute(sa.text("DELETE FROM datasets WHERE id = :id"), {"id": dataset.id})
        session.rollback()
        assert delete_owned_backtest(session, backtest_id=run.id, owner_user_id=user.id)
        session.delete(session.get(Dataset, dataset.id))
        session.commit()
        assert count(session, Dataset) == 0

    def test_no_manual_child_delete_loop(self) -> None:
        source = (
            Path(__file__).resolve().parents[2] / "app" / "backtests" / "history.py"
        ).read_text(encoding="utf-8")
        assert source.count("session.delete(") == 1  # the run itself only
        for child in ("Trade", "ZoneEventRecord", "EventEquity", "DailyEquity", "BacktestEvent"):
            assert child not in source

    def test_rollback_on_commit_failure(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = make_user(session, "a@example.com")
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset, "survivor")

        def failing_commit() -> None:
            raise RuntimeError("db down")

        monkeypatch.setattr(session, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            delete_owned_backtest(session, backtest_id=run.id, owner_user_id=user.id)
        with session_factory() as fresh:
            assert fresh.get(BacktestRun, run.id) is not None
