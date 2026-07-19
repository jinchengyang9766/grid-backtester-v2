"""Complete deterministic backtest orchestration (SPEC 10-22 integration).

run_backtest wires the already-frozen modules together and owns only ordering:
plan each segment once, materialize each planned action immediately (so Event
Equity snapshots the portfolio at that exact instant, before any later action
in the same segment moves cash or shares), and capture Daily Close Equity
inline the moment a Bar's final path point is reached — strictly before the
overnight segment into the next Bar can trade again. No pricing, crossing,
equity, or metric formula is re-implemented here.
"""

from collections.abc import Sequence

from app.domain.models import Bar
from app.engine.backtest_models import BacktestConfig, BacktestResult, FinalBacktestState
from app.engine.benchmarks import build_benchmark1, build_benchmark2
from app.engine.equity import capture_daily_equity, capture_event_equity, compute_initial_equity
from app.engine.equity_models import DailyEquityPoint, EventEquityPoint, SequencedAction
from app.engine.execution import (
    create_portfolio_state,
    execute_or_skip,
    validate_execution_config,
)
from app.engine.execution_models import ExecutionConfig, PortfolioState, TradeResult
from app.engine.grid import build_grid_setup
from app.engine.metrics import compute_backtest_metrics
from app.engine.path import build_path_segments, build_price_path, initialize_path_state
from app.engine.segment import create_traversal_state, plan_segment_actions
from app.engine.segment_models import (
    PlannedGridCrossing,
    SegmentTraversalState,
    ZoneEvent,
)

__all__ = ["run_backtest"]


def _materialize_action(
    planned: PlannedGridCrossing | ZoneEvent,
    *,
    portfolio: PortfolioState,
    traversal: SegmentTraversalState,
    execution: ExecutionConfig,
) -> TradeResult | ZoneEvent:
    if isinstance(planned, PlannedGridCrossing):
        return execute_or_skip(planned, portfolio=portfolio, traversal=traversal, config=execution)
    # Task 8 already applied this zone transition while planning; the immutable
    # event passes through unchanged and is never applied a second time.
    return planned


def run_backtest(bars: Sequence[Bar], config: BacktestConfig) -> BacktestResult:
    validate_execution_config(config.execution)

    path_points = build_price_path(bars, config.data_mode, ohlc_path_mode=config.ohlc_path_mode)
    initial_equity = compute_initial_equity(
        initial_cash=config.initial_cash,
        initial_shares=config.initial_shares,
        mark_price=path_points[0].price,
    )
    grid_setup = build_grid_setup(
        bars,
        baseline_override=config.baseline_override,
        a_distance=config.a_distance,
        c_distance=config.c_distance,
        grid_step=config.grid_step,
        tick_size=config.execution.tick_size,
    )
    segments = build_path_segments(path_points)
    traversal = create_traversal_state(initialize_path_state(path_points, grid_setup.boundaries))
    portfolio = create_portfolio_state(config.initial_cash, config.initial_shares)

    benchmark1 = build_benchmark1(
        bars, initial_cash=config.initial_cash, initial_shares=config.initial_shares
    )
    benchmark2 = build_benchmark2(
        bars,
        config.data_mode,
        initial_cash=config.initial_cash,
        initial_shares=config.initial_shares,
        config=config.execution,
    )

    running_peak = initial_equity
    next_event_sequence = 1
    actions: list[SequencedAction] = []
    event_equity: list[EventEquityPoint] = []
    daily_equity: list[DailyEquityPoint] = []
    bar_index = 0

    # CLOSE_ONLY's Bar 0 contributes the path's first (and its only, therefore
    # final) point, which no segment ever ends at -- capture it before the
    # first Close-to-Close segment can change the portfolio (SPEC 11.3/11.6).
    if path_points[0].is_bar_final:
        point, running_peak = capture_daily_equity(
            bar=bars[bar_index],
            portfolio=portfolio,
            boundaries=grid_setup.boundaries,
            running_peak_before=running_peak,
        )
        daily_equity.append(point)
        bar_index += 1

    for segment in segments:
        planned_actions = plan_segment_actions(
            segment,
            state=traversal,
            boundaries=grid_setup.boundaries,
            grid_levels=grid_setup.grid_levels,
        )
        for planned in planned_actions:
            materialized = _materialize_action(
                planned, portfolio=portfolio, traversal=traversal, execution=config.execution
            )
            sequenced = SequencedAction(event_sequence=next_event_sequence, action=materialized)
            actions.append(sequenced)
            event_equity.append(
                capture_event_equity(sequenced_action=sequenced, portfolio=portfolio)
            )
            next_event_sequence += 1

        if segment.end.is_bar_final:
            point, running_peak = capture_daily_equity(
                bar=bars[bar_index],
                portfolio=portfolio,
                boundaries=grid_setup.boundaries,
                running_peak_before=running_peak,
            )
            daily_equity.append(point)
            bar_index += 1

    metrics = compute_backtest_metrics(
        initial_equity=initial_equity,
        daily_equity=daily_equity,
        actions=actions,
        bar_dates=[bar.date for bar in bars],
        benchmark1=benchmark1,
        benchmark2=benchmark2,
        annual_risk_free_rate=config.annual_risk_free_rate,
    )
    final_state = FinalBacktestState(
        cash=portfolio.cash,
        shares=portfolio.shares,
        market_cursor=traversal.market_cursor,
        trade_anchor=traversal.trade_anchor,
        zone_state=traversal.zone_state,
    )
    return BacktestResult(
        initial_equity=initial_equity,
        grid_setup=grid_setup,
        actions=tuple(actions),
        event_equity=tuple(event_equity),
        daily_equity=tuple(daily_equity),
        benchmark1=benchmark1,
        benchmark2=benchmark2,
        metrics=metrics,
        final_state=final_state,
    )
