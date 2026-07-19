"""Tests for POST /api/datasets (save) and the full preview-save flow."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from app.datasets.service import build_preview_entry
from app.db.models import Dataset, PriceBar, User
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

TDX_TEXT = (
    "农业ETF基金 (159825)\t\t\t\t\t\n"
    "时间\t开盘\t最高\t最低\t收盘\t成交量\n"
    "2024/07/23\t1.00\t1.10\t0.90\t1.05\t1000\n"
    "2024/07/24\t1.05\t1.15\t1.00\t1.10\t\n"
    "数据来源：通达信\n"
)


def signup(client: TestClient, email: str = "user@example.com") -> None:
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    login(client, email)


def login(client: TestClient, email: str = "user@example.com") -> None:
    client.post("/api/auth/login", json={"email": email, "password": "password123"})


def preview_token(
    client: TestClient, filename: str = "159825.xls", content: bytes | None = None
) -> str:
    raw = content if content is not None else TDX_TEXT.encode("gb18030")
    response = client.post(
        "/api/datasets/preview",
        files={"file": (filename, raw, "application/octet-stream")},
    )
    assert response.status_code == 200
    token: str = response.json()["preview_token"]
    return token


def save(client: TestClient, token: str, name: str = "My Dataset") -> httpx.Response:
    response: httpx.Response = client.post(
        "/api/datasets", json={"name": name, "preview_token": token}
    )
    return response


def user_id_of(session_factory: sessionmaker[Session], email: str = "user@example.com") -> int:
    with session_factory() as session:
        return session.execute(sa.select(User.id).where(User.email == email)).scalar_one()


class TestSave:
    def test_unauthenticated_save_401(self, client: TestClient) -> None:
        response = save(client, "any-token")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_valid_token_creates_dataset_with_exact_response(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        token = preview_token(client)
        response = save(client, token, name="  159825 Dataset  ")
        assert response.status_code == 201
        body = response.json()
        assert set(body) == {
            "id",
            "name",
            "data_mode",
            "start_date",
            "end_date",
            "row_count",
            "created_at",
        }
        assert body["name"] == "159825 Dataset"
        assert body["data_mode"] == "OHLCV"
        assert body["start_date"] == "2024-07-23"
        assert body["end_date"] == "2024-07-24"
        assert body["row_count"] == 2
        assert "price_bars" not in body

    def test_stored_dataset_fields(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        token = preview_token(client, filename=r"C:\fakepath\159825.xls")
        save(client, token)
        with session_factory() as session:
            dataset = session.execute(sa.select(Dataset)).scalar_one()
            assert dataset.user_id == user_id_of(session_factory)
            assert dataset.source_type == "TDX_XLS"
            assert dataset.original_filename == "159825.xls"
            assert dataset.security_name == "农业ETF基金"
            assert dataset.security_code == "159825"
            assert dataset.data_mode == "OHLCV"
            assert dataset.column_mapping == {
                "date": "时间",
                "open": "开盘",
                "high": "最高",
                "low": "最低",
                "close": "收盘",
                "volume": "成交量",
            }
            assert dataset.cleaning_summary["final_row_count"] == 2
            assert dataset.cleaning_summary["bad_row_reasons"]["UNPARSEABLE_DATE"] == 0

    def test_price_bars_persisted_with_decimals_and_nulls(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        save(client, preview_token(client))
        with session_factory() as session:
            bars = session.execute(sa.select(PriceBar).order_by(PriceBar.date)).scalars().all()
            assert len(bars) == 2
            assert isinstance(bars[0].close, Decimal)
            assert bars[0].close == Decimal("1.05")
            assert bars[0].volume == Decimal("1000")
            assert bars[1].volume is None  # blank volume stays null

    @pytest.mark.parametrize("extra_field", [("column_mapping", {}), ("user_id", 99), ("bars", [])])
    def test_extra_request_fields_rejected(
        self, client: TestClient, extra_field: tuple[str, object]
    ) -> None:
        signup(client)
        token = preview_token(client)
        key, value = extra_field
        response = client.post(
            "/api/datasets", json={"name": "X", "preview_token": token, key: value}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.parametrize("bad_name", ["", "   ", "\t\n"])
    def test_blank_name_rejected(self, client: TestClient, bad_name: str) -> None:
        signup(client)
        token = preview_token(client)
        response = save(client, token, name=bad_name)
        assert response.status_code == 422


class TestTokenFailures:
    def test_all_token_failures_are_identical_404(
        self, client: TestClient, api_app: FastAPI, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        owner_id = user_id_of(session_factory)

        # Unknown token.
        unknown = save(client, "completely-unknown-token")

        # Expired token: a service-built entry created 31 minutes ago.
        stale_entry = build_preview_entry(
            raw=TDX_TEXT.encode("gb18030"),
            filename="stale.xls",
            manual_mapping_json=None,
            owner_user_id=owner_id,
            now=datetime.now(UTC) - timedelta(minutes=31),
        )
        expired = save(client, api_app.state.preview_cache.put(stale_entry))

        # Consumed token.
        consumed_token = preview_token(client)
        assert save(client, consumed_token).status_code == 201
        consumed = save(client, consumed_token)

        # Wrong-owner token.
        foreign_token = preview_token(client)
        signup(client, email="other@example.com")
        wrong_owner = save(client, foreign_token)

        for response in (unknown, expired, consumed, wrong_owner):
            assert response.status_code == 404
            assert response.json() == {
                "error": {
                    "code": "PREVIEW_TOKEN_NOT_FOUND",
                    "message": "Preview token not found or expired.",
                }
            }

    def test_wrong_owner_does_not_consume_token(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client, email="alice@example.com")
        token = preview_token(client)
        signup(client, email="bob@example.com")
        assert save(client, token).status_code == 404
        login(client, email="alice@example.com")
        assert save(client, token).status_code == 201
        with session_factory() as session:
            dataset = session.execute(sa.select(Dataset)).scalar_one()
            owner_id = session.execute(
                sa.select(User.id).where(User.email == "alice@example.com")
            ).scalar_one()
            assert dataset.user_id == owner_id


class TestTransaction:
    def test_database_failure_rolls_back_restores_token_and_retry_succeeds(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        signup(client)
        token = preview_token(client)

        def failing_commit(self: Session) -> None:
            raise RuntimeError("database temporarily unavailable")

        monkeypatch.setattr(Session, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            save(client, token)
        monkeypatch.undo()

        with session_factory() as session:
            assert (
                session.execute(sa.select(sa.func.count()).select_from(Dataset)).scalar_one() == 0
            )
            assert (
                session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one() == 0
            )
        retry = save(client, token)
        assert retry.status_code == 201
        with session_factory() as session:
            assert (
                session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one() == 2
            )

    def test_user_row_not_modified_by_save(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        with session_factory() as session:
            before = session.execute(sa.select(User.updated_at)).scalar_one()
        save(client, preview_token(client))
        with session_factory() as session:
            assert session.execute(sa.select(User.updated_at)).scalar_one() == before


class TestFullFlow:
    def test_register_login_preview_save_retry(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        db_engine: sa.engine.Engine,
        tmp_path: Path,
    ) -> None:
        before_files = set(tmp_path.rglob("*"))
        signup(client, email="flow@example.com")
        response = client.post(
            "/api/datasets/preview",
            files={"file": ("159825.xls", TDX_TEXT.encode("gb18030"), "application/octet-stream")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["column_mapping_used"]["close"] == "收盘"
        assert body["cleaning_summary"]["final_row_count"] == 2
        token = body["preview_token"]
        assert token

        saved = save(client, token, name="Flow Dataset")
        assert saved.status_code == 201
        with session_factory() as session:
            dataset = session.execute(sa.select(Dataset)).scalar_one()
            bar_count = session.execute(
                sa.select(sa.func.count()).select_from(PriceBar)
            ).scalar_one()
        assert dataset.name == "Flow Dataset"
        assert bar_count == 2

        assert save(client, token).status_code == 404
        assert set(tmp_path.rglob("*")) == before_files  # no uploaded file on disk
        from app.db import Base

        assert set(sa.inspect(db_engine).get_table_names()) == set(Base.metadata.tables)
