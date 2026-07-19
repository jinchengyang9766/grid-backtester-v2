"""Tests for the backtest persistence models (SPEC Sections 23.4-23.9)."""

import datetime
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from app.db import Base
from app.db.models import (
    BacktestEvent,
    BacktestRun,
    DailyEquity,
    Dataset,
    EventEquity,
    Trade,
    User,
    ZoneEventRecord,
)
from app.db.session import create_database_engine, create_session_factory
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

APPLICATION_TABLES = {
    "users",
    "datasets",
    "price_bars",
    "backtest_runs",
    "backtest_events",
    "trades",
    "zone_events",
    "daily_equity",
    "event_equity",
}

RUNS_TABLE = cast(sa.Table, BacktestRun.__table__)
EVENTS_TABLE = cast(sa.Table, BacktestEvent.__table__)
TRADES_TABLE = cast(sa.Table, Trade.__table__)
ZONE_EVENTS_TABLE = cast(sa.Table, ZoneEventRecord.__table__)
DAILY_EQUITY_TABLE = cast(sa.Table, DailyEquity.__table__)
EVENT_EQUITY_TABLE = cast(sa.Table, EventEquity.__table__)


def _pg_table_ddl(table: sa.Table) -> str:
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'bt_models.db'}")
    Base.metadata.create_all(database_engine)
    yield database_engine
    database_engine.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    factory = create_session_factory(engine)
    with factory() as db_session:
        yield db_session


def make_user(session: Session, email: str = "runner@example.com") -> User:
    user = User(email=email, password_hash="hash")
    session.add(user)
    session.commit()
    return user


def make_dataset(session: Session, user: User) -> Dataset:
    dataset = Dataset(
        user_id=user.id,
        name="ds",
        source_type="CSV",
        original_filename="ds.csv",
        security_name=None,
        security_code=None,
        data_mode="CLOSE_ONLY",
        start_date=datetime.date(2026, 1, 5),
        end_date=datetime.date(2026, 1, 6),
        row_count=2,
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"bad_rows": 0},
    )
    session.add(dataset)
    session.commit()
    return dataset


def make_run(session: Session, user: User, dataset: Dataset, **overrides: Any) -> BacktestRun:
    fields: dict[str, Any] = {
        "user_id": user.id,
        "dataset_id": dataset.id,
        "name": "Test Run",
        "status": "COMPLETED",
        "configuration": {"initial_cash": "100000.00", "grid_step": {"mode": "PERCENT"}},
        "ohlc_path_mode": None,
        "start_date": datetime.date(2026, 1, 5),
        "end_date": datetime.date(2026, 1, 6),
        "result_metrics": {"net_profit": "12.5"},
    }
    fields.update(overrides)
    run = BacktestRun(**fields)
    session.add(run)
    session.commit()
    return run


def make_event(
    session: Session,
    run: BacktestRun,
    sequence: int,
    event_type: str = "TRADE",
    day: datetime.date = datetime.date(2026, 1, 5),
) -> BacktestEvent:
    event = BacktestEvent(
        backtest_run_id=run.id,
        event_sequence=sequence,
        event_type=event_type,
        date=day,
        market_price=Decimal("1.05000000"),
    )
    session.add(event)
    session.commit()
    return event


def executed_trade_fields(event: BacktestEvent) -> dict[str, Any]:
    return {
        "event_id": event.id,
        "side": "BUY",
        "grid_price": Decimal("1.05000000"),
        "execution_price": Decimal("1.05100000"),
        "shares": 100,
        "notional": Decimal("105.10000000"),
        "commission": Decimal("5.00000000"),
        "slippage_cost": Decimal("0.10000000"),
        "cash_after": Decimal("894.90000000"),
        "shares_after": 100,
        "equity_after": Decimal("999.90000000"),
        "status": "EXECUTED",
        "skip_reason": None,
    }


class TestRegistration:
    def test_metadata_contains_exactly_nine_application_tables(self) -> None:
        assert set(Base.metadata.tables) == APPLICATION_TABLES

    def test_public_imports(self) -> None:
        import app.db

        assert app.db.BacktestRun is BacktestRun
        assert app.db.BacktestEvent is BacktestEvent
        assert app.db.Trade is Trade
        assert app.db.ZoneEventRecord is ZoneEventRecord
        assert app.db.DailyEquity is DailyEquity
        assert app.db.EventEquity is EventEquity

    def test_no_optimization_tables(self) -> None:
        assert not any(name.startswith("optimization") for name in Base.metadata.tables)


