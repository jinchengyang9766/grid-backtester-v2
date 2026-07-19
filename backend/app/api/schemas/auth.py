"""Authentication request/response schemas (SPEC Section 25.1).

password_hash and access tokens never appear in any response model; the
token travels exclusively in the HttpOnly cookie.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

__all__ = [
    "AuthenticatedUserResponse",
    "LoginRequest",
    "RegisterRequest",
    "RegisteredUserResponse",
]


class RegisterRequest(BaseModel):
    email: EmailStr
    # The frozen minimum-eight-character rule only — no complexity rules (ED-17).
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    # No minimum length: a too-short password is simply a wrong password and
    # must produce INVALID_CREDENTIALS, not a distinct validation response.
    password: str


class RegisteredUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _ensure_timezone_aware(cls, value: datetime) -> datetime:
        # PostgreSQL TIMESTAMPTZ yields aware datetimes; SQLite's
        # CURRENT_TIMESTAMP yields naive UTC ones. Normalize to aware UTC.
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AuthenticatedUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
