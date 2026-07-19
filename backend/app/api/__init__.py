"""HTTP API layer; may depend on the engine later, never the reverse."""

from app.api.router import api_router

__all__ = ["api_router"]
