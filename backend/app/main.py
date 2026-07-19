"""FastAPI application factory.

Startup opens no database connection, creates no tables (Alembic owns the
schema), and never runs the backtest engine.
"""

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.router import api_router
from app.core.config import get_settings
from app.datasets.preview_cache import PreviewCache

__all__ = ["app", "create_app"]


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.debug)
    # One in-process preview cache per application instance (SPEC 25.2's
    # 30-minute preview tokens); tests build isolated apps with own caches.
    application.state.preview_cache = PreviewCache()
    register_error_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()
