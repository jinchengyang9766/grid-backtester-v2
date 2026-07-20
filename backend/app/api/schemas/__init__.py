"""Pydantic API schemas, grouped by resource."""

from app.api.schemas.auth import (
    AuthenticatedUserResponse,
    LoginRequest,
    RegisteredUserResponse,
    RegisterRequest,
)
from app.api.schemas.backtests import (
    BacktestCompareRequest,
    BacktestCompareResponse,
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestDuplicateRequest,
    BacktestListItem,
    BacktestListResponse,
)
from app.api.schemas.datasets import (
    DatasetPreviewResponse,
    DatasetSavedResponse,
    DatasetSaveRequest,
)

__all__ = [
    "AuthenticatedUserResponse",
    "BacktestCompareRequest",
    "BacktestCompareResponse",
    "BacktestCreateRequest",
    "BacktestCreateResponse",
    "BacktestDetailResponse",
    "BacktestDuplicateRequest",
    "BacktestListItem",
    "BacktestListResponse",
    "DatasetPreviewResponse",
    "DatasetSaveRequest",
    "DatasetSavedResponse",
    "LoginRequest",
    "RegisterRequest",
    "RegisteredUserResponse",
]
