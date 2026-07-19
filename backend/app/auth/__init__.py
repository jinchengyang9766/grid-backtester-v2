"""Authentication: Argon2id hashing, HS256 JWTs, and the current-user dependency."""

from app.auth.dependencies import get_current_user
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import AuthTokenError, create_access_token, decode_access_token

__all__ = [
    "AuthTokenError",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "hash_password",
    "verify_password",
]
