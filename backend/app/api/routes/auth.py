"""Authentication endpoints (SPEC Section 25.1).

The access token travels only in the HttpOnly cookie; it never appears in a
JSON response body. Cookie attributes follow the same-origin proxy
architecture (SPEC Section 24.5): SameSite=Lax, Path=/api, no Domain, and
Secure only in production.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas.auth import (
    AuthenticatedUserResponse,
    LoginRequest,
    RegisteredUserResponse,
    RegisterRequest,
)
from app.auth.dependencies import get_current_user
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import create_access_token
from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db_session

__all__ = ["router"]

router = APIRouter(prefix="/api/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_db_session)]

# Duplicate-email uniqueness violations from either the exact constraint or
# the functional lower(email) index, on PostgreSQL or SQLite.
_DUPLICATE_EMAIL_MARKERS = ("uq_users_email", "ux_users_email_lower", "users.email")


def _canonical_email(email: str) -> str:
    return email.strip().lower()


def _find_user_by_email(session: Session, canonical_email: str) -> User | None:
    statement = select(User).where(func.lower(User.email) == canonical_email)
    return session.execute(statement).scalar_one_or_none()


def _email_conflict() -> ApiError:
    return ApiError(
        status.HTTP_409_CONFLICT,
        "EMAIL_ALREADY_REGISTERED",
        "This email is already registered.",
    )


def _invalid_credentials() -> ApiError:
    # Identical response whether the email is unknown or the password is
    # wrong — never reveal which credential failed.
    return ApiError(
        status.HTTP_401_UNAUTHORIZED,
        "INVALID_CREDENTIALS",
        "Incorrect email or password.",
    )


def _is_duplicate_email_violation(error: IntegrityError) -> bool:
    message = str(error.orig)
    return any(marker in message for marker in _DUPLICATE_EMAIL_MARKERS)


def _set_access_token_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/api",
        httponly=True,
        secure=settings.app_environment == "production",
        samesite="lax",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisteredUserResponse,
)
def register(payload: RegisterRequest, session: SessionDep) -> User:
    email = _canonical_email(payload.email)
    if _find_user_by_email(session, email) is not None:
        raise _email_conflict()
    user = User(email=email, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        # Concurrent registration race: the pre-check passed but the insert
        # hit the uniqueness constraint. Unrelated integrity failures are
        # re-raised, never mislabeled as a duplicate email.
        session.rollback()
        if _is_duplicate_email_violation(error):
            raise _email_conflict() from error
        raise
    session.refresh(user)
    return user


@router.post("/login", response_model=AuthenticatedUserResponse)
def login(payload: LoginRequest, session: SessionDep, response: Response) -> User:
    settings = get_settings()
    email = _canonical_email(payload.email)
    user = _find_user_by_email(session, email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise _invalid_credentials()
    token = create_access_token(
        user.id,
        secret_key=settings.auth_secret_key.get_secret_value(),
        expire_minutes=settings.access_token_expire_minutes,
    )
    _set_access_token_cookie(response, settings, token)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    # Idempotent and database-free: clearing the cookie needs no token
    # validation and no current user. Attributes match the login cookie so
    # the browser removes the original.
    settings = get_settings()
    response.delete_cookie(
        key=settings.access_token_cookie_name,
        path="/api",
        httponly=True,
        secure=settings.app_environment == "production",
        samesite="lax",
    )


@router.get("/me", response_model=AuthenticatedUserResponse)
def read_current_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
