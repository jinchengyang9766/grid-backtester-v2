"""Tests for the in-memory trades.csv and equity.csv export builders."""

import csv
import io
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from app.backtests.exports import (
    DAILY_EQUITY_CSV_HEADER,
    TRADE_CSV_HEADER,
    _render_csv,
    build_daily_equity_csv,
    build_trades_csv,
)
from app.db import Base
from app.db.models import (
    BacktestEvent,
    BacktestRun,
    DailyEquity,
    Dataset,
    Trade,
    User,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

START = date(2026, 3, 2)


@pytest.fixture()
def engine(tmp_path: Any) -> Engine:
    created = sa.create_engine(f"sqlite:///{tmp_path / 'exports.db'}")
    Base.metadata.create_all(created)
    return created


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


class CommitForbiddenError(AssertionError):
    """Raised when export code attempts to write to the database."""


def commit_forbidding_session(session_factory: sessionmaker[Session]) -> Session:
    """A session whose commit/flush raise, proving exports are read-only.

    autoflush is off so the ban catches only writes the export code itself
    attempts, not SQLAlchemy's pre-query housekeeping.
    """
    session = session_factory(autoflush=False)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise CommitForbiddenError("export builders must never write")

    session.commit = forbidden  # type: ignore[method-assign]
    session.flush = forbidden  # type: ignore[method-assign]
    return session


def seed_run(session: Session, *, name: str = "run") -> int:
    user = User(email=f"{name}@example.com", password_hash="x")
    session.add(user)
    session.flush()
    dataset = Dataset(
        user_id=user.id,
        name="数据集",
        source_type="TDX_XLS",
        original_filename="159825.xls",
        security_name="中概互联",
        security_code="159825",
        data_mode="CLOSE_ONLY",
        start_date=START,
        end_date=START + timedelta(days=2),
        row_count=3,
        column_mapping={"date": "日期"},
        cleaning_summary={"removed": 0},
    )
    session.add(dataset)
    session.flush()
    run = BacktestRun(
        user_id=user.id,
        dataset_id=dataset.id,
        name=name,
        status="COMPLETED",
        configuration={"initial_cash": "100000.00"},
        ohlc_path_mode=None,
        start_date=START,
        end_date=START + timedelta(days=2),
        result_metrics={"benchmark1": {}, "benchmark2": {}},
    )
    session.add(run)
    session.flush()
    return int(run.id)


def add_trade(
    session: Session,
    *,
    run_id: int,
    event_sequence: int,
    event_date: date,
    status: str = "EXECUTED",
    side: str = "BUY",
    skip_reason: str | None = None,
) -> Trade:
    event = BacktestEvent(
        backtest_run_id=run_id,
        event_sequence=event_sequence,
        event_type="TRADE",
        date=event_date,
        market_price=Decimal("10.00000000"),
    )
    session.add(event)
    session.flush()
    executed = status == "EXECUTED"
    trade = Trade(
        event_id=event.id,
        side=side,
        grid_price=Decimal("10.00000000"),
        execution_price=Decimal("10.01000000") if executed else None,
        shares=100,
        notional=Decimal("1001.00000000") if executed else None,
        commission=Decimal("5.00000000") if executed else None,
        slippage_cost=Decimal("1.00000000") if executed else None,
        cash_after=Decimal("98994.00000000"),
        shares_after=100,
        equity_after=Decimal("99994.00000000"),
        status=status,
        skip_reason=skip_reason,
    )
    session.add(trade)
    session.flush()
    return trade


def parse(content: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(content, newline="")))


# A digit followed by an exponent marker -- i.e. actual scientific notation,
# not merely the letter E inside a word such as "EXECUTED".
SCIENTIFIC_NOTATION = re.compile(r"\d[eE][+-]?\d")


def assert_no_scientific_notation(content: str) -> None:
    for row in parse(content):
        for cell in row:
            assert not SCIENTIFIC_NOTATION.search(cell), cell


