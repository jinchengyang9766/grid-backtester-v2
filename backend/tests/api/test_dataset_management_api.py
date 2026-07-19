"""Tests for GET /api/datasets, GET/DELETE /api/datasets/{id}."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
import sqlalchemy as sa
from app.db.models import Dataset, PriceBar, User
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

CSV_TEXT = "Date,Close\n2024/07/23,1.05\n2024/07/24,1.10\n"


def signup(client: TestClient, email: str = "user@example.com") -> None:
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    login(client, email)


def login(client: TestClient, email: str = "user@example.com") -> None:
    client.post("/api/auth/login", json={"email": email, "password": "password123"})


def seed_user(session_factory: sessionmaker[Session], email: str) -> int:
    with session_factory() as session:
        user = User(email=email, password_hash="seeded-hash")
        session.add(user)
        session.commit()
        return user.id


def user_id_of(session_factory: sessionmaker[Session], email: str) -> int:
    with session_factory() as session:
        return session.execute(sa.select(User.id).where(User.email == email)).scalar_one()


def seed_dataset(
    session_factory: sessionmaker[Session],
    owner_id: int,
    name: str,
    *,
    created_at: datetime | None = None,
    bar_count: int = 2,
    security_name: str | None = "农业ETF富国",
    security_code: str | None = "159825",
) -> int:
    with session_factory() as session:
        dataset = Dataset(
            user_id=owner_id,
            name=name,
            source_type="TDX_XLS",
            original_filename=f"{name}.xls",
            security_name=security_name,
            security_code=security_code,
            data_mode="OHLCV",
            start_date=date(2024, 7, 23),
            end_date=date(2024, 7, 23) + timedelta(days=max(bar_count - 1, 0)),
            row_count=bar_count,
            column_mapping={"date": "时间", "close": "收盘"},
            cleaning_summary={"final_row_count": bar_count, "bad_rows": 0},
        )
        if created_at is not None:
            dataset.created_at = created_at
        session.add(dataset)
        for offset in range(bar_count):
            session.add(
                PriceBar(
                    dataset=dataset,
                    date=date(2024, 7, 23) + timedelta(days=offset),
                    open=Decimal("1.00000000"),
                    high=Decimal("1.10000000"),
                    low=Decimal("0.90000000"),
                    close=Decimal("1.05000000"),
                    volume=Decimal("1000"),
                )
            )
        session.commit()
        return dataset.id


def bar_count_for(session_factory: sessionmaker[Session], dataset_id: int) -> int:
    with session_factory() as session:
        return session.execute(
            sa.select(sa.func.count())
            .select_from(PriceBar)
            .where(PriceBar.dataset_id == dataset_id)
        ).scalar_one()


class TestAuthentication:
    def test_unauthenticated_requests_401(self, client: TestClient) -> None:
        for response in (
            client.get("/api/datasets"),
            client.get("/api/datasets/1"),
            client.delete("/api/datasets/1"),
        ):
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_invalid_cookie_401(self, client: TestClient) -> None:
        client.cookies.set("access_token", "garbage")
        assert client.get("/api/datasets").status_code == 401


class TestList:
    def test_empty_list_shape(self, client: TestClient) -> None:
        signup(client)
        response = client.get("/api/datasets")
        assert response.status_code == 200
        assert response.json() == {"items": []}

    def test_only_own_datasets_in_deterministic_order(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        other = seed_user(session_factory, "other@example.com")
        old = seed_dataset(session_factory, me, "old", created_at=datetime(2026, 1, 1, 10, 0))
        tied_a = seed_dataset(session_factory, me, "tied-a", created_at=datetime(2026, 1, 2, 10, 0))
        tied_b = seed_dataset(session_factory, me, "tied-b", created_at=datetime(2026, 1, 2, 10, 0))
        seed_dataset(session_factory, other, "foreign")

        body = client.get("/api/datasets").json()
        assert [item["id"] for item in body["items"]] == [tied_b, tied_a, old]

    def test_summary_fields_exact(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        seed_dataset(session_factory, me, "sample", bar_count=3)
        (item,) = client.get("/api/datasets").json()["items"]
        assert set(item) == {
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
            "created_at",
        }
        assert item["name"] == "sample"
        assert item["source_type"] == "TDX_XLS"
        assert item["security_name"] == "农业ETF富国"
        assert item["row_count"] == 3
        assert item["start_date"] == "2024-07-23"
        assert item["end_date"] == "2024-07-25"

    def test_list_excludes_sensitive_and_heavy_fields(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        seed_dataset(session_factory, me, "sample")
        response = client.get("/api/datasets")
        assert "user_id" not in response.text
        assert "column_mapping" not in response.text
        assert "cleaning_summary" not in response.text
        assert "price_bars" not in response.text


class TestDetail:
    def test_owned_detail_complete(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        dataset_id = seed_dataset(session_factory, me, "detailed", bar_count=2)
        response = client.get(f"/api/datasets/{dataset_id}")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
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
            "column_mapping",
            "cleaning_summary",
            "created_at",
        }
        assert body["column_mapping"] == {"date": "时间", "close": "收盘"}
        assert body["cleaning_summary"] == {"final_row_count": 2, "bad_rows": 0}
        assert "price_bars" not in response.text
        assert "user_id" not in response.text

    def test_nullable_security_fields_return_null(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        dataset_id = seed_dataset(
            session_factory, me, "anon", security_name=None, security_code=None
        )
        body = client.get(f"/api/datasets/{dataset_id}").json()
        assert body["security_name"] is None
        assert body["security_code"] is None

    def test_missing_and_wrong_owner_identical_404(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        other = seed_user(session_factory, "other@example.com")
        foreign_id = seed_dataset(session_factory, other, "foreign")

        missing = client.get("/api/datasets/999999")
        wrong_owner = client.get(f"/api/datasets/{foreign_id}")
        assert missing.status_code == wrong_owner.status_code == 404
        assert missing.json() == wrong_owner.json()
        assert missing.json() == {
            "error": {"code": "DATASET_NOT_FOUND", "message": "Dataset not found."}
        }

    def test_detail_does_not_mutate(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        dataset_id = seed_dataset(session_factory, me, "stable")
        with session_factory() as session:
            before = session.execute(sa.select(Dataset.name, Dataset.row_count)).all()
        assert client.get(f"/api/datasets/{dataset_id}").status_code == 200
        with session_factory() as session:
            assert session.execute(sa.select(Dataset.name, Dataset.row_count)).all() == before


class TestDelete:
    def test_owned_delete_204_cascades_and_spares_others(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        other = seed_user(session_factory, "other@example.com")
        target = seed_dataset(session_factory, me, "target", bar_count=3)
        keeper = seed_dataset(session_factory, me, "keeper", bar_count=2)
        foreign = seed_dataset(session_factory, other, "foreign", bar_count=4)

        response = client.delete(f"/api/datasets/{target}")
        assert response.status_code == 204
        assert response.content == b""

        assert bar_count_for(session_factory, target) == 0
        assert bar_count_for(session_factory, keeper) == 2
        assert bar_count_for(session_factory, foreign) == 4
        with session_factory() as session:
            remaining = set(session.execute(sa.select(Dataset.id)).scalars())
            assert remaining == {keeper, foreign}
            users = session.execute(sa.select(sa.func.count()).select_from(User)).scalar_one()
            assert users == 2

    def test_missing_wrong_owner_and_repeat_are_identical_404(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        other = seed_user(session_factory, "other@example.com")
        mine = seed_dataset(session_factory, me, "mine")
        foreign = seed_dataset(session_factory, other, "foreign")

        assert client.delete(f"/api/datasets/{mine}").status_code == 204
        repeat = client.delete(f"/api/datasets/{mine}")
        missing = client.delete("/api/datasets/999999")
        wrong_owner = client.delete(f"/api/datasets/{foreign}")
        assert repeat.json() == missing.json() == wrong_owner.json()
        assert repeat.status_code == missing.status_code == wrong_owner.status_code == 404
        # The wrong-owner attempt deleted nothing.
        assert bar_count_for(session_factory, foreign) == 2

    def test_restricted_delete_returns_409_and_keeps_rows(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        db_engine: Engine,
    ) -> None:
        signup(client)
        me = user_id_of(session_factory, "user@example.com")
        dataset_id = seed_dataset(session_factory, me, "referenced", bar_count=2)
        with db_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE test_only_refs ("
                "id INTEGER PRIMARY KEY, "
                "dataset_id INTEGER NOT NULL "
                "REFERENCES datasets(id) ON DELETE RESTRICT)"
            )
            connection.exec_driver_sql(
                "INSERT INTO test_only_refs (dataset_id) VALUES (?)", (dataset_id,)
            )

        response = client.delete(f"/api/datasets/{dataset_id}")
        assert response.status_code == 409
        assert response.json() == {
            "error": {
                "code": "DATASET_IN_USE",
                "message": "Dataset is referenced by existing resources and cannot be deleted.",
            }
        }
        assert "FOREIGN KEY" not in response.text
        assert "sqlite" not in response.text.lower()
        assert "constraint" not in response.text.lower()

        with session_factory() as session:
            assert (
                session.execute(sa.select(sa.func.count()).select_from(Dataset)).scalar_one() == 1
            )
        assert bar_count_for(session_factory, dataset_id) == 2


class TestRegression:
    def test_preview_save_flow_and_token_consumption_unchanged(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        preview: httpx.Response = client.post(
            "/api/datasets/preview",
            files={"file": ("flow.csv", CSV_TEXT.encode(), "text/csv")},
        )
        assert preview.status_code == 200
        token = preview.json()["preview_token"]
        saved = client.post("/api/datasets", json={"name": "Flow", "preview_token": token})
        assert saved.status_code == 201
        assert (
            client.post("/api/datasets", json={"name": "Again", "preview_token": token})
        ).status_code == 404
        # The saved dataset shows up in the new list endpoint.
        assert [item["name"] for item in client.get("/api/datasets").json()["items"]] == ["Flow"]

    def test_health_and_auth_unchanged(self, client: TestClient) -> None:
        health = client.get("/health")
        assert health.status_code == 200
        assert set(health.json()) == {"status", "service"}
        signup(client, email="authcheck@example.com")
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "authcheck@example.com"


class TestArchitecture:
    def test_openapi_has_all_five_dataset_operations(self, api_app: FastAPI) -> None:
        paths = api_app.openapi()["paths"]
        assert "post" in paths["/api/datasets/preview"]
        assert set(paths["/api/datasets"]) >= {"post", "get"}
        assert set(paths["/api/datasets/{dataset_id}"]) >= {"get", "delete"}
        assert "/health" in paths

    def test_metadata_unchanged_and_no_engine_imports(self) -> None:
        from pathlib import Path

        from app.db import Base

        assert {"users", "datasets", "price_bars"} <= set(Base.metadata.tables)
        management_source = (
            Path(__file__).resolve().parents[2] / "app" / "datasets" / "management.py"
        ).read_text(encoding="utf-8")
        assert "app.engine" not in management_source
        assert "app.importing" not in management_source
