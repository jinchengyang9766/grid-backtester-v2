"""Pydantic API schemas, grouped by resource."""

from app.api.schemas.auth import (
    AuthenticatedUserResponse,
    LoginRequest,
    RegisteredUserResponse,
    RegisterRequest,
)

__all__ = [
    "AuthenticatedUserResponse",
    "LoginRequest",
    "RegisterRequest",
    "RegisteredUserResponse",
]
