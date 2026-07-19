"""Alembic migration environment.

The database URL comes from the application Settings (never hard-coded here),
with an optional per-invocation "sqlalchemy.url" config override used by the
migration test suite to target temporary databases. Importing app.db.models
registers every persistence model on Base.metadata before target_metadata is
evaluated; Alembic owns all schema creation.
"""

from logging.config import fileConfig

import app.db.models  # noqa: F401  (registers models on Base.metadata)
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    override = config.get_main_option("sqlalchemy.url")
    if override:
        return override
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: emit SQL without a DBAPI connection."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode: connect and execute directly."""
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
