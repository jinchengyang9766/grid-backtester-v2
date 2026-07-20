"""Tests for the three authenticated backtest export endpoints (SPEC 25.4)."""

import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from app.db.models import BacktestRun, Dataset, PriceBar, User
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

APP_DIR = Path(__file__).resolve().parents[2] / "app"

START = date(2026, 1, 5)

OWNER = "exporter@example.com"
STRANGER = "stranger@example.com"


def configuration(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "initial_cash": "9.00",
        "initial_shares": 0,
        "lot_size": 1,
        "trade_lots": 1,
        "baseline": None,
        "a_distance": {"mode": "FIXED", "value": "2"},
        "c_distance": {"mode": "FIXED", "value": "4"},
        "grid_step": {"mode": "FIXED", "value": "1"},
        "tick_size": {"enabled": False, "value": None},
        "ohlc_path_mode": None,
        "buy_commission": {
            "rate_enabled": False,
            "rate": "0",
            "minimum_enabled": False,
            "minimum": "0",
            "fixed_enabled": False,
            "fixed": "0",
        },
        "sell_commission": {
            "rate_enabled": False,
            "rate": "0",
            "minimum_enabled": False,
            "minimum": "0",
            "fixed_enabled": False,
            "fixed": "0",
        },
        "slippage": {"shared": True, "mode": "FIXED", "value": "0", "buy": None, "sell": None},
        "risk_free_rate_annual": "0.0",
    }
    config.update(overrides)
    return config


def signup(client: TestClient, email: str = OWNER) -> None:
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    login(client, email)


def login(client: TestClient, email: str = OWNER) -> None:
    client.post("/api/auth/login", json={"email": email, "password": "password123"})


def seed_dataset(
    session_factory: sessionmaker[Session],
    email: str,
    *,
    security_name: str | None = "中概互联ETF",
) -> int:
    with session_factory() as session:
        user_id = session.execute(sa.select(User.id).where(User.email == email)).scalar_one()
        dataset = Dataset(
            user_id=user_id,
            name="导出数据集",
            source_type="CSV",
            original_filename="export.csv",
            security_name=security_name,
            security_code="159999",
            data_mode="CLOSE_ONLY",
            start_date=START,
            end_date=START + timedelta(days=2),
            row_count=3,
            column_mapping={"date": "日期", "close": "收盘"},
            cleaning_summary={"removed_rows": 0},
        )
        session.add(dataset)
        session.flush()
        for offset, close in enumerate(["10", "7", "10"]):
            session.add(
                PriceBar(
                    dataset_id=dataset.id,
                    date=START + timedelta(days=offset),
                    close=Decimal(close),
                )
            )
        session.commit()
        return int(dataset.id)


def create_run(client: TestClient, dataset_id: int, name: str = "Export Run") -> dict[str, Any]:
    response = client.post(
        "/api/backtests",
        json={"dataset_id": dataset_id, "name": name, "configuration": configuration()},
    )
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture()
def owned_run(client: TestClient, session_factory: sessionmaker[Session]) -> dict[str, Any]:
    signup(client)
    dataset_id = seed_dataset(session_factory, OWNER)
    return create_run(client, dataset_id)


def export_paths(backtest_id: int) -> tuple[str, str, str]:
    base = f"/api/backtests/{backtest_id}/exports"
    return (f"{base}/trades.csv", f"{base}/equity.csv", f"{base}/result.json")


def read_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text, newline="")))


class TestAuthentication:
    def test_unauthenticated_requests_are_rejected(self, client: TestClient) -> None:
        for path in export_paths(1):
            response = client.get(path)
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_invalid_cookie_is_rejected(self, client: TestClient) -> None:
        client.cookies.set("access_token", "garbage")
        for path in export_paths(1):
            assert client.get(path).status_code == 401


