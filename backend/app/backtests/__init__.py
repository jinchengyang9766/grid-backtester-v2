"""Backtest application services: configuration adapting, execution, persistence."""

from app.backtests.configuration import (
    AdaptedConfiguration,
    adapt_configuration,
    generate_backtest_name,
)
from app.backtests.history import (
    BACKTEST_STATUSES,
    BacktestListPage,
    delete_owned_backtest,
    get_owned_backtest,
    list_owned_backtests,
    rename_owned_backtest,
)
from app.backtests.persistence import (
    ResultIntegrityError,
    persist_completed_run,
    persist_failed_run,
)
from app.backtests.projections import (
    load_daily_equity_projection,
    load_event_equity_projection,
    load_trade_projection,
    load_zone_event_projection,
)
from app.backtests.serialization import build_result_metrics, json_safe, plain_decimal
from app.backtests.service import create_backtest

__all__ = [
    "AdaptedConfiguration",
    "BACKTEST_STATUSES",
    "BacktestListPage",
    "ResultIntegrityError",
    "adapt_configuration",
    "build_result_metrics",
    "create_backtest",
    "delete_owned_backtest",
    "generate_backtest_name",
    "get_owned_backtest",
    "json_safe",
    "list_owned_backtests",
    "load_daily_equity_projection",
    "load_event_equity_projection",
    "load_trade_projection",
    "load_zone_event_projection",
    "persist_completed_run",
    "persist_failed_run",
    "plain_decimal",
    "rename_owned_backtest",
]
