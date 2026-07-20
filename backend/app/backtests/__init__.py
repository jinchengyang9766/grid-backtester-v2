"""Backtest application services: configuration adapting, execution, persistence."""

from app.backtests.comparison import compare_owned_backtests
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
from app.backtests.replay import (
    configuration_request_from_stored,
    deep_merge_configuration,
    duplicate_backtest,
    rerun_backtest,
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
    "compare_owned_backtests",
    "configuration_request_from_stored",
    "create_backtest",
    "deep_merge_configuration",
    "delete_owned_backtest",
    "duplicate_backtest",
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
    "rerun_backtest",
]
