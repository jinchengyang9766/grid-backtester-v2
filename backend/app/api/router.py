"""Top-level API router aggregating all route modules."""

from fastapi import APIRouter

from app.api.routes.health import router as health_router

__all__ = ["api_router"]

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
