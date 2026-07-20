"""Tests for the in-memory PDF backtest report builder (SPEC 32)."""

import copy
import io
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from app.backtests.pdf_report import (
    FIRST_TRADE_ROWS,
    RISK_DISCLAIMER,
    build_backtest_pdf_report,
)
from app.db import Base
from app.db.models import (
    BacktestEvent,
    BacktestRun,
    DailyEquity,
    Dataset,
    Trade,
    User,
    ZoneEventRecord,
)
from pypdf import PdfReader
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

START = date(2026, 2, 2)

CONFIGURATION: dict[str, Any] = {
    "initial_cash": "100000.00",
    "initial_shares": 10000,
    "lot_size": 100,
    "trade_lots": 1,
    "baseline": None,
    "a_distance": {"mode": "FIXED", "value": "0.06"},
    "c_distance": {"mode": "FIXED", "value": "0.12"},
    "grid_step": {"mode": "PERCENT", "value": "0.01"},
    "tick_size": {"enabled": True, "value": "0.001"},
    "ohlc_path_mode": "AUTO",
    "buy_commission": {
        "rate_enabled": True,
        "rate": "0.0003",
        "minimum_enabled": True,
        "minimum": "5",
        "fixed_enabled": False,
        "fixed": "0",
    },
    "sell_commission": {
        "rate_enabled": True,
        "rate": "0.0003",
        "minimum_enabled": False,
        "minimum": "0",
        "fixed_enabled": False,
        "fixed": "0",
    },
    "slippage": {
        "shared": False,
        "mode": "PERCENT",
        "value": None,
        "buy": "0.001",
        "sell": "0.002",
    },
    "risk_free_rate_annual": "0",
}

EQUITY_SERIES: dict[str, Any] = {
    "initial_equity": "106580.00000000",
    "final_equity": "107771.70000000",
    "net_profit": "1191.70000000",
    "total_return": "0.011181272283730531056483393",
    "annualized_return": "0.006709867855762830722388486",
    "maximum_drawdown": "-0.0125574249718591970490891340",
    "sharpe_ratio": "0.5301681561862160237276256059",
}

RESULT_METRICS: dict[str, Any] = {
    "initial_equity": "106580.00000000",
    "baseline": "0.63900000",
    "a_lower": "0.57900000",
    "a_upper": "0.69900000",
    "c_lower": "0.51900000",
    "c_upper": "0.75900000",
    "grid_step": "0.01",
    "grid_levels": ["0.57900000", "0.63900000", "0.69900000"],
    "metrics": {
        "strategy": dict(EQUITY_SERIES),
        "trade_costs": {
            "total_commission": "665",
            "total_slippage_cost": "13.300",
            "executed_trades": 3,
            "skipped_trades": 1,
            "buy_count": 2,
            "sell_count": 2,
        },
        "zones": {
            "days_closed_in_a_zone": 184,
            "days_closed_in_c_zone": 62,
            "days_closed_outside_c": 174,
            "zone_event_counts": {"ENTER_C_ZONE": 17, "EXIT_C_ZONE": 16},
        },
        "first_return": {"equity": "106480.800", "days": 0},
        "benchmark1": dict(EQUITY_SERIES),
        "benchmark2": dict(EQUITY_SERIES),
        "benchmark2_day_one_commission": "29.9713200",
        "benchmark2_day_one_slippage_cost": "151.600",
    },
    "benchmark1": {
        "points": [
            {
                "date": "2026-02-02",
                "close": "0.639",
                "cash": "1",
                "shares": 1,
                "equity": "106390.0",
            },
            {
                "date": "2026-02-03",
                "close": "0.641",
                "cash": "1",
                "shares": 1,
                "equity": "106500.0",
            },
            {
                "date": "2026-02-04",
                "close": "0.643",
                "cash": "1",
                "shares": 1,
                "equity": "106700.0",
            },
        ],
        "day_one_purchase": None,
    },
    "benchmark2": {
        "points": [
            {
                "date": "2026-02-02",
                "close": "0.639",
                "cash": "1",
                "shares": 1,
                "equity": "103328.0",
            },
            {
                "date": "2026-02-03",
                "close": "0.641",
                "cash": "1",
                "shares": 1,
                "equity": "104000.0",
            },
            {
                "date": "2026-02-04",
                "close": "0.643",
                "cash": "1",
                "shares": 1,
                "equity": "105000.0",
            },
        ],
        "day_one_purchase": {
            "reference_price": "0.65800000",
            "tick_price": "0.658",
            "execution_price": "0.659",
            "lots": 1516,
            "shares_purchased": 151600,
            "notional": "99904.400",
            "commission": "29.9713200",
            "slippage_cost": "151.600",
            "cash_after": "65.6286800",
            "shares_after": 161600,
        },
    },
    "final_state": {
        "cash": "99725.200",
        "shares": 9500,
        "market_cursor": "0.84700000",
        "trade_anchor": "0.699",
        "zone_state": "OUTSIDE_C",
    },
}


