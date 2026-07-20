"""Tests for the complete result.json export document builder."""

import copy
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from app.backtests.exports import build_complete_result_document
from app.backtests.persistence import ResultIntegrityError
from app.db import Base
from app.db.models import BacktestRun, Dataset, PriceBar, User
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

START = date(2026, 3, 2)

CONFIGURATION: dict[str, Any] = {
    "initial_cash": "100000.00",
    "initial_shares": 0,
    "lot_size": 100,
    "trade_lots": 1,
    "baseline": None,
    "a_distance": {"mode": "PERCENT", "value": "0.05"},
    "tick_size": {"enabled": False, "value": None},
    "ohlc_path_mode": "AUTO",
    "risk_free_rate_annual": "0.0",
}

BENCHMARK_1: dict[str, Any] = {
    "final_equity": "108000.00000000",
    "total_return": "0.08000000",
    "shares_purchased": 0,
}

BENCHMARK_2: dict[str, Any] = {
    "final_equity": "112500.00000000",
    "total_return": "0.12500000",
    # Day-one purchase information must survive the export untouched.
    "day_one_purchase": {
        "date": "2026-03-02",
        "price": "10.00000000",
        "shares": 9900,
        "commission": "5.00000000",
        "residual_cash": "1015.00000000",
    },
}

RESULT_METRICS: dict[str, Any] = {
    "initial_equity": "100000.00000000",
    "baseline": "10.00000000",
    "grid_levels": ["9.50000000", "10.00000000", "10.50000000"],
    "metrics": {"sharpe_ratio": "1.25000000", "max_drawdown": "-0.08000000"},
    "benchmark1": BENCHMARK_1,
    "benchmark2": BENCHMARK_2,
    "final_state": {"cash": "1000.00000000", "shares": 9900},
}


@pytest.fixture()
def engine(tmp_path: Any) -> Engine:
    created = sa.create_engine(f"sqlite:///{tmp_path / 'json_export.db'}")
    Base.metadata.create_all(created)
    return created


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_run(
    session: Session,
    *,
    result_metrics: dict[str, Any] | None,
    security_name: str | None = "中概互联ETF",
    security_code: str | None = "159825",
) -> BacktestRun:
    user = User(email="json@example.com", password_hash="x")
    session.add(user)
    session.flush()
    dataset = Dataset(
        user_id=user.id,
        name="沪深数据集",
        source_type="TDX_XLS",
        original_filename="159825.xls",
        security_name=security_name,
        security_code=security_code,
        data_mode="CLOSE_ONLY",
        start_date=START,
        end_date=START + timedelta(days=2),
        row_count=3,
        column_mapping={"date": "日期", "close": "收盘"},
        cleaning_summary={"removed_rows": 2, "duplicates": {"kept": "LAST", "count": 1}},
    )
    session.add(dataset)
    session.flush()
    for offset in range(3):
        session.add(
            PriceBar(
                dataset_id=dataset.id,
                date=START + timedelta(days=offset),
                close=Decimal("10.00000000"),
            )
        )
    run = BacktestRun(
        user_id=user.id,
        dataset_id=dataset.id,
        name="导出测试",
        status="COMPLETED" if result_metrics is not None else "FAILED",
        configuration=copy.deepcopy(CONFIGURATION),
        ohlc_path_mode="AUTO",
        start_date=START,
        end_date=START + timedelta(days=2),
        result_metrics=copy.deepcopy(result_metrics) if result_metrics is not None else None,
    )
    session.add(run)
    session.flush()
    return run


