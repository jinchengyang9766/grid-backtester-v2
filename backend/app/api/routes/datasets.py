"""Dataset preview and save endpoints (SPEC Section 25.2).

Preview parses/cleans the upload in memory and never touches the database
beyond the authentication dependency; save persists exactly the cached
cleaned result. The raw upload is read once and released with the request.
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.schemas.datasets import (
    DatasetPreviewResponse,
    DatasetSavedResponse,
    DatasetSaveRequest,
)
from app.auth.dependencies import get_current_user
from app.datasets.preview_cache import PreviewCache
from app.datasets.service import build_preview_entry, save_dataset
from app.db.models import Dataset, User
from app.db.session import get_db_session

__all__ = ["get_preview_cache", "router"]

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def get_preview_cache(request: Request) -> PreviewCache:
    """The per-application cache instance created in create_app()."""
    return cast(PreviewCache, request.app.state.preview_cache)


CurrentUserDep = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[Session, Depends(get_db_session)]
PreviewCacheDep = Annotated[PreviewCache, Depends(get_preview_cache)]


@router.post("/preview", response_model=DatasetPreviewResponse)
async def preview_dataset(
    current_user: CurrentUserDep,
    cache: PreviewCacheDep,
    file: UploadFile,
    manual_mapping: Annotated[str | None, Form()] = None,
    ohlc_path_hint: Annotated[str | None, Form()] = None,  # accepted, reserved, unused
) -> DatasetPreviewResponse:
    raw = await file.read()
    entry = build_preview_entry(
        raw=raw,
        filename=file.filename or "",
        manual_mapping_json=manual_mapping,
        owner_user_id=current_user.id,
    )
    token = cache.put(entry)
    return DatasetPreviewResponse.from_entry(entry, token)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DatasetSavedResponse)
def save_dataset_endpoint(
    payload: DatasetSaveRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
    cache: PreviewCacheDep,
) -> Dataset:
    return save_dataset(
        session,
        cache,
        token=payload.preview_token,
        name=payload.name,
        owner_user_id=current_user.id,
    )