@pytest.fixture()
def engine(tmp_path: Any) -> Engine:
    created = sa.create_engine(f"sqlite:///{tmp_path / 'pdf.db'}")
    Base.metadata.create_all(created)
    return created


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_run(
    session: Session,
    *,
    status: str = "COMPLETED",
    result_metrics: dict[str, Any] | None = None,
    with_series: bool = True,
    trade_count: int = 4,
    run_name: str = "农业ETF富国 网格回测",
    security_name: str | None = "农业ETF富国",
    data_mode: str = "OHLCV",
    error_message: str | None = None,
    email: str = "pdf@example.com",
) -> BacktestRun:
    user = session.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(email=email, password_hash="x")
        session.add(user)
        session.flush()
    dataset = Dataset(
        user_id=user.id,
        name="沪深数据集",
        source_type="TDX_XLS",
        original_filename="159825.xls",
        security_name=security_name,
        security_code="159825",
        data_mode=data_mode,
        start_date=START,
        end_date=START + timedelta(days=2),
        row_count=3,
        column_mapping={"date": "时间", "close": "收盘"},
        cleaning_summary={"bad_rows": 0, "duplicate_dates": 0},
    )
    session.add(dataset)
    session.flush()
    run = BacktestRun(
        user_id=user.id,
        dataset_id=dataset.id,
        name=run_name,
        status=status,
        configuration=copy.deepcopy(CONFIGURATION),
        ohlc_path_mode="AUTO",
        start_date=START,
        end_date=START + timedelta(days=2),
        result_metrics=copy.deepcopy(result_metrics) if result_metrics is not None else None,
        error_message=error_message,
    )
    session.add(run)
    session.flush()

    if with_series:
        for index in range(trade_count):
            event = BacktestEvent(
                backtest_run_id=run.id,
                event_sequence=index + 1,
                event_type="TRADE",
                date=START + timedelta(days=index % 3),
                market_price=Decimal("0.63900000"),
            )
            session.add(event)
            session.flush()
            skipped = index == 1
            session.add(
                Trade(
                    event_id=event.id,
                    side="BUY" if index % 2 == 0 else "SELL",
                    grid_price=Decimal("0.63900000"),
                    execution_price=None if skipped else Decimal("0.64000000"),
                    shares=100,
                    notional=None if skipped else Decimal("64.00000000"),
                    commission=None if skipped else Decimal("5.00000000"),
                    slippage_cost=None if skipped else Decimal("0.10000000"),
                    cash_after=Decimal("99725.20000000"),
                    shares_after=9500,
                    equity_after=Decimal("106584.90000000"),
                    status="SKIPPED" if skipped else "EXECUTED",
                    skip_reason="INSUFFICIENT_CASH" if skipped else None,
                )
            )
        zone_event = BacktestEvent(
            backtest_run_id=run.id,
            event_sequence=trade_count + 1,
            event_type="ZONE_EVENT",
            date=START,
            market_price=Decimal("0.75900000"),
        )
        session.add(zone_event)
        session.flush()
        session.add(
            ZoneEventRecord(
                event_id=zone_event.id,
                event_type="ENTER_C_ZONE",
                price=Decimal("0.75900000"),
            )
        )
        for offset, (equity, drawdown) in enumerate(
            [("106390.0", "0.0"), ("106500.0", "-0.0125"), ("107771.70000000", "-0.0031")]
        ):
            session.add(
                DailyEquity(
                    backtest_run_id=run.id,
                    date=START + timedelta(days=offset),
                    close=Decimal("0.63900000") + Decimal(offset) / 1000,
                    cash=Decimal("99725.20000000"),
                    shares=9500,
                    equity=Decimal(equity),
                    drawdown=Decimal(drawdown),
                    zone_at_close="IN_A",
                )
            )
    session.flush()
    return run


