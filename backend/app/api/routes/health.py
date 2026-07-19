"""Liveness endpoint: deterministic, no database, no business schemas."""

from fastapi import APIRouter

from app.core.config import get_settings

__all__ = ["router"]

router = APIRouter()


@router.get("/health")
def read_health() -> dict[str, str]:
    return {"status": "ok", "service": get_settings().app_name}
