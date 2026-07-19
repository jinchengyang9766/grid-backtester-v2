"""Tests for the /health endpoint."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient

HEALTH_MODULE = Path(__file__).resolve().parents[2] / "app" / "api" / "routes" / "health.py"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    for name in list(os.environ):
        if name.startswith("GRID_BACKTESTER_"):
            monkeypatch.delenv(name)
    get_settings.cache_clear()
    yield TestClient(create_app())
    get_settings.cache_clear()


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Grid Backtester V2"}


def test_health_is_deterministic_across_requests(client: TestClient) -> None:
    first = client.get("/health")
    second = client.get("/health")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_health_service_name_comes_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRID_BACKTESTER_APP_NAME", "Renamed Service")
    get_settings.cache_clear()
    try:
        response = TestClient(create_app()).get("/health")
        assert response.json() == {"status": "ok", "service": "Renamed Service"}
    finally:
        get_settings.cache_clear()


def test_health_route_needs_no_database_or_engine() -> None:
    source = HEALTH_MODULE.read_text(encoding="utf-8")
    assert "app.db" not in source
    assert "sqlalchemy" not in source.lower()
    assert "app.engine" not in source
    assert "Depends" not in source


def test_docs_endpoint_is_registered(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
