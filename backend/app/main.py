"""FastAPI application factory.

Startup opens no database connection, creates no tables (Alembic owns the
schema), and never runs the backtest engine.
"""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings

__all__ = ["app", "create_app"]


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.debug)
    application.include_router(api_router)
    return application


app = create_app()