class TestTradesCsvHeader:
    def test_frozen_header_names_and_order(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            rows = parse(build_trades_csv(session, backtest_run_id=run_id))
        assert rows[0] == [
            "date",
            "event_sequence",
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
        ]
        assert rows[0] == list(TRADE_CSV_HEADER)

    def test_internal_identifiers_absent(self, session_factory: sessionmaker[Session]) -> None:
        assert "event_id" not in TRADE_CSV_HEADER
        assert "id" not in TRADE_CSV_HEADER
        assert "backtest_run_id" not in TRADE_CSV_HEADER

    def test_empty_trade_set_returns_header_only(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        rows = parse(content)
        assert len(rows) == 1
        assert content.endswith("\n")


class TestTradesCsvRows:
    def test_one_trade_produces_one_row_with_executed_values(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            add_trade(session, run_id=run_id, event_sequence=1, event_date=START)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        rows = list(csv.DictReader(io.StringIO(content, newline="")))
        assert len(rows) == 1
        assert rows[0] == {
            "date": "2026-03-02",
            "event_sequence": "1",
            "side": "BUY",
            "grid_price": "10.00000000",
            "execution_price": "10.01000000",
            "shares": "100",
            "notional": "1001.00000000",
            "commission": "5.00000000",
            "slippage_cost": "1.00000000",
            "cash_after": "98994.00000000",
            "shares_after": "100",
            "equity_after": "99994.00000000",
            "status": "EXECUTED",
            "skip_reason": "",
        }

    def test_skipped_trade_nulls_become_empty_cells(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            add_trade(
                session,
                run_id=run_id,
                event_sequence=1,
                event_date=START,
                status="SKIPPED",
                skip_reason="INSUFFICIENT_CASH",
            )
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        row = next(iter(csv.DictReader(io.StringIO(content, newline=""))))
        assert row["execution_price"] == ""
        assert row["notional"] == ""
        assert row["commission"] == ""
        assert row["slippage_cost"] == ""
        # Skip reason and the portfolio state remain populated.
        assert row["skip_reason"] == "INSUFFICIENT_CASH"
        assert row["cash_after"] == "98994.00000000"
        assert row["shares_after"] == "100"
        assert row["equity_after"] == "99994.00000000"

    def test_date_and_sequence_come_from_backtest_event(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            add_trade(
                session,
                run_id=run_id,
                event_sequence=7,
                event_date=START + timedelta(days=2),
            )
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        row = next(iter(csv.DictReader(io.StringIO(content, newline=""))))
        assert row["date"] == "2026-03-04"
        assert row["event_sequence"] == "7"

    def test_rows_ordered_by_event_sequence(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            # Inserted out of order on purpose.
            for sequence in (3, 1, 2):
                add_trade(
                    session,
                    run_id=run_id,
                    event_sequence=sequence,
                    event_date=START,
                    side="SELL" if sequence == 2 else "BUY",
                )
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        sequences = [
            row["event_sequence"] for row in csv.DictReader(io.StringIO(content, newline=""))
        ]
        assert sequences == ["1", "2", "3"]

    def test_only_the_requested_run_is_exported(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session, name="mine")
            other_run_id = seed_run(session, name="other")
            add_trade(session, run_id=run_id, event_sequence=1, event_date=START)
            add_trade(session, run_id=other_run_id, event_sequence=1, event_date=START)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        assert len(parse(content)) == 2  # header + exactly one row

    def test_repeated_generation_is_deterministic(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            for sequence in (1, 2):
                add_trade(session, run_id=run_id, event_sequence=sequence, event_date=START)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            first = build_trades_csv(session, backtest_run_id=run_id)
            second = build_trades_csv(session, backtest_run_id=run_id)
        assert first == second


class TestTradesCsvSerialization:
    def test_large_and_small_decimals_never_use_scientific_notation(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            trade = add_trade(session, run_id=run_id, event_sequence=1, event_date=START)
            trade.grid_price = Decimal("0.00000001")
            trade.equity_after = Decimal("123456789012.00000000")
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        row = next(iter(csv.DictReader(io.StringIO(content, newline=""))))
        assert row["grid_price"] == "0.00000001"
        assert row["equity_after"] == "123456789012.00000000"
        assert_no_scientific_notation(content)
        assert "," not in row["equity_after"]  # no thousands separators

    def test_adversarial_text_is_escaped_by_the_csv_writer(self) -> None:
        """Escaping is csv.writer's job, never manual concatenation.

        Exercised on the renderer directly because every text column in
        `trades` is CHECK-constrained (side/status/skip_reason are closed
        enumerations), so no such value can reach a persisted row.
        """
        content = _render_csv(
            ("a", "b", "c"),
            [['has "quotes"', "has,comma", "has\nnewline"], ["中文", "买入", "普通"]],
        )
        rows = list(csv.reader(io.StringIO(content, newline="")))
        assert rows[1] == ['has "quotes"', "has,comma", "has\nnewline"]
        assert rows[2] == ["中文", "买入", "普通"]
        assert content.encode("utf-8").decode("utf-8") == content

    def test_no_utf8_bom(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        assert not content.startswith("﻿")
        assert not content.encode("utf-8").startswith(b"\xef\xbb\xbf")

    def test_line_terminator_is_lf_only(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            add_trade(session, run_id=run_id, event_sequence=1, event_date=START)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_trades_csv(session, backtest_run_id=run_id)
        assert "\r\n" not in content


class TestDailyEquityCsv:
    def add_row(
        self,
        session: Session,
        *,
        run_id: int,
        day_offset: int,
        drawdown: str = "0.00000000",
    ) -> None:
        session.add(
            DailyEquity(
                backtest_run_id=run_id,
                date=START + timedelta(days=day_offset),
                close=Decimal("10.50000000"),
                cash=Decimal("50000.00000000"),
                shares=1000,
                equity=Decimal("60500.00000000"),
                drawdown=Decimal(drawdown),
                zone_at_close="IN_A",
            )
        )
        session.flush()

    def test_frozen_header_names_and_order(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            rows = parse(build_daily_equity_csv(session, backtest_run_id=run_id))
        # SPEC 25.4: table columns minus `id` only -- backtest_run_id stays.
        assert rows[0] == [
            "backtest_run_id",
            "date",
            "close",
            "cash",
            "shares",
            "equity",
            "drawdown",
            "zone_at_close",
        ]
        assert rows[0] == list(DAILY_EQUITY_CSV_HEADER)
        assert "id" not in DAILY_EQUITY_CSV_HEADER

    def test_one_row_per_daily_equity_row_in_date_order(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            for offset in (2, 0, 1):  # inserted out of order
                self.add_row(session, run_id=run_id, day_offset=offset)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_daily_equity_csv(session, backtest_run_id=run_id)
        rows = list(csv.DictReader(io.StringIO(content, newline="")))
        assert [row["date"] for row in rows] == ["2026-03-02", "2026-03-03", "2026-03-04"]
        assert all(row["backtest_run_id"] == str(run_id) for row in rows)

    def test_decimal_and_negative_drawdown_preserved(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            self.add_row(session, run_id=run_id, day_offset=0, drawdown="-0.12345678")
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_daily_equity_csv(session, backtest_run_id=run_id)
        row = next(iter(csv.DictReader(io.StringIO(content, newline=""))))
        assert row["drawdown"] == "-0.12345678"
        assert row["equity"] == "60500.00000000"
        assert row["shares"] == "1000"
        assert row["zone_at_close"] == "IN_A"
        assert_no_scientific_notation(content)

    def test_empty_series_returns_header_only(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_daily_equity_csv(session, backtest_run_id=run_id)
        assert len(parse(content)) == 1

    def test_only_the_requested_run_is_exported(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session, name="mine")
            other_run_id = seed_run(session, name="other")
            self.add_row(session, run_id=run_id, day_offset=0)
            self.add_row(session, run_id=other_run_id, day_offset=0)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            content = build_daily_equity_csv(session, backtest_run_id=run_id)
        assert len(parse(content)) == 2

    def test_repeated_generation_is_deterministic(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            for offset in (0, 1):
                self.add_row(session, run_id=run_id, day_offset=offset)
            session.commit()
        with commit_forbidding_session(session_factory) as session:
            assert build_daily_equity_csv(
                session, backtest_run_id=run_id
            ) == build_daily_equity_csv(session, backtest_run_id=run_id)


class TestQueryEfficiency:
    def test_trades_csv_uses_one_query(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            for sequence in range(1, 6):
                add_trade(session, run_id=run_id, event_sequence=sequence, event_date=START)
            session.commit()
        statements: list[str] = []
        with commit_forbidding_session(session_factory) as session:
            event = sa.event

            def record(
                conn: Any, cursor: Any, statement: str, *_rest: Any
            ) -> None:  # pragma: no cover - trivial
                statements.append(statement)

            event.listen(session.get_bind(), "before_cursor_execute", record)
            try:
                build_trades_csv(session, backtest_run_id=run_id)
            finally:
                event.remove(session.get_bind(), "before_cursor_execute", record)
        selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
        assert len(selects) == 1  # no N+1 per-trade lookups

    def test_equity_csv_uses_one_query(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run_id = seed_run(session)
            for offset in range(5):
                session.add(
                    DailyEquity(
                        backtest_run_id=run_id,
                        date=START + timedelta(days=offset),
                        close=Decimal("1"),
                        cash=Decimal("1"),
                        shares=1,
                        equity=Decimal("1"),
                        drawdown=Decimal("0"),
                        zone_at_close="IN_A",
                    )
                )
            session.commit()
        statements: list[str] = []
        with commit_forbidding_session(session_factory) as session:

            def record(
                conn: Any, cursor: Any, statement: str, *_rest: Any
            ) -> None:  # pragma: no cover - trivial
                statements.append(statement)

            sa.event.listen(session.get_bind(), "before_cursor_execute", record)
            try:
                build_daily_equity_csv(session, backtest_run_id=run_id)
            finally:
                sa.event.remove(session.get_bind(), "before_cursor_execute", record)
        selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
        assert len(selects) == 1
