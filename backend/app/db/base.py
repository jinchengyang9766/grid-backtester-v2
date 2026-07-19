"""SQLAlchemy 2.x declarative base; future persistence models inherit from it.

No application tables are defined yet — Alembic owns schema creation, and no
engine or session objects live in this module.
"""

from sqlalchemy.orm import DeclarativeBase

__all__ = ["Base"]


class Base(DeclarativeBase):
    """Declarative base for all future application persistence models."""
