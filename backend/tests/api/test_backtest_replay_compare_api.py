"""Tests for POST rerun, duplicate, and compare backtest endpoints."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from app.db import Base
from app.db.models import BacktestEvent, Dataset, PriceBar, User
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

START = date(2026, 1, 5)


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


def signup(client: TestClient, email: str = "rc@example.com") -> None:
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    login(client, email)


def login(client: TestClient, email: str = "rc@example.com") -> None:
    client.post("/api/auth/login", json={"email": email, "password": "password123"})


def seed_dataset(session_factory: sessionmaker[Session], email: str) -> int:
    with session_factory() as session:
        user_id = session.execute(sa.select(User.id).where(User.email == email)).scalar_one()
        dataset = Dataset(
            user_id=user_id,
            name="rc-ds",
            source_type="CSV",
            original_filename="rc.csv",
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
                    dataset_id=dataset.id, date=START + timedelta(days=offset), close=Decimal(close)
                )
            )
        session.commit()
        return dataset.id


def create_run(
    client: TestClient, dataset_id: int, name: str = "Source", **overrides: Any
) -> dict[str, Any]:
    response = client.post(
        "/api/backtests",
        json={"dataset_id": dataset_id, "name": name, "configuration": configuration(**overrides)},
    )
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def event_count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.execute(sa.select(sa.func.count()).select_from(BacktestEvent)).scalar_one()


class TestAuthentication:
    def test_unauthenticated(self, client: TestClient) -> None:
        for response in (
            client.post("/api/backtests/1/rerun"),
            client.post("/api/backtests/1/duplicate", json={"configuration_overrides": {}}),
            client.post("/api/backtests/compare", json={"backtest_ids": [1, 2]}),
        ):
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_invalid_cookie(self, client: TestClient) -> None:
        client.cookies.set("access_token", "garbage")
        assert client.post("/api/backtests/1/rerun").status_code == 401


class TestRerun:
    def test_rerun_success_no_body(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        source = create_run(client, dataset_id, name="Custom Source Name")
        before_events = event_count(session_factory)

        response = client.post(f"/api/backtests/{source['id']}/rerun")
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "COMPLETED"
        assert body["status"] not in ("PENDING", "RUNNING")
        assert body["id"] != source["id"]
        assert body["name"] != "Custom Source Name"

        # Source unchanged; new run has independent children.
        source_detail = client.get(f"/api/backtests/{source['id']}").json()
        assert source_detail["name"] == "Custom Source Name"
        assert event_count(session_factory) == before_events * 2
        new_detail = client.get(f"/api/backtests/{body['id']}").json()
        assert new_detail["configuration"] == source_detail["configuration"]

    def test_rerun_missing_and_wrong_owner_identical_404(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, "owner@example.com")
        dataset_id = seed_dataset(session_factory, "owner@example.com")
        source = create_run(client, dataset_id)
        signup(client, "intruder@example.com")
        wrong = client.post(f"/api/backtests/{source['id']}/rerun")
        missing = client.post("/api/backtests/999999/rerun")
        assert wrong.status_code == missing.status_code == 404
        assert wrong.json() == missing.json()
        assert wrong.json() == {
            "error": {"code": "BACKTEST_NOT_FOUND", "message": "Backtest not found."}
        }

    def test_rerun_runtime_failure_returns_201_failed(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        failed = create_run(
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
        assert failed["status"] == "FAILED"
        response = client.post(f"/api/backtests/{failed['id']}/rerun")
        assert response.status_code == 201
        assert response.json()["status"] == "FAILED"
        assert response.json()["id"] != failed["id"]


class TestDuplicate:
    def test_empty_override(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        source = create_run(client, dataset_id)
        response = client.post(
            f"/api/backtests/{source['id']}/duplicate", json={"configuration_overrides": {}}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["id"] != source["id"]
        assert body["status"] == "COMPLETED"
        source_detail = client.get(f"/api/backtests/{source['id']}").json()
        new_detail = client.get(f"/api/backtests/{body['id']}").json()
        assert new_detail["configuration"] == source_detail["configuration"]

    def test_duplicate_defaults_to_empty_override(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        source = create_run(client, dataset_id)
        # No body at all -> configuration_overrides defaults to {}.
        response = client.post(f"/api/backtests/{source['id']}/duplicate", json={})
        assert response.status_code == 201

    def test_nested_override_merges_and_source_unchanged(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        source = create_run(client, dataset_id)
        source_config_before = client.get(f"/api/backtests/{source['id']}").json()["configuration"]
        response = client.post(
            f"/api/backtests/{source['id']}/duplicate",
            json={"configuration_overrides": {"grid_step": {"value": "2"}}},
        )
        assert response.status_code == 201
        new_detail = client.get(f"/api/backtests/{response.json()['id']}").json()
        assert new_detail["configuration"]["grid_step"] == {"mode": "FIXED", "value": "2"}
        assert new_detail["configuration"]["a_distance"] == source_config_before["a_distance"]
        source_after = client.get(f"/api/backtests/{source['id']}").json()
        assert source_after["configuration"] == source_config_before

    def test_slippage_side_override(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        source = create_run(
            client,
            dataset_id,
            slippage={
                "shared": False,
                "mode": None,
                "value": None,
                "buy": {"mode": "FIXED", "value": "0"},
                "sell": {"mode": "FIXED", "value": "0"},
            },
        )
        response = client.post(
            f"/api/backtests/{source['id']}/duplicate",
            json={"configuration_overrides": {"slippage": {"buy": {"value": "0.001"}}}},
        )
        assert response.status_code == 201
        new_config = client.get(f"/api/backtests/{response.json()['id']}").json()["configuration"]
        assert new_config["slippage"]["buy"] == {"mode": "FIXED", "value": "0.001"}
        assert new_config["slippage"]["sell"] == {"mode": "FIXED", "value": "0"}

    def test_unknown_override_field_422_no_run(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        source = create_run(client, dataset_id)
        before = event_count(session_factory)
        response = client.post(
            f"/api/backtests/{source['id']}/duplicate",
            json={"configuration_overrides": {"bogus": 1}},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert event_count(session_factory) == before

    def test_invalid_merged_config_specific_code(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        source = create_run(client, dataset_id)
        response = client.post(
            f"/api/backtests/{source['id']}/duplicate",
            json={"configuration_overrides": {"c_distance": {"value": "2"}}},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_ZONE_CONFIG"

    def test_missing_and_wrong_owner_identical_404(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, "owner@example.com")
        dataset_id = seed_dataset(session_factory, "owner@example.com")
        source = create_run(client, dataset_id)
        signup(client, "intruder@example.com")
        wrong = client.post(
            f"/api/backtests/{source['id']}/duplicate", json={"configuration_overrides": {}}
        )
        missing = client.post(
            "/api/backtests/999999/duplicate", json={"configuration_overrides": {}}
        )
        assert wrong.status_code == missing.status_code == 404
        assert wrong.json() == missing.json()

    def test_extra_top_level_field_rejected(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        source = create_run(client, dataset_id)
        response = client.post(
            f"/api/backtests/{source['id']}/duplicate",
            json={"configuration_overrides": {}, "dataset_id": 5},
        )
        assert response.status_code == 422


class TestCompare:
    def test_compare_preserves_request_order(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        first = create_run(client, dataset_id, name="First")["id"]
        second = create_run(client, dataset_id, name="Second")["id"]
        third = create_run(client, dataset_id, name="Third")["id"]
        response = client.post(
            "/api/backtests/compare", json={"backtest_ids": [third, first, second]}
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"runs"}
        assert [run["id"] for run in body["runs"]] == [third, first, second]
        for run in body["runs"]:
            assert set(run) == {"id", "name", "result_metrics"}
            assert "configuration" not in run
            assert "user_id" not in run
        assert body["runs"][0]["name"] == "Third"

    def test_compare_preserves_stored_metrics_and_failed_null(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        completed = create_run(client, dataset_id)["id"]
        failed = client.post(
            "/api/backtests",
            json={
                "dataset_id": dataset_id,
                "configuration": configuration(
                    slippage={
                        "shared": False,
                        "mode": None,
                        "value": None,
                        "buy": {"mode": "FIXED", "value": "0"},
                        "sell": {"mode": "FIXED", "value": "20"},
                    }
                ),
            },
        ).json()["id"]
        stored_metrics = client.get(f"/api/backtests/{completed}").json()["result_metrics"]
        response = client.post("/api/backtests/compare", json={"backtest_ids": [completed, failed]})
        body = response.json()
        assert body["runs"][0]["result_metrics"] == stored_metrics
        assert body["runs"][1]["result_metrics"] is None

    def test_compare_validation_errors(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        one = create_run(client, dataset_id)["id"]
        for payload in (
            {"backtest_ids": [one]},
            {"backtest_ids": [one, one]},
            {"backtest_ids": [one, -3]},
            {"backtest_ids": [one, 0]},
            {"backtest_ids": [one, 2], "extra": 1},
        ):
            response = client.post("/api/backtests/compare", json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_compare_all_or_nothing_missing_and_wrong_owner(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, "owner@example.com")
        dataset_id = seed_dataset(session_factory, "owner@example.com")
        owned_a = create_run(client, dataset_id, name="A")["id"]
        owned_b = create_run(client, dataset_id, name="B")["id"]
        # A foreign run.
        signup(client, "intruder@example.com")
        intruder_ds = seed_dataset(session_factory, "intruder@example.com")
        foreign = create_run(client, intruder_ds, name="Foreign")["id"]

        login(client, "owner@example.com")
        missing = client.post("/api/backtests/compare", json={"backtest_ids": [owned_a, 987654]})
        wrong_owner = client.post(
            "/api/backtests/compare", json={"backtest_ids": [owned_a, foreign]}
        )
        assert missing.status_code == wrong_owner.status_code == 404
        assert missing.json() == wrong_owner.json()
        assert missing.json() == {
            "error": {"code": "BACKTEST_NOT_FOUND", "message": "Backtest not found."}
        }
        # A fully-owned comparison still succeeds.
        ok = client.post("/api/backtests/compare", json={"backtest_ids": [owned_a, owned_b]})
        assert ok.status_code == 200

    def test_compare_route_is_static_not_path_param(self, api_app: FastAPI) -> None:
        paths = api_app.openapi()["paths"]
        assert "/api/backtests/compare" in paths
        assert "post" in paths["/api/backtests/compare"]


class TestOpenApiAndRegression:
    def test_all_eight_operations_and_no_exports(self, api_app: FastAPI) -> None:
        paths = api_app.openapi()["paths"]
        assert set(paths["/api/backtests"]) == {"post", "get"}
        assert set(paths["/api/backtests/{backtest_id}"]) == {"get", "patch", "delete"}
        assert "post" in paths["/api/backtests/compare"]
        assert "post" in paths["/api/backtests/{backtest_id}/rerun"]
        assert "post" in paths["/api/backtests/{backtest_id}/duplicate"]
        # The eight operations are unchanged by the read-only export GETs,
        # whose surface is now complete (Task 19B).
        assert sorted(path for path in paths if "/exports/" in path) == [
            "/api/backtests/{backtest_id}/exports/equity.csv",
            "/api/backtests/{backtest_id}/exports/report.pdf",
            "/api/backtests/{backtest_id}/exports/result.json",
            "/api/backtests/{backtest_id}/exports/trades.csv",
        ]
        schemas = api_app.openapi()["components"]["schemas"]
        assert "BacktestDuplicateRequest" in schemas
        assert "BacktestCompareRequest" in schemas
        assert "BacktestCompareResponse" in schemas

    def test_existing_endpoints_unchanged(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        assert client.get("/health").status_code == 200
        signup(client)
        dataset_id = seed_dataset(session_factory, "rc@example.com")
        created = create_run(client, dataset_id)
        assert client.get("/api/backtests").status_code == 200
        assert client.get(f"/api/backtests/{created['id']}").status_code == 200
        assert (
            client.patch(f"/api/backtests/{created['id']}", json={"name": "Renamed"}).status_code
            == 200
        )
        assert client.get("/api/datasets").status_code == 200
        assert client.get("/api/auth/me").status_code == 200
        assert len(Base.metadata.tables) == 9
