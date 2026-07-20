"""Tests for the authenticated report.pdf export endpoint (SPEC 25.4, 32)."""

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
from pypdf import PdfReader
from sqlalchemy.orm import Session, sessionmaker

APP_DIR = Path(__file__).resolve().parents[2] / "app"

START = date(2026, 1, 5)

OWNER = "pdfowner@example.com"
STRANGER = "pdfstranger@example.com"


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


def seed_dataset(session_factory: sessionmaker[Session], email: str) -> int:
    with session_factory() as session:
        user_id = session.execute(sa.select(User.id).where(User.email == email)).scalar_one()
        dataset = Dataset(
            user_id=user_id,
            name="导出数据集",
            source_type="CSV",
            original_filename="export.csv",
            security_name="中概互联ETF",
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


def create_run(client: TestClient, dataset_id: int, name: str = "PDF Run") -> dict[str, Any]:
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


def pdf_path(backtest_id: int) -> str:
    return f"/api/backtests/{backtest_id}/exports/report.pdf"


def text_of(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class TestAuthentication:
    def test_unauthenticated_is_rejected(self, client: TestClient) -> None:
        response = client.get(pdf_path(1))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_invalid_cookie_is_rejected(self, client: TestClient) -> None:
        client.cookies.set("access_token", "garbage")
        assert client.get(pdf_path(1)).status_code == 401


class TestOwnership:
    def test_missing_run_returns_backtest_not_found(self, client: TestClient) -> None:
        signup(client)
        response = client.get(pdf_path(9999))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BACKTEST_NOT_FOUND"
        assert response.json()["error"]["message"] == "Backtest not found."

    def test_wrong_owner_returns_byte_identical_404(
        self, client: TestClient, api_app: FastAPI, owned_run: dict[str, Any]
    ) -> None:
        with TestClient(api_app) as other:
            signup(other, STRANGER)
            wrong_owner = other.get(pdf_path(owned_run["id"]))
            missing = other.get(pdf_path(9999))
        assert wrong_owner.status_code == 404
        assert wrong_owner.content == missing.content

    def test_404_matches_other_export_404s(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        signup(client)
        csv_404 = client.get("/api/backtests/9999/exports/trades.csv")
        detail_404 = client.get("/api/backtests/9999")
        pdf_404 = client.get(pdf_path(9999))
        assert pdf_404.content == csv_404.content == detail_404.content

    def test_deleted_run_returns_404(self, client: TestClient, owned_run: dict[str, Any]) -> None:
        run_id = owned_run["id"]
        assert client.delete(f"/api/backtests/{run_id}").status_code == 204
        assert client.get(pdf_path(run_id)).status_code == 404

    def test_response_reveals_no_ownership_information(self, client: TestClient) -> None:
        signup(client)
        body = client.get(pdf_path(9999)).text
        assert "user_id" not in body
        assert OWNER not in body
        assert "403" not in body


class TestResponse:
    def test_headers_and_filename(self, client: TestClient, owned_run: dict[str, Any]) -> None:
        response = client.get(pdf_path(owned_run["id"]))
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        disposition = response.headers["content-disposition"]
        assert disposition == f'attachment; filename="backtest-{owned_run["id"]}-report.pdf"'
        assert "inline" not in disposition

    def test_body_is_a_parseable_pdf_not_a_json_envelope(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        response = client.get(pdf_path(owned_run["id"]))
        data = response.content
        assert data.startswith(b"%PDF-")
        reader = PdfReader(io.BytesIO(data))
        assert len(reader.pages) >= 1
        # Binary PDF, never the standard JSON success envelope.
        with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
            json.loads(data)

    def test_filename_never_uses_the_editable_run_name(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, OWNER)
        run_id = create_run(client, dataset_id, name="../../etc/passwd 名称")["id"]
        disposition = client.get(pdf_path(run_id)).headers["content-disposition"]
        assert disposition == f'attachment; filename="backtest-{run_id}-report.pdf"'
        assert ".." not in disposition
        assert "passwd" not in disposition


class TestContent:
    def test_completed_run_report_content(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        text = text_of(client.get(pdf_path(owned_run["id"])).content)
        assert "PDF Run" in text
        assert "COMPLETED" in text
        assert "Core Metrics" in text
        assert "Buy-and-Hold Benchmarks" in text
        assert "Risk Disclaimer" in text

    def test_chinese_dataset_metadata_renders(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        text = text_of(client.get(pdf_path(owned_run["id"])).content)
        assert "中概互联ETF" in text
        assert "导出数据集" in text
        # No replacement characters or missing-glyph boxes.
        assert "�" not in text

    def test_metadata_title_uses_the_numeric_id(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        reader = PdfReader(io.BytesIO(client.get(pdf_path(owned_run["id"])).content))
        assert reader.metadata is not None
        assert reader.metadata.get("/Title") == f"Backtest Report {owned_run['id']}"

    def test_failed_run_produces_a_safe_report(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, OWNER)
        run_id = create_run(client, dataset_id)["id"]
        with session_factory() as session:
            run = session.get(BacktestRun, run_id)
            assert run is not None
            run.status = "FAILED"
            run.result_metrics = None
            run.error_message = "Sanitized engine failure."
            run.events.clear()
            run.daily_equity_rows.clear()
            session.commit()
        response = client.get(pdf_path(run_id))
        assert response.status_code == 200
        text = text_of(response.content)
        assert "FAILED" in text
        assert "Sanitized engine failure." in text
        assert "Result data is unavailable" in text

    def test_empty_series_run_still_downloads(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, OWNER)
        run_id = create_run(client, dataset_id)["id"]
        with session_factory() as session:
            run = session.get(BacktestRun, run_id)
            assert run is not None
            run.events.clear()
            run.daily_equity_rows.clear()
            session.commit()
        response = client.get(pdf_path(run_id))
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")


class TestNoSideEffects:
    def test_no_database_change_and_no_file_on_disk(
        self, client: TestClient, session_factory: sessionmaker[Session], owned_run: dict[str, Any]
    ) -> None:
        repo_root = APP_DIR.parents[1]

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
                }

        before = snapshot()
        pdfs_before = set(repo_root.rglob("*.pdf"))
        assert client.get(pdf_path(owned_run["id"])).status_code == 200
        assert snapshot() == before
        assert set(repo_root.rglob("*.pdf")) == pdfs_before


class TestOpenApi:
    def test_all_four_export_routes_with_correct_media_types(self, api_app: FastAPI) -> None:
        schema = api_app.openapi()
        paths = schema["paths"]
        export_routes = sorted(path for path in paths if "/exports/" in path)
        assert export_routes == [
            "/api/backtests/{backtest_id}/exports/equity.csv",
            "/api/backtests/{backtest_id}/exports/report.pdf",
            "/api/backtests/{backtest_id}/exports/result.json",
            "/api/backtests/{backtest_id}/exports/trades.csv",
        ]
        expected = {
            "trades.csv": "text/csv",
            "equity.csv": "text/csv",
            "result.json": "application/json",
            "report.pdf": "application/pdf",
        }
        for path in export_routes:
            leaf = path.rsplit("/", 1)[-1]
            content = paths[path]["get"]["responses"]["200"]["content"]
            assert list(content) == [expected[leaf]], (path, content)

    def test_no_unrelated_paths_added(self, api_app: FastAPI) -> None:
        paths = set(api_app.openapi()["paths"])
        assert paths == {
            "/health",
            "/api/auth/register",
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/me",
            "/api/datasets/preview",
            "/api/datasets",
            "/api/datasets/{dataset_id}",
            "/api/backtests",
            "/api/backtests/compare",
            "/api/backtests/{backtest_id}",
            "/api/backtests/{backtest_id}/rerun",
            "/api/backtests/{backtest_id}/duplicate",
            "/api/backtests/{backtest_id}/exports/trades.csv",
            "/api/backtests/{backtest_id}/exports/equity.csv",
            "/api/backtests/{backtest_id}/exports/result.json",
            "/api/backtests/{backtest_id}/exports/report.pdf",
        }


class TestRegression:
    def test_task_19a_exports_unchanged(
        self, client: TestClient, owned_run: dict[str, Any]
    ) -> None:
        run_id = owned_run["id"]
        base = f"/api/backtests/{run_id}/exports"
        trades = client.get(f"{base}/trades.csv")
        equity = client.get(f"{base}/equity.csv")
        result = client.get(f"{base}/result.json")
        assert trades.headers["content-type"] == "text/csv; charset=utf-8"
        assert equity.headers["content-type"] == "text/csv; charset=utf-8"
        assert result.headers["content-type"].startswith("application/json")
        assert trades.text.splitlines()[0] == (
            "date,event_sequence,side,grid_price,execution_price,shares,notional,"
            "commission,slippage_cost,cash_after,shares_after,equity_after,status,skip_reason"
        )
        assert equity.text.splitlines()[0] == (
            "backtest_run_id,date,close,cash,shares,equity,drawdown,zone_at_close"
        )
        assert list(json.loads(result.content)) == [
            "configuration",
            "result_metrics",
            "benchmark_1",
            "benchmark_2",
            "dataset_summary",
        ]

    def test_eight_backtest_operations_unchanged(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, OWNER)
        run_id = create_run(client, dataset_id)["id"]
        assert client.get("/api/backtests").status_code == 200
        assert client.get(f"/api/backtests/{run_id}").status_code == 200
        assert client.patch(f"/api/backtests/{run_id}", json={"name": "r"}).status_code == 200
        rerun = client.post(f"/api/backtests/{run_id}/rerun")
        assert rerun.status_code == 201
        assert (
            client.post(
                f"/api/backtests/{run_id}/duplicate", json={"configuration_overrides": {}}
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/backtests/compare",
                json={"backtest_ids": [run_id, rerun.json()["id"]]},
            ).status_code
            == 200
        )
        assert client.delete(f"/api/backtests/{run_id}").status_code == 204

    def test_auth_dataset_health_unchanged(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        assert client.get("/health").status_code == 200
        signup(client)
        seed_dataset(session_factory, OWNER)
        assert client.get("/api/auth/me").status_code == 200
        assert client.get("/api/datasets").status_code == 200

    def test_base_metadata_still_nine_tables(self) -> None:
        from app.db import Base

        assert len(Base.metadata.tables) == 9


class TestArchitecture:
    def test_pdf_code_never_imports_or_runs_the_engine(self) -> None:
        source = (APP_DIR / "backtests" / "pdf_report.py").read_text(encoding="utf-8")
        assert "app.engine" not in source
        assert "run_backtest" not in source

    def test_pdf_code_never_touches_the_filesystem(self) -> None:
        source = (APP_DIR / "backtests" / "pdf_report.py").read_text(encoding="utf-8")
        assert "open(" not in source
        assert "tempfile" not in source
        assert "pathlib" not in source

    def test_pdf_code_never_writes_to_the_database(self) -> None:
        source = (APP_DIR / "backtests" / "pdf_report.py").read_text(encoding="utf-8")
        assert ".commit(" not in source
        assert ".flush(" not in source
        # `drawing.add(...)` is ReportLab's canvas API; only session writes matter.
        assert "session.add(" not in source
        assert "session.delete(" not in source

    def test_no_font_files_are_tracked(self) -> None:
        repo_root = APP_DIR.parents[1]
        fonts = [
            path
            for pattern in ("*.ttf", "*.otf", "*.ttc", "*.woff", "*.woff2")
            for path in repo_root.rglob(pattern)
            if ".venv" not in path.parts and "node_modules" not in path.parts
        ]
        assert not fonts, fonts
