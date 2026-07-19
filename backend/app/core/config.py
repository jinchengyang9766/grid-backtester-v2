"""Typed application settings loaded from the environment (SPEC Section 37).

All configuration flows through Settings; nothing else in the application
reads environment variables directly.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GRID_BACKTESTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "Grid Backtester V2"
    app_environment: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./grid_backtester_dev.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