class TestOwnership:
    def test_missing_run_returns_backtest_not_found(self, client: TestClient) -> None:
        signup(client)
        for path in export_paths(9999):
            response = client.get(path)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "BACKTEST_NOT_FOUND"
            assert response.json()["error"]["message"] == "Backtest not found."

    def test_other_users_run_returns_byte_identical_404(
        self,
        client: TestClient,
        api_app: FastAPI,
        session_factory: sessionmaker[Session],
        owned_run: dict[str, Any],
    ) -> None:
        run_id = owned_run["id"]
        with TestClient(api_app) as other:
            signup(other, STRANGER)
            for owned_path, missing_path in zip(
                export_paths(run_id), export_paths(9999), strict=True
            ):
                wrong_owner = other.get(owned_path)
                missing = other.get(missing_path)
                assert wrong_owner.status_code == 404
                # Existence and ownership are indistinguishable to a non-owner.
                assert wrong_owner.content == missing.content

    def test_export_404_matches_the_detail_endpoint_404(self, client: TestClient) -> None:
        signup(client)
        detail = client.get("/api/backtests/9999")
        for path in export_paths(9999):
            assert client.get(path).content == detail.content

    def test_deleted_run_returns_404(self, client: TestClient, owned_run: dict[str, Any]) -> None:
        run_id = owned_run["id"]
        assert client.delete(f"/api/backtests/{run_id}").status_code == 204
        for path in export_paths(run_id):
            response = client.get(path)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "BACKTEST_NOT_FOUND"

    def test_no_response_reveals_ownership_details(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        signup(client)
        for path in export_paths(9999):
            body = client.get(path).text
            assert "user_id" not in body
            assert "403" not in body
            assert OWNER not in body


class TestTradesCsvEndpoint:
    def test_successful_download_headers(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(export_paths(owned_run["id"])[0])
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        disposition = response.headers["content-disposition"]
        assert disposition == f'attachment; filename="backtest-{owned_run["id"]}-trades.csv"'
        assert "inline" not in disposition

    def test_content_parses_with_exact_headers(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(export_paths(owned_run["id"])[0])
        rows = list(csv.reader(io.StringIO(response.text, newline="")))
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

    def test_row_count_matches_persisted_trades(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        owned_run: dict[str, Any],
    ) -> None:
        run_id = owned_run["id"]
        response = client.get(export_paths(run_id)[0])
        rows = read_rows(response.text)
        detail = client.get(f"/api/backtests/{run_id}?include=trades").json()
        assert len(rows) == len(detail["trades"])
        assert rows  # the deterministic fixture actually trades
        # Joined event ordering matches the detail projection exactly.
        assert [row["event_sequence"] for row in rows] == [
            str(trade["event_sequence"]) for trade in detail["trades"]
        ]
        assert [row["date"] for row in rows] == [trade["date"] for trade in detail["trades"]]

    def test_internal_identifiers_are_not_exported(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(export_paths(owned_run["id"])[0])
        header = response.text.splitlines()[0]
        assert "event_id" not in header
        assert "backtest_run_id" not in header

    def test_empty_run_returns_header_only(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, OWNER)
        run_id = create_run(client, dataset_id)["id"]
        with session_factory() as session:
            run = session.get(BacktestRun, run_id)
            assert run is not None
            run.events.clear()
            session.commit()
        response = client.get(export_paths(run_id)[0])
        assert response.status_code == 200
        assert len(list(csv.reader(io.StringIO(response.text, newline="")))) == 1


class TestEquityCsvEndpoint:
    def test_successful_download_headers(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(export_paths(owned_run["id"])[1])
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="backtest-{owned_run["id"]}-equity.csv"'
        )

    def test_content_parses_with_exact_headers(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(export_paths(owned_run["id"])[1])
        rows = list(csv.reader(io.StringIO(response.text, newline="")))
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

    def test_rows_match_persisted_daily_equity(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        run_id = owned_run["id"]
        rows = read_rows(client.get(export_paths(run_id)[1]).text)
        detail = client.get(f"/api/backtests/{run_id}?include=daily_equity").json()
        persisted = detail["daily_equity"]
        assert len(rows) == len(persisted)
        assert [row["date"] for row in rows] == [item["date"] for item in persisted]
        assert [row["equity"] for row in rows] == [item["equity"] for item in persisted]
        assert all(row["backtest_run_id"] == str(run_id) for row in rows)
        # Ascending dates.
        dates = [row["date"] for row in rows]
        assert dates == sorted(dates)

    def test_empty_series_returns_header_only(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, OWNER)
        run_id = create_run(client, dataset_id)["id"]
        with session_factory() as session:
            run = session.get(BacktestRun, run_id)
            assert run is not None
            run.daily_equity_rows.clear()
            session.commit()
        response = client.get(export_paths(run_id)[1])
        assert response.status_code == 200
        assert len(list(csv.reader(io.StringIO(response.text, newline="")))) == 1


class TestResultJsonEndpoint:
    def test_successful_download_headers(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(export_paths(owned_run["id"])[2])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="backtest-{owned_run["id"]}-result.json"'
        )

    def test_parses_with_standard_json_and_has_exact_top_level_keys(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(export_paths(owned_run["id"])[2])
        document = json.loads(response.content.decode("utf-8"))
        assert list(document) == [
            "configuration",
            "result_metrics",
            "benchmark_1",
            "benchmark_2",
            "dataset_summary",
        ]

    def test_stored_values_are_preserved(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        run_id = owned_run["id"]
        document = json.loads(client.get(export_paths(run_id)[2]).content)
        detail = client.get(f"/api/backtests/{run_id}").json()
        assert document["configuration"] == detail["configuration"]
        assert document["result_metrics"] == detail["result_metrics"]
        assert document["benchmark_1"] == detail["result_metrics"]["benchmark1"]
        assert document["benchmark_2"] == detail["result_metrics"]["benchmark2"]

    def test_utf8_chinese_metadata_preserved(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(export_paths(owned_run["id"])[2])
        document = json.loads(response.content.decode("utf-8"))
        summary = document["dataset_summary"]
        assert summary["security_name"] == "中概互联ETF"
        assert summary["name"] == "导出数据集"
        assert summary["column_mapping"]["date"] == "日期"

    def test_no_price_bars_or_user_ids(self, client: TestClient, owned_run: dict[str, Any]) -> None:
        body = client.get(export_paths(owned_run["id"])[2]).text
        assert "price_bars" not in body
        assert "user_id" not in body
        assert "password" not in body

    def test_repeated_requests_are_byte_identical(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        path = export_paths(owned_run["id"])[2]
        assert client.get(path).content == client.get(path).content


class TestStatusBehavior:
    def test_completed_run_exports_all_available_data(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        assert owned_run["status"] == "COMPLETED"
        trades, equity, result = export_paths(owned_run["id"])
        assert len(read_rows(client.get(trades).text)) > 0
        assert len(read_rows(client.get(equity).text)) > 0
        assert json.loads(client.get(result).content)["result_metrics"] is not None

    def test_failed_run_exports_headers_and_null_metrics(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, OWNER)
        run_id = create_run(client, dataset_id)["id"]
        # Ownership is the only access gate (SPEC 24.4): a FAILED run still
        # exports, it simply has no result data to show.
        with session_factory() as session:
            run = session.get(BacktestRun, run_id)
            assert run is not None
            run.status = "FAILED"
            run.result_metrics = None
            run.error_message = "engine failure"
            run.events.clear()
            run.daily_equity_rows.clear()
            session.commit()
        trades, equity, result = export_paths(run_id)
        trades_response = client.get(trades)
        equity_response = client.get(equity)
        result_response = client.get(result)
        assert trades_response.status_code == 200
        assert equity_response.status_code == 200
        assert result_response.status_code == 200
        # Header-only: no synthetic rows are invented for a failed run.
        assert len(list(csv.reader(io.StringIO(trades_response.text, newline="")))) == 1
        assert len(list(csv.reader(io.StringIO(equity_response.text, newline="")))) == 1
        document = json.loads(result_response.content)
        assert document["result_metrics"] is None
        assert document["benchmark_1"] is None
        assert document["benchmark_2"] is None
        assert document["configuration"] is not None


class TestNoDatabaseWrites:
    def test_exports_do_not_change_any_row(
        self, client: TestClient, session_factory: sessionmaker[Session], owned_run: dict[str, Any]
    ) -> None:
        def snapshot() -> dict[str, Any]:
            with session_factory() as session:
                run = session.get(BacktestRun, owned_run["id"])
                assert run is not None
                return {
                    "status": run.status,
                    "result_metrics": run.result_metrics,
                    "configuration": run.configuration,
                    "completed_at": run.completed_at,
                    "events": session.execute(
                        sa.select(sa.func.count()).select_from(sa.table("backtest_events"))
                    ).scalar_one(),
                    "daily": session.execute(
                        sa.select(sa.func.count()).select_from(sa.table("daily_equity"))
                    ).scalar_one(),
                }

        before = snapshot()
        for path in export_paths(owned_run["id"]):
            assert client.get(path).status_code == 200
        assert snapshot() == before


class TestOpenApi:
    def test_exactly_three_export_routes_with_correct_media_types(self, api_app: FastAPI) -> None:
        schema = api_app.openapi()
        export_routes = sorted(path for path in schema["paths"] if "/exports/" in path)
        assert export_routes == [
            "/api/backtests/{backtest_id}/exports/equity.csv",
            "/api/backtests/{backtest_id}/exports/result.json",
            "/api/backtests/{backtest_id}/exports/trades.csv",
        ]
        for path in export_routes[:2] + export_routes[2:]:
            content = schema["paths"][path]["get"]["responses"]["200"]["content"]
            expected = "application/json" if path.endswith("result.json") else "text/csv"
            assert list(content) == [expected], (path, content)

    def test_report_pdf_is_not_registered_yet(self, api_app: FastAPI) -> None:
        assert not [path for path in api_app.openapi()["paths"] if "report.pdf" in path]


class TestRegression:
    def test_existing_backtest_operations_still_work(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, OWNER)
        created = create_run(client, dataset_id)
        run_id = created["id"]
        assert client.get("/api/backtests").status_code == 200
        assert client.get(f"/api/backtests/{run_id}").status_code == 200
        assert client.patch(f"/api/backtests/{run_id}", json={"name": "renamed"}).status_code == 200
        rerun = client.post(f"/api/backtests/{run_id}/rerun")
        assert rerun.status_code == 201
        duplicate = client.post(
            f"/api/backtests/{run_id}/duplicate", json={"configuration_overrides": {}}
        )
        assert duplicate.status_code == 201
        compare = client.post(
            "/api/backtests/compare",
            json={"backtest_ids": [run_id, rerun.json()["id"]]},
        )
        assert compare.status_code == 200
        assert client.delete(f"/api/backtests/{run_id}").status_code == 204

    def test_health_and_auth_unchanged(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200
        signup(client)
        assert client.get("/api/auth/me").status_code == 200

    def test_dataset_endpoints_unchanged(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        seed_dataset(session_factory, OWNER)
        assert client.get("/api/datasets").status_code == 200

    def test_base_metadata_still_nine_tables(self) -> None:
        from app.db import Base

        assert len(Base.metadata.tables) == 9


class TestArchitecture:
    def test_export_code_never_imports_or_runs_the_engine(self) -> None:
        for relative in (
            ("backtests", "exports.py"),
            ("api", "routes", "backtest_exports.py"),
        ):
            source = APP_DIR.joinpath(*relative).read_text(encoding="utf-8")
            assert "app.engine" not in source
            assert "run_backtest" not in source

    def test_exports_never_touch_the_filesystem(self) -> None:
        source = (APP_DIR / "backtests" / "exports.py").read_text(encoding="utf-8")
        # Generated in memory only: no file handles, paths, or temp dirs.
        assert "open(" not in source
        assert "tempfile" not in source
        assert "pathlib" not in source
        assert "Path(" not in source

    def test_exports_never_write_to_the_database(self) -> None:
        for relative in (
            ("backtests", "exports.py"),
            ("api", "routes", "backtest_exports.py"),
        ):
            source = APP_DIR.joinpath(*relative).read_text(encoding="utf-8")
            assert ".commit(" not in source
            assert ".flush(" not in source
            assert ".add(" not in source
            assert ".delete(" not in source
