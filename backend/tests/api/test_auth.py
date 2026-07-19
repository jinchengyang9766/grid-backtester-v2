"""Tests for the authentication endpoints, cookie handling, and settings."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import app.api.routes.auth as auth_routes
import httpx
import pytest
import sqlalchemy as sa
from app.auth.tokens import create_access_token, decode_access_token
from app.core.config import Settings, get_settings
from app.db import Base
from app.db.models import User
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND_DIR / "app"

EMAIL = "user@example.com"
PASSWORD = "password123"


def register(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> httpx.Response:
    response: httpx.Response = client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    return response


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> httpx.Response:
    response: httpx.Response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    return response


def stored_user(session_factory: sessionmaker[Session]) -> User:
    with session_factory() as session:
        return session.execute(sa.select(User)).scalar_one()


def token_secret() -> str:
    return get_settings().auth_secret_key.get_secret_value()


class TestSettings:
    @pytest.fixture()
    def clean_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
        for name in list(os.environ):
            if name.startswith("GRID_BACKTESTER_"):
                monkeypatch.delenv(name)
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_new_defaults(self, clean_env: None) -> None:
        settings = Settings()
        assert isinstance(settings.auth_secret_key, SecretStr)
        assert "dev-only" in settings.auth_secret_key.get_secret_value()
        assert settings.access_token_expire_minutes == 1440
        assert settings.access_token_cookie_name == "access_token"

    def test_prefixed_environment_overrides(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GRID_BACKTESTER_AUTH_SECRET_KEY", "overridden-secret")
        monkeypatch.setenv("GRID_BACKTESTER_ACCESS_TOKEN_EXPIRE_MINUTES", "5")
        monkeypatch.setenv("GRID_BACKTESTER_ACCESS_TOKEN_COOKIE_NAME", "custom_cookie")
        settings = Settings()
        assert settings.auth_secret_key.get_secret_value() == "overridden-secret"
        assert settings.access_token_expire_minutes == 5
        assert settings.access_token_cookie_name == "custom_cookie"

    @pytest.mark.parametrize("minutes", [0, -1])
    def test_expiry_must_be_positive(self, clean_env: None, minutes: int) -> None:
        with pytest.raises(ValidationError):
            Settings(access_token_expire_minutes=minutes)

    def test_settings_remain_frozen(self, clean_env: None) -> None:
        settings = Settings()
        with pytest.raises(ValidationError):
            settings.access_token_expire_minutes = 5

    def test_secret_is_not_exposed_in_repr(self, clean_env: None) -> None:
        settings = Settings()
        secret_value = settings.auth_secret_key.get_secret_value()
        assert secret_value not in repr(settings)
        assert secret_value not in str(settings)
        assert secret_value not in repr(settings.auth_secret_key)

    def test_env_example_contains_only_obvious_placeholder(self) -> None:
        content = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
        assert "GRID_BACKTESTER_AUTH_SECRET_KEY=dev-only-placeholder-not-a-real-secret" in content
        assert "GRID_BACKTESTER_ACCESS_TOKEN_EXPIRE_MINUTES=1440" in content
        assert "GRID_BACKTESTER_ACCESS_TOKEN_COOKIE_NAME=access_token" in content


class TestRegistration:
    def test_returns_201_with_exact_fields(self, client: TestClient) -> None:
        response = register(client)
        assert response.status_code == 201
        body = response.json()
        assert set(body) == {"id", "email", "created_at"}
        assert body["email"] == EMAIL
        assert isinstance(body["id"], int)
        created_at = datetime.fromisoformat(body["created_at"])
        assert created_at.tzinfo is not None

    def test_mixed_case_email_stored_canonically_lowercase(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        response = register(client, email="User@Example.com")
        assert response.status_code == 201
        assert response.json()["email"] == "user@example.com"
        assert stored_user(session_factory).email == "user@example.com"

    def test_password_stored_as_argon2id_hash_without_plaintext(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        register(client)
        user = stored_user(session_factory)
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash

    def test_response_excludes_password_hash(self, client: TestClient) -> None:
        response = register(client)
        assert "password" not in response.text
        assert "argon2" not in response.text

    def test_no_cookie_set_on_registration(self, client: TestClient) -> None:
        response = register(client)
        assert "set-cookie" not in response.headers

    def test_exact_duplicate_email_conflicts(self, client: TestClient) -> None:
        register(client)
        response = register(client)
        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
        assert set(body) == {"error"}

    def test_different_case_duplicate_email_conflicts(self, client: TestClient) -> None:
        register(client, email="user@example.com")
        response = register(client, email="USER@EXAMPLE.COM")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    def test_integrity_error_race_maps_to_409(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        register(client)
        # Simulate the race: the pre-check misses the existing row, so the
        # INSERT itself hits the uniqueness constraint.
        monkeypatch.setattr(auth_routes, "_find_user_by_email", lambda session, email: None)
        response = register(client)
        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
        assert "uq_users_email" not in response.text
        assert "UNIQUE" not in response.text

    def test_unrelated_integrity_errors_are_not_mislabeled(self) -> None:
        unrelated = IntegrityError(
            "INSERT INTO users ...",
            {},
            Exception("NOT NULL constraint failed: users.password_hash"),
        )
        duplicate = IntegrityError(
            "INSERT INTO users ...",
            {},
            Exception("UNIQUE constraint failed: index 'ux_users_email_lower'"),
        )
        assert auth_routes._is_duplicate_email_violation(unrelated) is False
        assert auth_routes._is_duplicate_email_violation(duplicate) is True


class TestLogin:
    def test_correct_credentials_return_200_with_exact_fields(self, client: TestClient) -> None:
        register(client)
        response = login(client)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"id", "email"}
        assert body["email"] == EMAIL

    def test_response_body_excludes_token_and_hash(self, client: TestClient) -> None:
        register(client)
        response = login(client)
        token = client.cookies.get("access_token")
        assert token is not None
        assert token not in response.text
        assert "argon2" not in response.text

    def test_cookie_contains_decodable_jwt_for_user(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        register(client)
        login(client)
        token = client.cookies.get("access_token")
        assert token is not None
        assert (
            decode_access_token(token, secret_key=token_secret()) == stored_user(session_factory).id
        )

    def test_development_cookie_attributes(self, client: TestClient) -> None:
        register(client)
        header = login(client).headers["set-cookie"].lower()
        assert "httponly" in header
        assert "samesite=lax" in header
        assert "path=/api" in header
        assert f"max-age={get_settings().access_token_expire_minutes * 60}" in header
        assert "domain=" not in header
        assert "secure" not in header

    def test_production_cookie_is_secure(self, production_client: TestClient) -> None:
        register(production_client)
        header = login(production_client).headers["set-cookie"].lower()
        assert "secure" in header
        assert "httponly" in header
        assert "samesite=lax" in header

    def test_only_one_cookie_and_no_refresh_cookie(self, client: TestClient) -> None:
        register(client)
        response = login(client)
        set_cookie_headers = response.headers.get_list("set-cookie")
        assert len(set_cookie_headers) == 1
        assert "refresh" not in set_cookie_headers[0].lower()

    def test_email_lookup_is_case_insensitive(self, client: TestClient) -> None:
        register(client, email="user@example.com")
        assert login(client, email="USER@Example.COM").status_code == 200

    def test_wrong_password_and_unknown_email_are_indistinguishable(
        self, client: TestClient
    ) -> None:
        register(client)
        wrong_password = login(client, password="not-the-password")
        unknown_email = login(client, email="nobody@example.com", password=PASSWORD)
        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()
        assert wrong_password.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_short_password_gets_invalid_credentials_not_validation_error(
        self, client: TestClient
    ) -> None:
        register(client)
        response = login(client, password="tiny")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_malformed_stored_hash_yields_401_not_500(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            session.add(User(email=EMAIL, password_hash="corrupt-not-a-hash"))
            session.commit()
        response = login(client)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_login_does_not_alter_updated_at(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        register(client)
        before = stored_user(session_factory).updated_at
        assert login(client).status_code == 200
        assert stored_user(session_factory).updated_at == before


class TestCurrentUser:
    def test_valid_cookie_returns_current_user(self, client: TestClient) -> None:
        register(client)
        login(client)
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"id", "email"}
        assert body["email"] == EMAIL
        assert "argon2" not in response.text

    def test_missing_cookie_unauthenticated(self, client: TestClient) -> None:
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_invalid_token_unauthenticated(self, client: TestClient) -> None:
        client.cookies.set("access_token", "not-a-jwt")
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_expired_token_unauthenticated(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        register(client)
        user_id = stored_user(session_factory).id
        expired = create_access_token(
            user_id,
            secret_key=token_secret(),
            expire_minutes=5,
            now=datetime.now(UTC) - timedelta(hours=2),
        )
        client.cookies.set("access_token", expired)
        assert client.get("/api/auth/me").status_code == 401

    def test_token_signed_with_other_secret_unauthenticated(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        register(client)
        user_id = stored_user(session_factory).id
        forged = create_access_token(
            user_id,
            secret_key="another-signing-secret-comfortably-over-32-bytes",
            expire_minutes=60,
        )
        client.cookies.set("access_token", forged)
        assert client.get("/api/auth/me").status_code == 401

    def test_token_for_deleted_user_unauthenticated(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        register(client)
        login(client)
        with session_factory() as session:
            session.execute(sa.delete(User))
            session.commit()
        assert client.get("/api/auth/me").status_code == 401

    def test_authorization_bearer_without_cookie_is_not_accepted(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        register(client)
        user_id = stored_user(session_factory).id
        token = create_access_token(user_id, secret_key=token_secret(), expire_minutes=60)
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_me_does_not_alter_the_user(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        register(client)
        login(client)
        before = stored_user(session_factory).updated_at
        assert client.get("/api/auth/me").status_code == 200
        assert stored_user(session_factory).updated_at == before


class TestLogout:
    def test_returns_exact_204_with_empty_body(self, client: TestClient) -> None:
        register(client)
        login(client)
        response = client.post("/api/auth/logout")
        assert response.status_code == 204
        assert response.content == b""

    def test_clears_configured_cookie_at_api_path(self, client: TestClient) -> None:
        register(client)
        login(client)
        header = client.post("/api/auth/logout").headers["set-cookie"].lower()
        assert "access_token=" in header
        assert "path=/api" in header
        assert "max-age=0" in header or "expires=" in header

    def test_works_without_a_cookie(self, client: TestClient) -> None:
        assert client.post("/api/auth/logout").status_code == 204

    def test_works_with_an_invalid_cookie(self, client: TestClient) -> None:
        client.cookies.set("access_token", "garbage")
        assert client.post("/api/auth/logout").status_code == 204

    def test_repeated_logout_remains_204(self, client: TestClient) -> None:
        for _ in range(3):
            assert client.post("/api/auth/logout").status_code == 204

    def test_does_not_access_the_database(self, session_factory: sessionmaker[Session]) -> None:
        from app.db.session import get_db_session
        from app.main import create_app

        application = create_app()

        def forbidden_session() -> Iterator[Session]:
            raise AssertionError("logout must not open a database session")
            yield  # pragma: no cover

        application.dependency_overrides[get_db_session] = forbidden_session
        with TestClient(application) as isolated_client:
            assert isolated_client.post("/api/auth/logout").status_code == 204


class TestFullFlow:
    def test_register_login_me_logout_me(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        assert register(client, email="Flow@Example.com").status_code == 201
        assert login(client, email="flow@example.com").status_code == 200
        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        assert me_response.json()["email"] == "flow@example.com"
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        # No plaintext password anywhere in the database.
        with session_factory() as session:
            hashes = session.execute(sa.select(User.password_hash)).scalars().all()
        assert all(PASSWORD not in stored for stored in hashes)


class TestDatabaseSafety:
    def test_auth_creates_no_additional_tables(self, client: TestClient, db_engine: Engine) -> None:
        register(client)
        login(client)
        client.get("/api/auth/me")
        client.post("/api/auth/logout")
        assert set(sa.inspect(db_engine).get_table_names()) == {
            "users",
            "datasets",
            "price_bars",
        }

    def test_metadata_still_contains_exactly_three_tables(self) -> None:
        assert set(Base.metadata.tables) == {"users", "datasets", "price_bars"}

    def test_no_default_dev_database_created_by_auth_imports(self, tmp_path: Path) -> None:
        # Engine creation stays lazy: no file appears without a connection.
        from app.db.session import create_database_engine

        database_file = tmp_path / "lazy_auth.db"
        create_database_engine(f"sqlite:///{database_file}")
        assert not database_file.exists()


class TestArchitectureBoundaries:
    AUTH_FILES = sorted((APP_DIR / "auth").glob("*.py"))
    API_FILES = sorted((APP_DIR / "api").rglob("*.py"))

    def test_auth_and_api_do_not_import_the_engine(self) -> None:
        # The API layer may call the pure importing pipeline (datasets
        # preview), but nothing in auth/api touches the backtest engine,
        # and auth never touches the importing pipeline either.
        for path in [*self.AUTH_FILES, *self.API_FILES]:
            assert "app.engine" not in path.read_text(encoding="utf-8"), path
        for path in self.AUTH_FILES:
            assert "app.importing" not in path.read_text(encoding="utf-8"), path

    def test_pure_packages_do_not_import_auth_jwt_or_db(self) -> None:
        for package in ("engine", "importing"):
            for path in (APP_DIR / package).rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                for forbidden in ("app.auth", "import jwt", "import argon2", "app.db"):
                    assert forbidden not in source, f"{path} contains {forbidden!r}"

    def test_orm_user_model_stays_framework_free(self) -> None:
        source = (APP_DIR / "db" / "models" / "user.py").read_text(encoding="utf-8")
        for forbidden in ("argon2", "jwt", "fastapi", "pydantic"):
            assert forbidden not in source

    def test_no_out_of_scope_auth_features_exist(self) -> None:
        for name in ("refresh.py", "reset.py", "oauth.py", "roles.py", "csrf.py"):
            assert not (APP_DIR / "auth" / name).exists()
        combined = "".join(path.read_text(encoding="utf-8") for path in self.AUTH_FILES)
        assert "refresh_token" not in combined
        assert "csrf" not in combined.lower()
