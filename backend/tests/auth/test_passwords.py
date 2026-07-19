"""Tests for Argon2id password hashing."""

import pytest
from app.auth.passwords import hash_password, verify_password

PASSWORD = "correct horse battery staple"


def test_hash_is_argon2id_encoded() -> None:
    assert hash_password(PASSWORD).startswith("$argon2id$")


def test_plaintext_is_not_present_in_hash() -> None:
    assert PASSWORD not in hash_password(PASSWORD)


def test_same_password_produces_different_salted_hashes() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_correct_password_verifies() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_wrong_password_returns_false() -> None:
    assert verify_password("wrong password", hash_password(PASSWORD)) is False


@pytest.mark.parametrize(
    "malformed_hash",
    [
        "",
        "not-a-hash",
        "$argon2id$corrupt",
        "$argon2id$v=19$m=65536,t=3,p=4$AAAA$????",
        "$2b$12$abcdefghijklmnopqrstuv",  # bcrypt-style, unsupported
    ],
)
def test_malformed_or_unsupported_hash_returns_false(malformed_hash: str) -> None:
    assert verify_password(PASSWORD, malformed_hash) is False
