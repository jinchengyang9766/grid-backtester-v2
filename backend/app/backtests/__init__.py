"""Backtest application services: configuration adapting, execution, persistence."""

from app.backtests.configuration import (
    AdaptedConfiguration,
    adapt_configuration,
    generate_backtest_name,
)
from app.backtests.persistence import (
    ResultIntegrityError,
    persist_completed_run,
    persist_failed_run,
)
from app.backtests.serialization import build_result_metrics, json_safe, plain_decimal
from app.backtests.service import create_backtest

__all__ = [
    "AdaptedConfiguration",
    "ResultIntegrityError",
    "adapt_configuration",
    "build_result_metrics",
    "create_backtest",
    "generate_backtest_name",
    "json_safe",
    "persist_completed_run",
    "persist_failed_run",
    "plain_decimal",
]
