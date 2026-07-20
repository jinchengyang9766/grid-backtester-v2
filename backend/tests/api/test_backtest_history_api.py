"""Tests for GET/PATCH/DELETE /api/backtests history endpoints."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
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
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

START = date(2026, 1, 5)

BASE_DETAIL_KEYS = {
    "id",
    "dataset_id",
    "dataset",
    "name",
    "status",
    "configuration",
    "ohlc_path_mode",
    "start_date",
    "end_date",
    "result_metrics",
    "error_message",
    "created_at",
    "completed_at",
}
SERIES_KEYS = {"trades", "zone_events", "daily_equity", "event_equity"}


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


FAILING_SLIPPAGE = {
    "shared": False,
    "mode": None,
    "value": None,
    "buy": {"mode": "FIXED", "value": "0"},
    "sell": {"mode": "FIXED", "value": "20"},
}


def signup(client: TestClient, email: str = "hist@example.com") -> None:
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    login(client, email)


def login(client: TestClient, email: str = "hist@example.com") -> None:
    client.post("/api/auth/login", json={"email": email, "password": "password123"})


def seed_dataset(session_factory: sessionmaker[Session], email: str, name: str = "hist-ds") -> int:
    with session_factory() as session:
        user_id = session.execute(sa.select(User.id).where(User.email == email)).scalar_one()
        dataset = Dataset(
            user_id=user_id,
            name=name,
            source_type="CSV",
            original_filename=f"{name}.csv",
            security_name=None,
            security_code="159999",
            data_mode="CLOSE_ONLY",
            start_date=START,
            end_date=START + timedelta(days=2),
            row_count=3,
            column_mapping={"date": "Date", "close": "Close"},
            cleaning_summary={"bad_rows": 0},
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
        return dataset.id


def create_run(
    client: TestClient, dataset_id: int, name: str | None = None, **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": dataset_id,
        "configuration": configuration(**overrides),
    }
    if name is not None:
        payload["name"] = name
    response = client.post("/api/backtests", json=payload)
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def child_counts(session_factory: sessionmaker[Session]) -> dict[str, int]:
    with session_factory() as session:
        return {
            model.__tablename__: session.execute(
                sa.select(sa.func.count()).select_from(model)
            ).scalar_one()
            for model in (BacktestEvent, Trade, ZoneEventRecord, EventEquity, DailyEquity)
        }


class TestAuthentication:
    def test_all_history_endpoints_require_authentication(self, client: TestClient) -> None:
        for response in (
            client.get("/api/backtests"),
            client.get("/api/backtests/1"),
            client.patch("/api/backtests/1", json={"name": "x"}),
            client.delete("/api/backtests/1"),
        ):
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_invalid_cookie_401(self, client: TestClient) -> None:
        client.cookies.set("access_token", "garbage")
        assert client.get("/api/backtests").status_code == 401


class TestList:
    def test_shape_defaults_and_owned_only(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, "alice@example.com")
        alice_dataset = seed_dataset(session_factory, "alice@example.com", "alice-ds")
        first = create_run(client, alice_dataset, name="alpha run")
        second = create_run(client, alice_dataset, name="beta run")
        signup(client, "bob@example.com")
        bob_dataset = seed_dataset(session_factory, "bob@example.com", "bob-ds")
        create_run(client, bob_dataset, name="bob run")

        login(client, "alice@example.com")
        response = client.get("/api/backtests")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "total", "limit", "offset"}
        assert body["total"] == 2
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]
        assert all(item["dataset_name"] == "alice-ds" for item in body["items"])
        assert "configuration" not in response.json()["items"][0]
        for series in SERIES_KEYS:
            assert series not in body["items"][0]
        assert "user_id" not in response.text

    def test_pagination_and_invalid_values(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        ids = [create_run(client, dataset_id, name=f"run {index}")["id"] for index in range(3)]
        page = client.get("/api/backtests", params={"limit": 1, "offset": 1}).json()
        assert page["total"] == 3
        assert page["limit"] == 1
        assert page["offset"] == 1
        assert [item["id"] for item in page["items"]] == [ids[1]]
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            invalid = client.get("/api/backtests", params=params)
            assert invalid.status_code == 422
            assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_search_and_filters(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        first = seed_dataset(session_factory, "hist@example.com", "first-ds")
        second = seed_dataset(session_factory, "hist@example.com", "second-ds")
        alpha = create_run(client, first, name="Grid Alpha")
        create_run(client, second, name="Grid Beta")
        failed = client.post(
            "/api/backtests",
            json={
                "dataset_id": first,
                "name": "Broken run",
                "configuration": configuration(slippage=FAILING_SLIPPAGE),
            },
        ).json()
        assert failed["status"] == "FAILED"

        search = client.get("/api/backtests", params={"search": "grid alpha"}).json()
        assert [item["id"] for item in search["items"]] == [alpha["id"]]
        by_dataset = client.get("/api/backtests", params={"dataset_id": second}).json()
        assert by_dataset["total"] == 1
        by_status = client.get("/api/backtests", params={"status": "FAILED"}).json()
        assert [item["id"] for item in by_status["items"]] == [failed["id"]]
        combined = client.get(
            "/api/backtests", params={"dataset_id": first, "status": "COMPLETED"}
        ).json()
        assert [item["id"] for item in combined["items"]] == [alpha["id"]]
        invalid = client.get("/api/backtests", params={"status": "DONE"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


class TestDetail:
    def test_base_detail_has_no_series(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        created = create_run(client, dataset_id, name="detail run")
        response = client.get(f"/api/backtests/{created['id']}")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == BASE_DETAIL_KEYS
        assert body["configuration"]["grid_step"] == {"mode": "FIXED", "value": "1"}
        assert body["result_metrics"]["grid_levels"]
        assert set(body["dataset"]) == {
            "id",
            "name",
            "source_type",
            "original_filename",
            "security_name",
            "security_code",
            "data_mode",
            "start_date",
            "end_date",
            "row_count",
        }
        assert "user_id" not in response.text
        assert "price_bars" not in response.text

    def test_each_include_and_all_together(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        run_id = create_run(client, dataset_id)["id"]
        for series in sorted(SERIES_KEYS):
            body = client.get(f"/api/backtests/{run_id}", params={"include": series}).json()
            assert set(body) == BASE_DETAIL_KEYS | {series}
            assert isinstance(body[series], list)
            assert body[series]
        everything = client.get(
            f"/api/backtests/{run_id}",
            params={"include": "trades,zone_events,daily_equity,event_equity"},
        ).json()
        assert set(everything) == BASE_DETAIL_KEYS | SERIES_KEYS
        assert len(everything["trades"]) == 3
        assert len(everything["zone_events"]) == 2
        assert len(everything["daily_equity"]) == 3
        assert len(everything["event_equity"]) == 5
        sequences = [event["event_sequence"] for event in everything["event_equity"]]
        assert sequences == [1, 2, 3, 4, 5]
        assert all(isinstance(t["grid_price"], str) for t in everything["trades"])

    def test_include_order_duplicates_and_unknown(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        run_id = create_run(client, dataset_id)["id"]
        forward = client.get(
            f"/api/backtests/{run_id}", params={"include": "trades,daily_equity"}
        ).json()
        backward = client.get(
            f"/api/backtests/{run_id}", params={"include": " daily_equity , trades "}
        ).json()
        assert forward == backward
        deduplicated = client.get(
            f"/api/backtests/{run_id}", params={"include": "trades,trades"}
        ).json()
        assert len(deduplicated["trades"]) == 3
        unknown = client.get(f"/api/backtests/{run_id}", params={"include": "trades,bogus"})
        assert unknown.status_code == 422
        body = unknown.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["details"]["invalid_includes"] == ["bogus"]

    def test_missing_and_wrong_owner_identical_404(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, "owner@example.com")
        dataset_id = seed_dataset(session_factory, "owner@example.com")
        run_id = create_run(client, dataset_id)["id"]
        signup(client, "intruder@example.com")
        wrong_owner = client.get(f"/api/backtests/{run_id}")
        missing = client.get("/api/backtests/987654")
        assert wrong_owner.status_code == missing.status_code == 404
        assert wrong_owner.json() == missing.json()
        assert wrong_owner.json() == {
            "error": {"code": "BACKTEST_NOT_FOUND", "message": "Backtest not found."}
        }

    def test_failed_run_detail(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        failed = client.post(
            "/api/backtests",
            json={
                "dataset_id": dataset_id,
                "configuration": configuration(slippage=FAILING_SLIPPAGE),
            },
        ).json()
        body = client.get(
            f"/api/backtests/{failed['id']}",
            params={"include": "trades,zone_events,daily_equity,event_equity"},
        ).json()
        assert body["status"] == "FAILED"
        assert body["result_metrics"] is None
        assert body["error_message"]
        for series in SERIES_KEYS:
            assert body[series] == []


class TestRename:
    def test_rename_success_trims_and_changes_only_name(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        run_id = create_run(client, dataset_id, name="Old Name")["id"]
        before = client.get(f"/api/backtests/{run_id}").json()
        before_children = child_counts(session_factory)

        response = client.patch(f"/api/backtests/{run_id}", json={"name": "  New Name  "})
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "New Name"
        assert set(body) == BASE_DETAIL_KEYS
        after = client.get(f"/api/backtests/{run_id}").json()
        assert after["name"] == "New Name"
        assert {k: v for k, v in after.items() if k != "name"} == {
            k: v for k, v in before.items() if k != "name"
        }
        assert child_counts(session_factory) == before_children

    def test_extra_field_is_immutable_field(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        run_id = create_run(client, dataset_id)["id"]
        response = client.patch(f"/api/backtests/{run_id}", json={"name": "x", "status": "PENDING"})
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "IMMUTABLE_FIELD"
        assert body["error"]["details"]["fields"] == ["status"]

    def test_blank_or_missing_name_validation_error(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        run_id = create_run(client, dataset_id)["id"]
        for payload in ({}, {"name": "   "}, {"name": 5}):
            response = client.patch(f"/api/backtests/{run_id}", json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_missing_and_wrong_owner_identical_404(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, "owner@example.com")
        dataset_id = seed_dataset(session_factory, "owner@example.com")
        run_id = create_run(client, dataset_id)["id"]
        signup(client, "intruder@example.com")
        wrong_owner = client.patch(f"/api/backtests/{run_id}", json={"name": "hijack"})
        missing = client.patch("/api/backtests/876543", json={"name": "ghost"})
        assert wrong_owner.status_code == missing.status_code == 404
        assert wrong_owner.json() == missing.json()


class TestDelete:
    def test_delete_cascades_and_unblocks_dataset(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "hist@example.com")
        first = create_run(client, dataset_id)["id"]
        second = create_run(client, dataset_id)["id"]
        assert client.delete(f"/api/datasets/{dataset_id}").status_code == 409

        response = client.delete(f"/api/backtests/{first}")
        assert response.status_code == 204
        assert response.content == b""
        assert client.delete(f"/api/backtests/{first}").status_code == 404
        remaining = client.get("/api/backtests").json()
        assert [item["id"] for item in remaining["items"]] == [second]
        with session_factory() as session:
            assert session.execute(sa.select(sa.func.count()).select_from(User)).scalar_one() == 1
            bars = session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one()
            assert bars == 3

        assert client.delete(f"/api/backtests/{second}").status_code == 204
        assert child_counts(session_factory) == {
            "backtest_events": 0,
            "trades": 0,
            "zone_events": 0,
            "event_equity": 0,
            "daily_equity": 0,
        }
        # Dataset became deletable once its last run was removed.
        assert client.delete(f"/api/datasets/{dataset_id}").status_code == 204

    def test_wrong_owner_delete_identical_404_and_run_survives(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, "owner@example.com")
        dataset_id = seed_dataset(session_factory, "owner@example.com")
        run_id = create_run(client, dataset_id)["id"]
        signup(client, "intruder@example.com")
        wrong_owner = client.delete(f"/api/backtests/{run_id}")
        missing = client.delete("/api/backtests/765432")
        assert wrong_owner.status_code == missing.status_code == 404
        assert wrong_owner.json() == missing.json()
        with session_factory() as session:
            assert session.get(BacktestRun, run_id) is not None


class TestRegressionAndOpenApi:
    def test_health_auth_datasets_unchanged_and_nine_tables(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        assert client.get("/health").status_code == 200
        signup(client, "reg@example.com")
        assert client.get("/api/auth/me").status_code == 200
        assert client.get("/api/datasets").status_code == 200
        assert len(Base.metadata.tables) == 9

    def test_openapi_paths_exact(self, api_app: FastAPI) -> None:
        paths = api_app.openapi()["paths"]
        assert set(paths["/api/backtests"]) == {"post", "get"}
        assert set(paths["/api/backtests/{backtest_id}"]) == {"get", "patch", "delete"}
        # Exports live on their own sub-paths and never add a method to the
        # list/detail routes. The export surface is now complete (Task 19B).
        assert sorted(path for path in paths if "/exports/" in path) == [
            "/api/backtests/{backtest_id}/exports/equity.csv",
            "/api/backtests/{backtest_id}/exports/report.pdf",
            "/api/backtests/{backtest_id}/exports/result.json",
            "/api/backtests/{backtest_id}/exports/trades.csv",
        ]