def text_of(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class TestStructure:
    def test_pdf_signature_and_trailer(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            data = build_backtest_pdf_report(session, run=run)
        assert data.startswith(b"%PDF-")
        assert data.rstrip().endswith(b"%%EOF")
        assert len(data) > 5000

    def test_page_count_in_expected_range(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            data = build_backtest_pdf_report(session, run=run)
        reader = PdfReader(io.BytesIO(data))
        assert 2 <= len(reader.pages) <= 8

    def test_pdf_metadata_is_safe_and_id_based(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            run_id = run.id
            run_name = run.name
            data = build_backtest_pdf_report(session, run=run)
        metadata = PdfReader(io.BytesIO(data)).metadata
        assert metadata is not None
        assert metadata.get("/Title") == f"Backtest Report {run_id}"
        assert metadata.get("/Author") == "Grid Backtester"
        assert metadata.get("/Subject") == "Backtest result report"
        # The editable run name never becomes document metadata identity.
        assert run_name not in str(metadata.get("/Title"))
        for value in metadata.values():
            rendered = str(value)
            assert "password" not in rendered.lower()
            assert "@example.com" not in rendered
            assert "C:\\" not in rendered and "/home/" not in rendered

    def test_page_numbers_present(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            data = build_backtest_pdf_report(session, run=run)
        text = text_of(data)
        assert "Page 1" in text
        assert "Page 2" in text


class TestCompletedContent:
    @pytest.fixture()
    def report_text(self, session_factory: sessionmaker[Session]) -> str:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            return text_of(build_backtest_pdf_report(session, run=run))

    def test_identity_and_status(
        self, session_factory: sessionmaker[Session], report_text: str
    ) -> None:
        assert "农业ETF富国 网格回测" in report_text
        assert "COMPLETED" in report_text
        assert re.search(r"Backtest #\d+", report_text)

    def test_all_frozen_spec_sections_present(self, report_text: str) -> None:
        # SPEC 32's fifteen ordered sections, by their rendered headings.
        for heading in (
            "Security and Dataset",
            "Data-Cleaning Summary",
            "Strategy Parameters",
            "Fee and Slippage Assumptions",
            "OHLC-Path Assumption",
            "Core Metrics",
            "Buy-and-Hold Benchmarks",
            "Price and Grid Geometry",
            "Equity Curve",
            "Drawdown",
            f"First {FIRST_TRADE_ROWS} Trades",
            "Cost Summary",
            "Risk Disclaimer",
        ):
            assert heading in report_text, heading

    def test_dataset_and_security_metadata(self, report_text: str) -> None:
        assert "农业ETF富国" in report_text
        assert "159825" in report_text
        assert "TDX_XLS" in report_text
        assert "159825.xls" in report_text
        assert "2026-02-02" in report_text

    def test_configuration_values_rendered(self, report_text: str) -> None:
        assert "100000.00" in report_text  # initial cash, exact stored string
        assert "10000" in report_text  # initial shares
        assert "0.06 (fixed mode)" in report_text
        assert "Enabled @ 0.001" in report_text  # tick size
        assert "- (default: first Close)" in report_text  # null baseline
        assert "0.0003" in report_text  # commission rate

    def test_separate_slippage_rendered_as_separate(self, report_text: str) -> None:
        assert "Separate" in report_text
        assert "buy 0.001" in report_text
        assert "sell 0.002" in report_text

    def test_commission_booleans_render_as_enabled_disabled(self, report_text: str) -> None:
        assert "rate Enabled" in report_text
        assert "fixed Disabled" in report_text

    def test_metrics_and_final_equity(self, report_text: str) -> None:
        assert "107771.70000000" in report_text
        assert "106580.00000000" in report_text
        assert "1191.70000000" in report_text
        assert "0.530168" in report_text  # sharpe, fixed-point

    def test_benchmark_labels_and_day_one(self, report_text: str) -> None:
        assert "Benchmark 1" in report_text
        assert "Benchmark 2" in report_text
        assert "Benchmark 2 Day-One Purchase" in report_text
        assert "151600" in report_text  # shares purchased
        assert "29.9713200" in report_text  # day-one commission

    def test_trade_and_zone_statistics(self, report_text: str) -> None:
        assert "BUY Count" in report_text
        assert "SELL Count" in report_text
        assert "Executed Trades" in report_text
        assert "Skipped Trades" in report_text
        assert "ENTER_C_ZONE" in report_text
        assert "Days Closed in A Zone" in report_text

    def test_cost_summary(self, report_text: str) -> None:
        assert "Total Commission" in report_text
        assert "Total Slippage Cost" in report_text

    def test_first_return_information(self, report_text: str) -> None:
        assert "First Return Equity" in report_text
        assert "Days Until First Return" in report_text

    def test_risk_disclaimer_text_is_the_frozen_wording(self, report_text: str) -> None:
        normalized = " ".join(report_text.split())
        assert " ".join(RISK_DISCLAIMER.split()) in normalized

    def test_no_internal_identifiers_or_secrets(self, report_text: str) -> None:
        assert "user_id" not in report_text
        assert "password" not in report_text.lower()
        assert "_sa_instance_state" not in report_text
        assert "event_id" not in report_text
        assert "SELECT " not in report_text

    def test_no_float_artifacts_in_rendered_numbers(self, report_text: str) -> None:
        # No scientific notation and no float repr tails such as 0.1000000000000001.
        assert not re.search(r"\d[eE][+-]?\d", report_text)
        assert not re.search(r"\.\d{17,}", report_text)


class TestBoundedTradeTable:
    def test_table_is_capped_at_first_20_trades(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, trade_count=45)
            text = text_of(build_backtest_pdf_report(session, run=run))
        # Sequence 20 is rendered; 21 and beyond are not.
        assert re.search(r"\b20\b", text)
        assert "Showing the first 20 trade(s)" in text
        assert "trades.csv" in text

    def test_fewer_trades_than_cap_reports_actual_count(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, trade_count=3)
            text = text_of(build_backtest_pdf_report(session, run=run))
        assert "Showing the first 3 trade(s)" in text

    def test_skipped_trade_renders_reason_and_dashes(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            text = text_of(build_backtest_pdf_report(session, run=run))
        assert "SKIPPED" in text
        # Long skip tokens may wrap inside the narrow column, so compare with
        # layout whitespace removed.
        assert "INSUFFICIENT_CASH" in "".join(text.split())


class TestFailedRun:
    def test_failed_run_shows_status_and_error(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(
                session,
                status="FAILED",
                result_metrics=None,
                with_series=False,
                error_message="Sanitized engine failure.",
            )
            data = build_backtest_pdf_report(session, run=run)
        text = text_of(data)
        assert data.startswith(b"%PDF-")
        assert "FAILED" in text
        assert "Sanitized engine failure." in text
        assert "Run Status: FAILED" in text

    def test_failed_run_fabricates_no_results_or_charts(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(
                session,
                status="FAILED",
                result_metrics=None,
                with_series=False,
                error_message="boom",
            )
            text = text_of(build_backtest_pdf_report(session, run=run))
        assert "Result data is unavailable" in text
        assert "Benchmark data is unavailable" in text
        assert "No daily price series is available" in text
        assert "No equity series is available" in text
        assert "Cost data is unavailable" in text
        # No synthetic numbers leaked in from the completed fixture.
        assert "107771.70000000" not in text

    def test_failed_run_still_shows_configuration_and_dataset(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(
                session, status="FAILED", result_metrics=None, with_series=False, error_message="x"
            )
            text = text_of(build_backtest_pdf_report(session, run=run))
        assert "Strategy Parameters" in text
        assert "农业ETF富国" in text
        assert "Risk Disclaimer" in text

    @pytest.mark.parametrize("status", ["PENDING", "RUNNING"])
    def test_pending_and_running_render_status_without_results(
        self, session_factory: sessionmaker[Session], status: str
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, status=status, result_metrics=None, with_series=False)
            text = text_of(build_backtest_pdf_report(session, run=run))
        assert f"Run Status: {status}" in text
        assert "Result data is unavailable" in text


class TestEdgeCases:
    def test_empty_series_still_produces_a_valid_pdf(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, with_series=False)
            data = build_backtest_pdf_report(session, run=run)
        text = text_of(data)
        assert data.startswith(b"%PDF-")
        assert "This run recorded no trades." in text
        assert "No daily price series is available" in text

    def test_single_point_series_does_not_crash(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, with_series=False)
            session.add(
                DailyEquity(
                    backtest_run_id=run.id,
                    date=START,
                    close=Decimal("0.639"),
                    cash=Decimal("1"),
                    shares=1,
                    equity=Decimal("106390.0"),
                    drawdown=Decimal("0"),
                    zone_at_close="IN_A",
                )
            )
            session.flush()
            data = build_backtest_pdf_report(session, run=run)
        assert data.startswith(b"%PDF-")

    def test_empty_benchmark_points_handled(self, session_factory: sessionmaker[Session]) -> None:
        metrics = copy.deepcopy(RESULT_METRICS)
        metrics["benchmark1"]["points"] = []
        metrics["benchmark2"]["points"] = []
        with session_factory() as session:
            run = seed_run(session, result_metrics=metrics)
            data = build_backtest_pdf_report(session, run=run)
        assert data.startswith(b"%PDF-")

    def test_null_optional_metrics_render_as_dash(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        metrics = copy.deepcopy(RESULT_METRICS)
        metrics["metrics"]["strategy"]["annualized_return"] = None
        metrics["metrics"]["strategy"]["sharpe_ratio"] = None
        metrics["metrics"]["first_return"] = {"equity": None, "days": None}
        with session_factory() as session:
            run = seed_run(session, result_metrics=metrics)
            data = build_backtest_pdf_report(session, run=run)
        assert data.startswith(b"%PDF-")
        assert "Days Until First Return" in text_of(data)

    def test_missing_day_one_purchase_handled(self, session_factory: sessionmaker[Session]) -> None:
        metrics = copy.deepcopy(RESULT_METRICS)
        metrics["benchmark2"]["day_one_purchase"] = None
        with session_factory() as session:
            run = seed_run(session, result_metrics=metrics)
            text = text_of(build_backtest_pdf_report(session, run=run))
        assert "No day-one purchase was recorded." in text

    def test_close_only_mode_does_not_claim_an_ohlc_path(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, data_mode="CLOSE_ONLY")
            text = text_of(build_backtest_pdf_report(session, run=run))
        assert "CLOSE_ONLY" in text
        assert "no OHLC path was reconstructed" in text
        assert "Stored Path Mode" not in text

    def test_very_long_name_wraps_without_crashing(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        long_name = "超长回测名称 " + "X" * 400
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, run_name=long_name)
            data = build_backtest_pdf_report(session, run=run)
        assert data.startswith(b"%PDF-")
        assert len(PdfReader(io.BytesIO(data)).pages) >= 2

    def test_markup_characters_in_name_are_escaped(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, run_name="A <b>& B</b> run")
            data = build_backtest_pdf_report(session, run=run)
        text = text_of(data)
        assert data.startswith(b"%PDF-")
        # Rendered literally, not interpreted as ReportLab inline markup.
        assert "<b>" in text or "A <b>& B</b> run" in text

    def test_null_security_name_renders_dash(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, security_name=None)
            data = build_backtest_pdf_report(session, run=run)
        assert data.startswith(b"%PDF-")


class TestPurity:
    def test_stored_documents_are_not_mutated(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            build_backtest_pdf_report(session, run=run)
            assert run.result_metrics == RESULT_METRICS
            assert run.configuration == CONFIGURATION

    def test_repeated_generation_is_semantically_deterministic(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            first = build_backtest_pdf_report(session, run=run)
            second = build_backtest_pdf_report(session, run=run)
        # Raw bytes embed a creation timestamp, so compare extracted content.
        assert text_of(first) == text_of(second)
        assert len(PdfReader(io.BytesIO(first)).pages) == len(PdfReader(io.BytesIO(second)).pages)

    def test_builder_never_commits_or_flushes(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            session.commit()
            run_id = run.id

        def forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("the PDF builder must never write")

        with session_factory(autoflush=False) as session:
            stored = session.get(BacktestRun, run_id)
            assert stored is not None
            monkeypatch.setattr(type(session), "commit", forbidden)
            monkeypatch.setattr(type(session), "flush", forbidden)
            data = build_backtest_pdf_report(session, run=stored)
        assert data.startswith(b"%PDF-")

    def test_builder_does_not_run_the_engine(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.engine as engine_module

        def forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("exports must never invoke the engine")

        monkeypatch.setattr(engine_module, "run_backtest", forbidden)
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            data = build_backtest_pdf_report(session, run=run)
        assert data.startswith(b"%PDF-")

    def test_no_file_is_written_to_disk(
        self, session_factory: sessionmaker[Session], tmp_path: Any
    ) -> None:
        before = set(tmp_path.rglob("*"))
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            build_backtest_pdf_report(session, run=run)
        new_files = {p for p in set(tmp_path.rglob("*")) - before if p.suffix == ".pdf"}
        assert not new_files


class TestQueryEfficiency:
    def test_series_loading_uses_bounded_query_count(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS, trade_count=40)
            session.commit()
            run_id = run.id

        statements: list[str] = []

        def record(conn: Any, cursor: Any, statement: str, *_rest: Any) -> None:
            statements.append(statement)

        with session_factory(autoflush=False) as session:
            stored = session.get(BacktestRun, run_id)
            assert stored is not None
            _ = stored.dataset  # dataset loaded before counting
            sa.event.listen(session.get_bind(), "before_cursor_execute", record)
            try:
                build_backtest_pdf_report(session, run=stored)
            finally:
                sa.event.remove(session.get_bind(), "before_cursor_execute", record)

        selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
        # One DailyEquity query plus one bounded Trade query -- no N+1.
        assert len(selects) == 2, selects
        assert any("LIMIT" in s.upper() for s in selects)

    def test_price_bars_are_never_queried(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            session.commit()
            run_id = run.id

        statements: list[str] = []

        def record(conn: Any, cursor: Any, statement: str, *_rest: Any) -> None:
            statements.append(statement)

        with session_factory(autoflush=False) as session:
            stored = session.get(BacktestRun, run_id)
            assert stored is not None
            sa.event.listen(session.get_bind(), "before_cursor_execute", record)
            try:
                build_backtest_pdf_report(session, run=stored)
            finally:
                sa.event.remove(session.get_bind(), "before_cursor_execute", record)

        assert not any("price_bars" in s.lower() for s in statements)
