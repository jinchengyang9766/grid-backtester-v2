"""Tests for POST /api/backtests (synchronous create + persist)."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
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
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

START = date(2026, 1, 5)
APP_DIR = Path(__file__).resolve().parents[2] / "app"


def base_configuration(**overrides: Any) -> dict[str, Any]:
    configuration: dict[str, Any] = {
        "initial_cash": "1000.00",
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
    configuration.update(overrides)
    return configuration


def signup(client: TestClient, email: str = "bt@example.com") -> None:
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    login(client, email)


def login(client: TestClient, email: str = "bt@example.com") -> None:
    client.post("/api/auth/login", json={"email": email, "password": "password123"})


def seed_dataset(
    session_factory: sessionmaker[Session],
    email: str,
    *,
    closes: list[str] | None = None,
    data_mode: str = "CLOSE_ONLY",
    security_code: str | None = "159999",
) -> int:
    closes = closes if closes is not None else ["10", "7", "10"]
    with session_factory() as session:
        user_id = session.execute(sa.select(User.id).where(User.email == email)).scalar_one()
        dataset = Dataset(
            user_id=user_id,
            name="api-ds",
            source_type="CSV",
            original_filename="a.csv",
            security_name=None,
            security_code=security_code,
            data_mode=data_mode,
            start_date=START,
            end_date=START + timedelta(days=len(closes) - 1),
            row_count=len(closes),
            column_mapping={"date": "Date", "close": "Close"},
            cleaning_summary={"bad_rows": 0},
        )
        session.add(dataset)
        session.flush()
        for offset, close in enumerate(closes):
            if data_mode == "OHLCV":
                value = Decimal(close)
                session.add(
                    PriceBar(
                        dataset_id=dataset.id,
                        date=START + timedelta(days=offset),
                        open=value,
                        high=value + Decimal("0.5"),
                        low=value - Decimal("0.5"),
                        close=value,
                    )
                )
            else:
                session.add(
                    PriceBar(
                        dataset_id=dataset.id,
                        date=START + timedelta(days=offset),
                        close=Decimal(close),
                    )
                )
        session.commit()
        return dataset.id


def post_backtest(
    client: TestClient, dataset_id: int, name: str | None = None, **overrides: Any
) -> httpx.Response:
    payload: dict[str, Any] = {
        "dataset_id": dataset_id,
        "configuration": base_configuration(**overrides),
    }
    if name is not None:
        payload["name"] = name
    response: httpx.Response = client.post("/api/backtests", json=payload)
    return response


def run_count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.execute(sa.select(sa.func.count()).select_from(BacktestRun)).scalar_one()


class TestAuthenticationAndOwnership:
    def test_unauthenticated_401(self, client: TestClient) -> None:
        response = post_backtest(client, 1)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_missing_and_foreign_dataset_identical_404(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, "owner@example.com")
        dataset_id = seed_dataset(session_factory, "owner@example.com")
        signup(client, "intruder@example.com")
        foreign = post_backtest(client, dataset_id)
        missing = post_backtest(client, 424242)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
        assert foreign.json()["error"]["code"] == "DATASET_NOT_FOUND"
        assert run_count(session_factory) == 0


class TestSuccess:
    def test_close_only_201_completed(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "bt@example.com")
        response = post_backtest(client, dataset_id)
        assert response.status_code == 201
        body = response.json()
        assert set(body) == {
            "id",
            "status",
            "name",
            "created_at",
            "completed_at",
            "error_message",
            "result_metrics",
        }
        assert body["status"] == "COMPLETED"
        assert body["status"] not in ("PENDING", "RUNNING")
        assert body["completed_at"] is not None
        assert body["error_message"] is None
        assert body["result_metrics"]["grid_levels"]
        assert body["name"].startswith("159999 — A Grid 1 — ")
        with session_factory() as session:
            run = session.execute(sa.select(BacktestRun)).scalar_one()
            assert run.result_metrics == body["result_metrics"]
            assert run.dataset_id == dataset_id
            assert run.start_date == START
            user_id = session.execute(
                sa.select(User.id).where(User.email == "bt@example.com")
            ).scalar_one()
            assert run.user_id == user_id

    def test_ohlcv_201_completed_with_supplied_name(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(
            session_factory, "bt@example.com", data_mode="OHLCV", closes=["10", "9", "10"]
        )
        response = post_backtest(client, dataset_id, name="OHLCV Run", ohlc_path_mode="AUTO")
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "COMPLETED"
        assert body["name"] == "OHLCV Run"


class TestValidation:
    def test_structural_errors_422(self, client: TestClient) -> None:
        signup(client)
        response = client.post("/api/backtests", json={"dataset_id": 1})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_unknown_field_rejected(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "bt@example.com")
        response = client.post(
            "/api/backtests",
            json={
                "dataset_id": dataset_id,
                "configuration": base_configuration(),
                "user_id": 3,
            },
        )
        assert response.status_code == 422
        assert run_count(session_factory) == 0

    def test_mixed_slippage_shape_422(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "bt@example.com")
        response = post_backtest(
            client,
            dataset_id,
            slippage={
                "shared": True,
                "mode": "FIXED",
                "value": "0.001",
                "buy": {"mode": "FIXED", "value": "1"},
                "sell": None,
            },
        )
        assert response.status_code == 422
        assert run_count(session_factory) == 0

    def test_whitespace_name_422(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "bt@example.com")
        assert post_backtest(client, dataset_id, name="   ").status_code == 422

    def test_engine_validation_code_via_api_and_no_run(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "bt@example.com")
        response = post_backtest(client, dataset_id, c_distance={"mode": "FIXED", "value": "2"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_ZONE_CONFIG"
        assert run_count(session_factory) == 0


class TestRuntimeFailure:
    def test_supported_runtime_failure_201_failed(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "bt@example.com")
        response = post_backtest(
            client,
            dataset_id,
            slippage={
                "shared": False,
                "mode": None,
                "value": None,
                "buy": {"mode": "FIXED", "value": "0"},
                "sell": {"mode": "FIXED", "value": "20"},
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "FAILED"
        assert body["result_metrics"] is None
        assert body["error_message"]
        assert body["completed_at"] is not None
        assert "Traceback" not in response.text
        with session_factory() as session:
            for model in (BacktestEvent, Trade, ZoneEventRecord, EventEquity, DailyEquity):
                total = session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()
                assert total == 0


class TestUnexpectedFailure:
    def test_unexpected_error_rolls_back_and_uses_safe_500(
        self,
        api_app: FastAPI,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import app.backtests.service as service_module

        with TestClient(api_app, raise_server_exceptions=False) as tolerant_client:
            signup(tolerant_client)
            dataset_id = seed_dataset(session_factory, "bt@example.com")

            def broken_persist(*args: object, **kwargs: object) -> None:
                raise RuntimeError("secret internal detail")

            monkeypatch.setattr(service_module, "persist_completed_run", broken_persist)
            response = post_backtest(tolerant_client, dataset_id)
            assert response.status_code == 500
            assert "secret internal detail" not in response.text
            assert run_count(session_factory) == 0
            # Session/database remain usable afterward.
            monkeypatch.undo()
            assert post_backtest(tolerant_client, dataset_id).status_code == 201


class TestRegression:
    def test_dataset_delete_blocked_after_backtest_run(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        referenced = seed_dataset(session_factory, "bt@example.com")
        assert post_backtest(client, referenced).status_code == 201
        blocked = client.delete(f"/api/datasets/{referenced}")
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "DATASET_IN_USE"
        # An unrelated dataset still deletes.
        with session_factory() as session:
            user_id = session.execute(
                sa.select(User.id).where(User.email == "bt@example.com")
            ).scalar_one()
            unrelated = Dataset(
                user_id=user_id,
                name="unrelated",
                source_type="CSV",
                original_filename="u.csv",
                security_name=None,
                security_code=None,
                data_mode="CLOSE_ONLY",
                start_date=START,
                end_date=START,
                row_count=0,
                column_mapping={},
                cleaning_summary={},
            )
            session.add(unrelated)
            session.commit()
            unrelated_id = unrelated.id
        assert client.delete(f"/api/datasets/{unrelated_id}").status_code == 204

    def test_health_and_auth_unchanged(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200
        signup(client, "reg@example.com")
        assert client.get("/api/auth/me").status_code == 200


class TestOpenApiAndArchitecture:
    def test_openapi_backtest_paths(self, api_app: FastAPI) -> None:
        paths = api_app.openapi()["paths"]
        assert "post" in paths["/api/backtests"]
        # Exports are read-only GETs on their own sub-path (Task 19A); the
        # create route itself never gained one, and report.pdf is pending.
        assert not any("export" in path for path in paths if "post" in paths[path])
        assert not any("report.pdf" in path for path in paths)
        schemas = api_app.openapi()["components"]["schemas"]
        assert "BacktestCreateRequest" in schemas
        assert "BacktestCreateResponse" in schemas

    def test_route_and_persistence_layers_stay_clean(self) -> None:
        route_source = (APP_DIR / "api" / "routes" / "backtests.py").read_text(encoding="utf-8")
        # The route never imports the engine or invokes it directly; all
        # execution flows through services (create/rerun/duplicate).
        assert "app.engine" not in route_source
        assert "import run_backtest" not in route_source
        persistence_source = (APP_DIR / "backtests" / "persistence.py").read_text(encoding="utf-8")
        assert "compute_" not in persistence_source  # no metric recomputation
        for module in ("engine", "importing"):
            for path in (APP_DIR / module).rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                assert "app.backtests" not in source
                assert "fastapi" not in source
