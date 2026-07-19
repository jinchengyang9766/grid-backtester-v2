"""Immutable configuration and result models for the complete backtest run."""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import DataMode, OHLCPathMode, ZoneState
from app.engine.benchmark_models import BenchmarkSeries
from app.engine.equity_models import DailyEquityPoint, EventEquityPoint, SequencedAction
from app.engine.execution_models import ExecutionConfig
from app.engine.grid_models import GridSetup, ValueConfig
from app.engine.metric_models import BacktestMetrics

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "FinalBacktestState",
]


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Complete run configuration; data_mode is explicit, never inferred."""

    data_mode: DataMode
    ohlc_path_mode: OHLCPathMode | None
    baseline_override: Decimal | None
    a_distance: ValueConfig
    c_distance: ValueConfig
    grid_step: ValueConfig
    execution: ExecutionConfig
    initial_cash: Decimal
    initial_shares: int
    annual_risk_free_rate: Decimal


@dataclass(frozen=True, slots=True)
class FinalBacktestState:
    """Immutable end-of-run snapshot of portfolio and traversal state."""

    cash: Decimal
    shares: int
    market_cursor: Decimal
    trade_anchor: Decimal
    zone_state: ZoneState


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Complete deterministic run output; actions and event_equity align 1:1."""

    initial_equity: Decimal
    grid_setup: GridSetup
    actions: tuple[SequencedAction, ...]
    event_equity: tuple[EventEquityPoint, ...]
    daily_equity: tuple[DailyEquityPoint, ...]
    benchmark1: BenchmarkSeries
    benchmark2: BenchmarkSeries
    metrics: BacktestMetrics
    final_state: FinalBacktestState
