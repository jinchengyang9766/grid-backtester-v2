"""HS256 access-token creation and validation (SPEC Sections 24.1 and 24.3).

The payload carries exactly the identity/time claims sub, iat, and exp —
no email, password hash, or other PII. All invalid-token cases raise the
single AuthTokenError, which the API layer maps to 401 UNAUTHENTICATED
without exposing PyJWT exception details.
"""

from datetime import UTC, datetime, timedelta

import jwt

__all__ = ["AuthTokenError", "create_access_token", "decode_access_token"]

_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["sub", "iat", "exp"]


class AuthTokenError(Exception):
    """Any invalid access token: expired, malformed, wrong signature/claims."""


def create_access_token(
    user_id: int,
    *,
    secret_key: str,
    expire_minutes: int,
    now: datetime | None = None,
) -> str:
    """Create a signed HS256 token whose sub is the user ID as a string.

    ``now`` exists only for deterministic tests; production callers omit it.
    """
    issued_at = now if now is not None else datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM)


def decode_access_token(
    token: str,
    *,
    secret_key: str,
    now: datetime | None = None,
) -> int:
    """Validate the token and return the integer user ID from ``sub``.

    Rejects expired tokens, invalid signatures, malformed tokens, missing
    sub/iat/exp claims, non-integer sub values, unexpected algorithms, and
    unsigned tokens. When ``now`` is given, expiry is checked against it
    deterministically instead of the system clock.
    """
    try:
        if now is None:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[_ALGORITHM],
                options={"require": _REQUIRED_CLAIMS},
            )
        else:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[_ALGORITHM],
                options={
                    "require": _REQUIRED_CLAIMS,
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
            if now >= expires_at:
                raise AuthTokenError("Access token has expired")
    except jwt.InvalidTokenError as error:
        raise AuthTokenError("Invalid access token") from error
    except (TypeError, ValueError) as error:  # non-numeric exp in the now-path
        raise AuthTokenError("Invalid access token") from error

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise AuthTokenError("Invalid subject claim")
    return int(subject)
