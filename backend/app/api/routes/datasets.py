"""Dataset preview and save endpoints (SPEC Section 25.2).

Preview parses/cleans the upload in memory and never touches the database
beyond the authentication dependency; save persists exactly the cached
cleaned result. The raw upload is read once and released with the request.
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas.datasets import (
    DatasetDetailResponse,
    DatasetListResponse,
    DatasetPreviewResponse,
    DatasetSavedResponse,
    DatasetSaveRequest,
    DatasetSummaryModel,
)
from app.auth.dependencies import get_current_user
from app.datasets.management import (
    DatasetInUseError,
    delete_owned_dataset,
    get_owned_dataset,
    list_owned_datasets,
)
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


def _dataset_not_found() -> ApiError:
    # One indistinguishable response for missing and wrong-owner datasets:
    # existence is never revealed to non-owners (SPEC 24.4).
    return ApiError(status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", "Dataset not found.")


@router.get("", response_model=DatasetListResponse)
def list_datasets(session: SessionDep, current_user: CurrentUserDep) -> DatasetListResponse:
    datasets = list_owned_datasets(session, owner_user_id=current_user.id)
    return DatasetListResponse(
        items=[DatasetSummaryModel.model_validate(dataset) for dataset in datasets]
    )


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset_id: int, session: SessionDep, current_user: CurrentUserDep) -> Dataset:
    dataset = get_owned_dataset(session, dataset_id=dataset_id, owner_user_id=current_user.id)
    if dataset is None:
        raise _dataset_not_found()
    return dataset


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: int, session: SessionDep, current_user: CurrentUserDep) -> None:
    try:
        deleted = delete_owned_dataset(
            session, dataset_id=dataset_id, owner_user_id=current_user.id
        )
    except DatasetInUseError as error:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "DATASET_IN_USE",
            "Dataset is referenced by existing resources and cannot be deleted.",
        ) from error
    if not deleted:
        raise _dataset_not_found()