class TestBacktestRun:
    def test_insert_read_and_json_round_trip(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        make_run(session, user, dataset)
        session.expire_all()
        run = session.execute(sa.select(BacktestRun)).scalar_one()
        assert run.configuration == {
            "initial_cash": "100000.00",
            "grid_step": {"mode": "PERCENT"},
        }
        assert run.result_metrics == {"net_profit": "12.5"}
        assert run.name == "Test Run"

    def test_ids_autoincrement(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        first = make_run(session, user, dataset)
        second = make_run(session, user, dataset)
        assert second.id == first.id + 1

    def test_nullable_fields_accepted(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = make_run(
            session, user, dataset, result_metrics=None, error_message=None, completed_at=None
        )
        assert run.result_metrics is None
        assert run.error_message is None
        assert run.completed_at is None

    @pytest.mark.parametrize("status_value", ["PENDING", "RUNNING", "COMPLETED", "FAILED"])
    def test_all_statuses_accepted(self, session: Session, status_value: str) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        assert make_run(session, user, dataset, status=status_value).status == status_value

    def test_invalid_status_rejected(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        with pytest.raises(IntegrityError):
            make_run(session, user, dataset, status="DONE")
        session.rollback()

    def test_status_defaults_to_pending(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = BacktestRun(
            user_id=user.id,
            dataset_id=dataset.id,
            name="defaulted",
            configuration={},
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 1, 6),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        assert run.status == "PENDING"

    @pytest.mark.parametrize("mode", [None, "HIGH_FIRST", "LOW_FIRST", "AUTO"])
    def test_path_modes_accepted(self, session: Session, mode: str | None) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        assert make_run(session, user, dataset, ohlc_path_mode=mode).ohlc_path_mode == mode

    def test_invalid_path_mode_rejected(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        with pytest.raises(IntegrityError):
            make_run(session, user, dataset, ohlc_path_mode="RANDOM")
        session.rollback()

    def test_timestamps_and_relationships(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset)
        session.refresh(run)
        assert isinstance(run.created_at, datetime.datetime)
        assert run.user is user
        assert run.dataset is dataset
        assert user.backtest_runs == [run]
        assert dataset.backtest_runs == [run]


class TestBacktestEvent:
    def test_sequence_unique_across_event_kinds_in_one_run(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset)
        make_event(session, run, sequence=1, event_type="TRADE")
        with pytest.raises(IntegrityError):
            make_event(session, run, sequence=1, event_type="ZONE_EVENT")
        session.rollback()

    def test_same_sequence_allowed_in_different_runs(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run_a = make_run(session, user, dataset)
        run_b = make_run(session, user, dataset)
        make_event(session, run_a, sequence=1)
        make_event(session, run_b, sequence=1)

    def test_ordered_relationship_and_decimal_price(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset)
        make_event(session, run, sequence=2, event_type="ZONE_EVENT")
        make_event(session, run, sequence=1, event_type="TRADE")
        session.expire_all()
        loaded = session.execute(sa.select(BacktestRun)).scalar_one()
        assert [event.event_sequence for event in loaded.events] == [1, 2]
        assert isinstance(loaded.events[0].market_price, Decimal)

    def test_invalid_event_type_rejected(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset)
        with pytest.raises(IntegrityError):
            make_event(session, run, sequence=1, event_type="EQUITY")
        session.rollback()


class TestTrade:
    def test_executed_trade_round_trips_decimals(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        event = make_event(session, make_run(session, user, dataset), sequence=1)
        session.add(Trade(**executed_trade_fields(event)))
        session.commit()
        session.expire_all()
        trade = session.execute(sa.select(Trade)).scalar_one()
        assert isinstance(trade.execution_price, Decimal)
        assert trade.notional == Decimal("105.10000000")
        assert trade.event.event_sequence == 1

    @pytest.mark.parametrize(
        "skip_reason",
        ["INSUFFICIENT_CASH", "INSUFFICIENT_SHARES", "INSUFFICIENT_CASH_FOR_COMMISSION"],
    )
    def test_skipped_trade_nullable_fields_and_reasons(
        self, session: Session, skip_reason: str
    ) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        event = make_event(session, make_run(session, user, dataset), sequence=1)
        fields = executed_trade_fields(event)
        fields.update(
            status="SKIPPED",
            skip_reason=skip_reason,
            execution_price=None,
            notional=None,
            commission=None,
            slippage_cost=None,
        )
        session.add(Trade(**fields))
        session.commit()
        trade = session.execute(sa.select(Trade)).scalar_one()
        assert trade.execution_price is None
        assert trade.skip_reason == skip_reason

    @pytest.mark.parametrize(
        ("field", "value"),
        [("side", "SHORT"), ("status", "PARTIAL"), ("skip_reason", "OUT_OF_MONEY")],
    )
    def test_invalid_enumerations_rejected(self, session: Session, field: str, value: str) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        event = make_event(session, make_run(session, user, dataset), sequence=1)
        fields = executed_trade_fields(event)
        fields[field] = value
        session.add(Trade(**fields))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_event_id_unique(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        event = make_event(session, make_run(session, user, dataset), sequence=1)
        session.add(Trade(**executed_trade_fields(event)))
        session.commit()
        session.add(Trade(**executed_trade_fields(event)))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_no_denormalized_columns(self) -> None:
        assert set(TRADES_TABLE.c.keys()) == {
            "id",
            "event_id",
            "side",
            "grid_price",
            "execution_price",
            "shares",
            "notional",
            "commission",
            "slippage_cost",
            "cash_after",
            "shares_after",
            "equity_after",
            "status",
            "skip_reason",
        }


class TestZoneEventRecord:
    @pytest.mark.parametrize(
        "zone_type",
        ["ENTER_C_ZONE", "EXIT_C_ZONE", "OUTSIDE_C_BOUNDARY", "RETURN_INSIDE_C_BOUNDARY"],
    )
    def test_all_types_accepted(self, session: Session, zone_type: str) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        event = make_event(
            session, make_run(session, user, dataset), sequence=1, event_type="ZONE_EVENT"
        )
        session.add(ZoneEventRecord(event_id=event.id, event_type=zone_type, price=Decimal("1.05")))
        session.commit()

    def test_invalid_type_rejected(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        event = make_event(
            session, make_run(session, user, dataset), sequence=1, event_type="ZONE_EVENT"
        )
        session.add(
            ZoneEventRecord(event_id=event.id, event_type="LEFT_MARKET", price=Decimal("1"))
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_event_id_unique_and_no_denormalized_columns(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        event = make_event(
            session, make_run(session, user, dataset), sequence=1, event_type="ZONE_EVENT"
        )
        session.add(
            ZoneEventRecord(event_id=event.id, event_type="ENTER_C_ZONE", price=Decimal("1"))
        )
        session.commit()
        session.add(
            ZoneEventRecord(event_id=event.id, event_type="EXIT_C_ZONE", price=Decimal("1"))
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert set(ZONE_EVENTS_TABLE.c.keys()) == {"id", "event_id", "event_type", "price"}


class TestDailyEquity:
    def make_row(self, run: BacktestRun, day: datetime.date, **overrides: Any) -> DailyEquity:
        fields: dict[str, Any] = {
            "backtest_run_id": run.id,
            "date": day,
            "close": Decimal("1.05000000"),
            "cash": Decimal("500.00000000"),
            "shares": 100,
            "equity": Decimal("605.00000000"),
            "drawdown": Decimal("-0.01000000"),
            "zone_at_close": "IN_A",
        }
        fields.update(overrides)
        return DailyEquity(**fields)

    def test_unique_per_run_and_date(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset)
        day = datetime.date(2026, 1, 5)
        session.add(self.make_row(run, day))
        session.commit()
        session.add(self.make_row(run, day))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_same_date_allowed_for_different_runs(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run_a = make_run(session, user, dataset)
        run_b = make_run(session, user, dataset)
        day = datetime.date(2026, 1, 5)
        session.add_all([self.make_row(run_a, day), self.make_row(run_b, day)])
        session.commit()

    @pytest.mark.parametrize("zone", ["IN_A", "IN_C", "OUTSIDE_C"])
    def test_zones_and_decimals(self, session: Session, zone: str) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset)
        session.add(self.make_row(run, datetime.date(2026, 1, 5), zone_at_close=zone))
        session.commit()
        session.expire_all()
        row = session.execute(sa.select(DailyEquity)).scalar_one()
        assert isinstance(row.equity, Decimal)
        assert isinstance(row.drawdown, Decimal)

    def test_invalid_zone_rejected(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        run = make_run(session, user, dataset)
        session.add(self.make_row(run, datetime.date(2026, 1, 5), zone_at_close="IN_B"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_no_event_id_column(self) -> None:
        assert "event_id" not in DAILY_EQUITY_TABLE.c


class TestEventEquity:
    def test_unique_decimal_and_no_denormalized_columns(self, session: Session) -> None:
        user = make_user(session)
        dataset = make_dataset(session, user)
        event = make_event(session, make_run(session, user, dataset), sequence=1)
        session.add(
            EventEquity(
                event_id=event.id,
                cash=Decimal("500.00000000"),
                shares=100,
                equity=Decimal("605.00000000"),
            )
        )
        session.commit()
        session.expire_all()
        row = session.execute(sa.select(EventEquity)).scalar_one()
        assert isinstance(row.equity, Decimal)
        session.add(
            EventEquity(event_id=event.id, cash=Decimal("1"), shares=1, equity=Decimal("2"))
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert set(EVENT_EQUITY_TABLE.c.keys()) == {"id", "event_id", "cash", "shares", "equity"}


class TestSchemaDefinition:
    def test_foreign_key_delete_policies(self) -> None:
        policies = {
            (fk.parent.table.name, fk.parent.name): fk.ondelete
            for table in (
                RUNS_TABLE,
                EVENTS_TABLE,
                TRADES_TABLE,
                ZONE_EVENTS_TABLE,
                DAILY_EQUITY_TABLE,
                EVENT_EQUITY_TABLE,
            )
            for column in table.columns
            for fk in column.foreign_keys
        }
        assert policies == {
            ("backtest_runs", "user_id"): "CASCADE",
            ("backtest_runs", "dataset_id"): "RESTRICT",
            ("backtest_events", "backtest_run_id"): "CASCADE",
            ("trades", "event_id"): "CASCADE",
            ("zone_events", "event_id"): "CASCADE",
            ("daily_equity", "backtest_run_id"): "CASCADE",
            ("event_equity", "event_id"): "CASCADE",
        }

    def test_named_constraints_and_indexes(self) -> None:
        run_checks = {c.name for c in RUNS_TABLE.constraints if isinstance(c, sa.CheckConstraint)}
        assert {"ck_backtest_runs_status", "ck_backtest_runs_ohlc_path_mode"} <= run_checks
        event_uniques = {
            c.name for c in EVENTS_TABLE.constraints if isinstance(c, sa.UniqueConstraint)
        }
        assert "uq_backtest_events_run_sequence" in event_uniques
        assert "uq_daily_equity_run_date" in {
            c.name for c in DAILY_EQUITY_TABLE.constraints if isinstance(c, sa.UniqueConstraint)
        }
        assert {index.name for index in RUNS_TABLE.indexes} == {
            "ix_backtest_runs_user_id_created_at",
            "ix_backtest_runs_dataset_id",
        }
        assert {index.name for index in EVENTS_TABLE.indexes} == {"ix_backtest_events_run_id_date"}

    def test_timestamps_are_timezone_aware(self) -> None:
        for column in (RUNS_TABLE.c.created_at, RUNS_TABLE.c.completed_at):
            assert isinstance(column.type, sa.DateTime)
            assert column.type.timezone is True

    def test_postgresql_ddl_essentials(self) -> None:
        runs_ddl = _pg_table_ddl(RUNS_TABLE)
        assert "id BIGSERIAL NOT NULL" in runs_ddl
        assert "configuration JSONB NOT NULL" in runs_ddl
        assert "result_metrics JSONB" in runs_ddl
        assert "ON DELETE RESTRICT" in runs_ddl
        assert "ON DELETE CASCADE" in runs_ddl

        events_ddl = _pg_table_ddl(EVENTS_TABLE)
        assert "market_price NUMERIC(20, 8) NOT NULL" in events_ddl
        assert "backtest_run_id BIGINT NOT NULL" in events_ddl

        trades_ddl = _pg_table_ddl(TRADES_TABLE)
        for column in ("grid_price", "cash_after", "equity_after"):
            assert f"{column} NUMERIC(20, 8) NOT NULL" in trades_ddl
        assert "shares BIGINT NOT NULL" in trades_ddl

        daily_ddl = _pg_table_ddl(DAILY_EQUITY_TABLE)
        for column in ("close", "cash", "equity", "drawdown"):
            assert f"{column} NUMERIC(20, 8) NOT NULL" in daily_ddl

        event_equity_ddl = _pg_table_ddl(EVENT_EQUITY_TABLE)
        assert "equity NUMERIC(20, 8) NOT NULL" in event_equity_ddl


class TestArchitecture:
    MODEL_FILES = sorted(
        (Path(__file__).resolve().parents[2] / "app" / "db" / "models").glob("*.py")
    )

    def test_models_stay_framework_free(self) -> None:
        for path in self.MODEL_FILES:
            source = path.read_text(encoding="utf-8")
            for forbidden in ("fastapi", "pydantic", "app.engine", "app.importing"):
                assert forbidden not in source, f"{path} contains {forbidden!r}"
