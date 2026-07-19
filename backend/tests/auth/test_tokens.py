"""Tests for HS256 access-token creation and validation."""

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from app.auth.tokens import AuthTokenError, create_access_token, decode_access_token

SECRET = "unit-test-secret-that-is-comfortably-over-32-bytes-long"
NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


def make_token(user_id: int = 42, expire_minutes: int = 1440) -> str:
    return create_access_token(user_id, secret_key=SECRET, expire_minutes=expire_minutes, now=NOW)


def encode_raw(payload: dict[str, Any], secret: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_hs256_token_round_trips_to_integer_user_id() -> None:
    assert decode_access_token(make_token(42), secret_key=SECRET, now=NOW) == 42


def test_payload_contains_exactly_sub_iat_exp() -> None:
    payload = jwt.decode(make_token(7), SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert set(payload) == {"sub", "iat", "exp"}
    assert payload["sub"] == "7"
    assert payload["iat"] == int(NOW.timestamp())
    assert payload["exp"] == int((NOW + timedelta(minutes=1440)).timestamp())


def test_payload_contains_no_email_or_password_material() -> None:
    token = make_token()
    payload = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})
    for forbidden in ("email", "password", "password_hash", "argon2"):
        assert forbidden not in payload
        assert forbidden not in token


def test_configured_expiry_is_respected() -> None:
    token = make_token(expire_minutes=60)
    assert decode_access_token(token, secret_key=SECRET, now=NOW + timedelta(minutes=59)) == 42
    with pytest.raises(AuthTokenError):
        decode_access_token(token, secret_key=SECRET, now=NOW + timedelta(minutes=60))


def test_expired_token_rejected_against_real_clock() -> None:
    stale = create_access_token(
        1, secret_key=SECRET, expire_minutes=5, now=datetime.now(UTC) - timedelta(hours=1)
    )
    with pytest.raises(AuthTokenError):
        decode_access_token(stale, secret_key=SECRET)


def test_valid_token_accepted_against_real_clock() -> None:
    fresh = create_access_token(9, secret_key=SECRET, expire_minutes=5)
    assert decode_access_token(fresh, secret_key=SECRET) == 9


def test_invalid_signature_rejected() -> None:
    with pytest.raises(AuthTokenError):
        decode_access_token(
            make_token(),
            secret_key="a-different-secret-also-comfortably-over-32-bytes",
            now=NOW,
        )


@pytest.mark.parametrize("bad_token", ["", "garbage", "a.b.c", "onlyonepart"])
def test_malformed_token_rejected(bad_token: str) -> None:
    with pytest.raises(AuthTokenError):
        decode_access_token(bad_token, secret_key=SECRET, now=NOW)


@pytest.mark.parametrize("missing_claim", ["sub", "iat", "exp"])
def test_missing_required_claim_rejected(missing_claim: str) -> None:
    payload: dict[str, Any] = {
        "sub": "1",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
    }
    del payload[missing_claim]
    with pytest.raises(AuthTokenError):
        decode_access_token(encode_raw(payload), secret_key=SECRET, now=NOW)


@pytest.mark.parametrize("bad_subject", ["abc", "12.5", "-3", ""])
def test_non_integer_sub_rejected(bad_subject: str) -> None:
    payload = {
        "sub": bad_subject,
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
    }
    with pytest.raises(AuthTokenError):
        decode_access_token(encode_raw(payload), secret_key=SECRET, now=NOW)


def test_unexpected_algorithm_rejected() -> None:
    payload = {
        "sub": "1",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
    }
    with pytest.raises(AuthTokenError):
        decode_access_token(encode_raw(payload, algorithm="HS512"), secret_key=SECRET, now=NOW)


def test_unsigned_token_rejected() -> None:
    def b64(segment: dict[str, Any]) -> str:
        raw = json.dumps(segment).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    payload = {
        "sub": "1",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
    }
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(payload)}."
    with pytest.raises(AuthTokenError):
        decode_access_token(unsigned, secret_key=SECRET, now=NOW)


def test_error_does_not_expose_secret() -> None:
    with pytest.raises(AuthTokenError) as excinfo:
        decode_access_token("garbage", secret_key=SECRET, now=NOW)
    assert SECRET not in str(excinfo.value)
    assert SECRET not in repr(excinfo.value)
