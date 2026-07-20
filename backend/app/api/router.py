"""Top-level API router aggregating all route modules."""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.backtest_exports import router as backtest_exports_router
from app.api.routes.backtests import router as backtests_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.health import router as health_router

__all__ = ["api_router"]

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(datasets_router)
# Exports are registered before the general backtest routes so the deeper
# "/{backtest_id}/exports/..." paths are matched deliberately first, never
# shadowed by "/{backtest_id}" or a future catch-all sub-path.
api_router.include_router(backtest_exports_router)
api_router.include_router(backtests_router)