class TestTopLevelShape:
    def test_exact_top_level_key_set_and_order(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        assert list(document) == [
            "configuration",
            "result_metrics",
            "benchmark_1",
            "benchmark_2",
            "dataset_summary",
        ]

    def test_document_is_json_serializable_and_parses_back(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        parsed = json.loads(json.dumps(document, ensure_ascii=False))
        assert parsed == document


class TestStoredValuePreservation:
    def test_configuration_preserved_exactly(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        assert document["configuration"] == CONFIGURATION
        # Nulls and nested structure survive; nothing is rebuilt via Pydantic.
        configuration = document["configuration"]
        assert isinstance(configuration, dict)
        assert configuration["baseline"] is None
        assert configuration["a_distance"] == {"mode": "PERCENT", "value": "0.05"}

    def test_result_metrics_preserved_exactly(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        assert document["result_metrics"] == RESULT_METRICS

    def test_decimal_strings_stay_strings_and_no_floats_appear(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)

        def assert_no_float(value: object) -> None:
            assert not isinstance(value, float), value
            if isinstance(value, dict):
                for item in value.values():
                    assert_no_float(item)
            elif isinstance(value, list):
                for item in value:
                    assert_no_float(item)

        assert_no_float(document)
        metrics = document["result_metrics"]
        assert isinstance(metrics, dict)
        assert metrics["initial_equity"] == "100000.00000000"

    def test_source_stored_json_is_not_mutated(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
            benchmark = document["benchmark_1"]
            assert isinstance(benchmark, dict)
            benchmark["final_equity"] = "MUTATED"
            summary = document["dataset_summary"]
            assert isinstance(summary, dict)
            cleaning = summary["cleaning_summary"]
            assert isinstance(cleaning, dict)
            cleaning["removed_rows"] = 999
            # The ORM-held documents are untouched by edits to the export.
            assert run.result_metrics == RESULT_METRICS
            assert run.dataset.cleaning_summary == {
                "removed_rows": 2,
                "duplicates": {"kept": "LAST", "count": 1},
            }

    def test_repeated_generation_is_deterministic(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            first = json.dumps(build_complete_result_document(run), ensure_ascii=False)
            second = json.dumps(build_complete_result_document(run), ensure_ascii=False)
        assert first == second


class TestBenchmarkMapping:
    def test_benchmarks_map_from_stored_keys(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        assert document["benchmark_1"] == BENCHMARK_1
        assert document["benchmark_2"] == BENCHMARK_2

    def test_benchmark_2_day_one_purchase_preserved(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        benchmark = document["benchmark_2"]
        assert isinstance(benchmark, dict)
        assert benchmark["day_one_purchase"] == BENCHMARK_2["day_one_purchase"]

    def test_stored_metrics_keys_are_not_renamed(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        metrics = document["result_metrics"]
        assert isinstance(metrics, dict)
        # Only the output field names differ; the stored document keeps its
        # canonical benchmark1/benchmark2 keys.
        assert "benchmark1" in metrics
        assert "benchmark2" in metrics
        assert "benchmark_1" not in metrics

    def test_null_result_metrics_produces_null_benchmarks(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=None)
            document = build_complete_result_document(run)
        assert document["result_metrics"] is None
        assert document["benchmark_1"] is None
        assert document["benchmark_2"] is None
        # A FAILED run still exports its configuration and dataset summary.
        assert document["configuration"] == CONFIGURATION
        assert isinstance(document["dataset_summary"], dict)

    @pytest.mark.parametrize("missing", ["benchmark1", "benchmark2"])
    def test_missing_benchmark_in_non_null_metrics_fails_loudly(
        self, session_factory: sessionmaker[Session], missing: str
    ) -> None:
        malformed = copy.deepcopy(RESULT_METRICS)
        del malformed[missing]
        with session_factory() as session:
            run = seed_run(session, result_metrics=malformed)
            with pytest.raises(ResultIntegrityError) as excinfo:
                build_complete_result_document(run)
        # Loud server-side failure, never a silent recomputation.
        assert missing in str(excinfo.value)


class TestDatasetSummary:
    def test_exact_field_set(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
            dataset_id = run.dataset.id
        summary = document["dataset_summary"]
        assert isinstance(summary, dict)
        assert summary == {
            "id": dataset_id,
            "name": "沪深数据集",
            "source_type": "TDX_XLS",
            "original_filename": "159825.xls",
            "security_name": "中概互联ETF",
            "security_code": "159825",
            "data_mode": "CLOSE_ONLY",
            "start_date": "2026-03-02",
            "end_date": "2026-03-04",
            "row_count": 3,
            "column_mapping": {"date": "日期", "close": "收盘"},
            "cleaning_summary": {
                "removed_rows": 2,
                "duplicates": {"kept": "LAST", "count": 1},
            },
        }

    def test_dates_serialize_as_iso_strings(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        summary = document["dataset_summary"]
        assert isinstance(summary, dict)
        assert summary["start_date"] == "2026-03-02"
        assert summary["end_date"] == "2026-03-04"

    def test_structured_json_fields_stay_structured(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        summary = document["dataset_summary"]
        assert isinstance(summary, dict)
        # Not stringified JSON -- real nested objects.
        assert isinstance(summary["column_mapping"], dict)
        assert isinstance(summary["cleaning_summary"], dict)

    def test_nullable_security_fields_remain_null(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(
                session,
                result_metrics=RESULT_METRICS,
                security_name=None,
                security_code=None,
            )
            document = build_complete_result_document(run)
        summary = document["dataset_summary"]
        assert isinstance(summary, dict)
        assert summary["security_name"] is None
        assert summary["security_code"] is None

    def test_chinese_metadata_survives_json_round_trip(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        encoded = json.dumps(document, ensure_ascii=False).encode("utf-8")
        summary = json.loads(encoded.decode("utf-8"))["dataset_summary"]
        assert summary["security_name"] == "中概互联ETF"
        assert summary["name"] == "沪深数据集"
        assert summary["column_mapping"]["date"] == "日期"

    def test_no_user_id_and_no_price_bars(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        summary = document["dataset_summary"]
        assert isinstance(summary, dict)
        assert "user_id" not in summary
        assert "price_bars" not in summary
        assert "user_id" not in document
        serialized = json.dumps(document, ensure_ascii=False)
        assert "price_bars" not in serialized
        assert "password" not in serialized
        assert "_sa_instance_state" not in serialized


class TestReadOnly:
    def test_builder_never_commits_or_flushes(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            session.commit()

        def forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("the result document builder must never write")

        with session_factory(autoflush=False) as session:
            stored = session.get(BacktestRun, run.id)
            assert stored is not None
            monkeypatch.setattr(type(session), "commit", forbidden)
            monkeypatch.setattr(type(session), "flush", forbidden)
            document = build_complete_result_document(stored)
        assert document["result_metrics"] == RESULT_METRICS

    def test_builder_does_not_run_the_engine(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.engine as engine_module

        def forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("exports must never invoke the engine")

        monkeypatch.setattr(engine_module, "run_backtest", forbidden)
        with session_factory() as session:
            run = seed_run(session, result_metrics=RESULT_METRICS)
            document = build_complete_result_document(run)
        # Benchmarks came from storage, not from a fresh engine run.
        assert document["benchmark_1"] == BENCHMARK_1
