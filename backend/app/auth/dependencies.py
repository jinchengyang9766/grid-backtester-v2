"""Authentication dependencies for API routes (SPEC Sections 24.1, 25.1).

The access token is read exclusively from the configured HttpOnly cookie —
Authorization: Bearer headers are not supported in V2. Every failure mode
(missing cookie, invalid/expired/wrongly-signed token, deleted user) maps
to the same indistinguishable 401 UNAUTHENTICATED response.
"""

from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.tokens import AuthTokenError, decode_access_token
from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_db_session

__all__ = ["get_current_user"]


def _unauthenticated() -> ApiError:
    return ApiError(
        status.HTTP_401_UNAUTHORIZED,
        "UNAUTHENTICATED",
        "Authentication required.",
    )


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> User:
    """Resolve the authenticated User from the access-token cookie.

    Read-only: never commits, flushes, or mutates the database.
    """
    settings = get_settings()
    token = request.cookies.get(settings.access_token_cookie_name)
    if token is None:
        raise _unauthenticated()
    try:
        user_id = decode_access_token(token, secret_key=settings.auth_secret_key.get_secret_value())
    except AuthTokenError as error:
        raise _unauthenticated() from error
    user = session.get(User, user_id)
    if user is None:
        raise _unauthenticated()
    return user
