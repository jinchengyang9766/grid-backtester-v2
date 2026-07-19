"""Typed application settings loaded from the environment (SPEC Section 37).

All configuration flows through Settings; nothing else in the application
reads environment variables directly.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
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

    # HS256 JWT signing secret. The default is a clearly-labeled,
    # NON-PRODUCTION development value so imports and tests are
    # self-contained; production deployments MUST override it via
    # GRID_BACKTESTER_AUTH_SECRET_KEY. SecretStr keeps it out of repr/logs.
    auth_secret_key: SecretStr = SecretStr("dev-only-insecure-secret-do-not-use-in-production")
    access_token_expire_minutes: int = Field(default=1440, ge=1)
    access_token_cookie_name: str = "access_token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
