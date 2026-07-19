"""Tests for settings, the application factory, the declarative base, Alembic
configuration, and the engine/infrastructure architectural boundary."""

import os
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.main import app, create_app
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy.orm import DeclarativeBase

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"


@pytest.fixture
def clean_settings_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    # Isolate from the developer's real environment: strip prefixed variables
    # and run from an empty directory so no local .env file is picked up.
    for name in list(os.environ):
        if name.startswith("GRID_BACKTESTER_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_defaults(clean_settings_env: None) -> None:
    settings = Settings()
    assert settings.app_name == "Grid Backtester V2"
    assert settings.app_environment == "development"
    assert settings.debug is False
    assert settings.database_url == "sqlite:///./grid_backtester_dev.db"


def test_settings_direct_construction(clean_settings_env: None) -> None:
    settings = Settings(
        app_name="Custom",
        app_environment="production",
        debug=True,
        database_url="sqlite:///:memory:",
    )
    assert settings.app_name == "Custom"
    assert settings.debug is True


def test_settings_env_prefix_overrides(
    clean_settings_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRID_BACKTESTER_APP_NAME", "Prefixed Name")
    monkeypatch.setenv("GRID_BACKTESTER_DEBUG", "true")
    settings = Settings()
    assert settings.app_name == "Prefixed Name"
    assert settings.debug is True


def test_unrelated_env_vars_do_not_affect_settings(
    clean_settings_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_NAME", "Wrong")
    monkeypatch.setenv("DATABASE_URL", "postgresql://wrong")
    settings = Settings()
    assert settings.app_name == "Grid Backtester V2"
    assert settings.database_url == "sqlite:///./grid_backtester_dev.db"


def test_settings_are_frozen(clean_settings_env: None) -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.app_name = "Changed"


def test_get_settings_is_cached(clean_settings_env: None) -> None:
    assert get_settings() is get_settings()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def test_create_app_returns_fastapi_and_module_app_exists() -> None:
    assert isinstance(create_app(), FastAPI)
    assert isinstance(app, FastAPI)


def test_app_title_and_debug_come_from_settings(
    clean_settings_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRID_BACKTESTER_APP_NAME", "Configured Title")
    monkeypatch.setenv("GRID_BACKTESTER_DEBUG", "true")
    get_settings.cache_clear()
    application = create_app()
    assert application.title == "Configured Title"
    assert application.debug is True


def test_router_is_included(clean_settings_env: None) -> None:
    get_settings.cache_clear()
    application = create_app()
    assert "/health" in application.openapi()["paths"]


def test_app_modules_never_run_the_backtest_engine() -> None:
    for module_path in (
        APP_DIR / "main.py",
        APP_DIR / "api" / "router.py",
        APP_DIR / "api" / "routes" / "health.py",
    ):
        source = module_path.read_text(encoding="utf-8")
        assert "app.engine" not in source, module_path
        assert "run_backtest" not in source, module_path


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


def test_base_is_declarative_and_has_no_tables() -> None:
    assert issubclass(Base, DeclarativeBase)
    assert dict(Base.metadata.tables) == {}


# ---------------------------------------------------------------------------
# Alembic
# ---------------------------------------------------------------------------


def test_alembic_ini_exists_and_holds_no_database_url() -> None:
    ini_path = BACKEND_DIR / "alembic.ini"
    assert ini_path.is_file()
    assert "sqlalchemy.url" not in ini_path.read_text(encoding="utf-8")


def test_alembic_env_targets_base_metadata() -> None:
    env_source = (BACKEND_DIR / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "target_metadata = Base.metadata" in env_source
    assert "compare_type=True" in env_source
    assert "get_settings" in env_source


def test_alembic_config_loads_without_live_database() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == []  # no migration revisions exist yet


# ---------------------------------------------------------------------------
# Architecture boundary
# ---------------------------------------------------------------------------


def _module_sources(package_dir: Path) -> list[tuple[Path, str]]:
    return [(path, path.read_text(encoding="utf-8")) for path in sorted(package_dir.glob("*.py"))]


def test_engine_package_stays_framework_free() -> None:
    forbidden = (
        "import fastapi",
        "from fastapi",
        "import sqlalchemy",
        "from sqlalchemy",
        "import alembic",
        "from alembic",
        "import pydantic",
        "from pydantic",
        "from app.core",
        "from app.db",
        "from app.api",
    )
    for path, source in _module_sources(APP_DIR / "engine"):
        for statement in forbidden:
            assert statement not in source, f"{path} contains {statement!r}"


def test_importing_package_stays_framework_free() -> None:
    forbidden = (
        "import fastapi",
        "from fastapi",
        "import sqlalchemy",
        "from sqlalchemy",
        "import alembic",
        "from alembic",
        "from app.core",
        "from app.db",
        "from app.api",
    )
    for path, source in _module_sources(APP_DIR / "importing"):
        for statement in forbidden:
            assert statement not in source, f"{path} contains {statement!r}"


def test_engine_results_are_unchanged_with_infrastructure_imported() -> None:
    # app.main (FastAPI, settings, routers) is already imported by this test
    # module; the pure engine must still produce the exact same results.
    from app.domain.enums import DataMode, ValueMode
    from app.domain.models import Bar
    from app.engine import (
        BacktestConfig,
        CommissionConfig,
        ExecutionConfig,
        SlippageConfig,
        TickSizeConfig,
        ValueConfig,
        run_backtest,
    )

    no_slip = SlippageConfig(mode=ValueMode.FIXED, value=Decimal("0"))
    no_comm = CommissionConfig(
        rate_enabled=False,
        rate=Decimal("0"),
        minimum_enabled=False,
        minimum=Decimal("0"),
        fixed_enabled=False,
        fixed=Decimal("0"),
    )
    config = BacktestConfig(
        data_mode=DataMode.CLOSE_ONLY,
        ohlc_path_mode=None,
        baseline_override=None,
        a_distance=ValueConfig(mode=ValueMode.FIXED, value=Decimal("2")),
        c_distance=ValueConfig(mode=ValueMode.FIXED, value=Decimal("4")),
        grid_step=ValueConfig(mode=ValueMode.FIXED, value=Decimal("1")),
        execution=ExecutionConfig(
            lot_size=1,
            trade_lots=1,
            buy_slippage=no_slip,
            sell_slippage=no_slip,
            buy_commission=no_comm,
            sell_commission=no_comm,
            tick_size=TickSizeConfig(enabled=False),
        ),
        initial_cash=Decimal("100"),
        initial_shares=0,
        annual_risk_free_rate=Decimal("0"),
    )
    bars = [
        Bar(date=date(2026, 1, 2), close=Decimal("10")),
        Bar(date=date(2026, 1, 3), close=Decimal("9")),
        Bar(date=date(2026, 1, 4), close=Decimal("10")),
    ]
    result = run_backtest(bars, config)
    assert result.final_state.cash == Decimal("101")
    assert result.final_state.shares == 0
    assert result == run_backtest(bars, config)


def test_no_business_models_auth_or_upload_code_introduced() -> None:
    assert dict(Base.metadata.tables) == {}
    assert not (APP_DIR / "auth").exists()
    assert not (APP_DIR / "api" / "routes" / "datasets.py").exists()
    assert not (APP_DIR / "api" / "routes" / "backtests.py").exists()
    assert not (APP_DIR / "db" / "models.py").exists()
