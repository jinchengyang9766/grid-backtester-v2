"""Tests for the standard JSON API error envelope (SPEC Section 26)."""

from fastapi.testclient import TestClient


def test_validation_error_uses_exact_envelope_structure(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "long-enough"}
    )
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"]["errors"], list)


def test_details_omitted_when_absent(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert "details" not in body["error"]


def test_invalid_email_produces_422_envelope_with_location(client: TestClient) -> None:
    response = client.post("/api/auth/register", json={"email": "nope", "password": "long-enough"})
    assert response.status_code == 422
    locations = [issue["loc"] for issue in response.json()["error"]["details"]["errors"]]
    assert ["body", "email"] in locations


def test_short_registration_password_produces_422_envelope(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register", json={"email": "a@example.com", "password": "short"}
    )
    assert response.status_code == 422
    locations = [issue["loc"] for issue in response.json()["error"]["details"]["errors"]]
    assert ["body", "password"] in locations


def test_validation_response_never_echoes_submitted_password(client: TestClient) -> None:
    submitted_password = "hunter7"  # short enough to fail validation
    response = client.post(
        "/api/auth/register", json={"email": "a@example.com", "password": submitted_password}
    )
    assert response.status_code == 422
    assert submitted_password not in response.text


def test_health_endpoint_remains_unchanged(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "service"}
