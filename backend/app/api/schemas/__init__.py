"""Pydantic API schemas, grouped by resource."""

from app.api.schemas.auth import (
    AuthenticatedUserResponse,
    LoginRequest,
    RegisteredUserResponse,
    RegisterRequest,
)
from app.api.schemas.backtests import (
    BacktestCreateRequest,
    BacktestCreateResponse,
)
from app.api.schemas.datasets import (
    DatasetPreviewResponse,
    DatasetSavedResponse,
    DatasetSaveRequest,
)

__all__ = [
    "AuthenticatedUserResponse",
    "BacktestCreateRequest",
    "BacktestCreateResponse",
    "DatasetPreviewResponse",
    "DatasetSaveRequest",
    "DatasetSavedResponse",
    "LoginRequest",
    "RegisterRequest",
    "RegisteredUserResponse",
]
