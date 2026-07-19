"""Backtest metric formulas over Daily Close Equity (SPEC Section 21).

Every series metric consumes the Daily Close Equity sequence, never
EventEquity. The drawdown running peak is seeded with the validated initial
equity, so the denominator stays positive even when a day's equity reaches
exactly zero (SPEC 21.4/21.11). All arithmetic is Decimal end to end.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.enums import TradeSide, TradeStatus, ZoneEventType, ZoneState
from app.engine.benchmark_models import BenchmarkSeries
from app.engine.equity_models import (
    DailyEquityPoint,
    SequencedAction,
    ZeroInitialEquityError,
)
from app.engine.execution_models import TradeResult
from app.engine.metric_models import (
    BacktestMetrics,
    EmptyEquitySeriesError,
    EquitySeriesMetrics,
    FirstReturnMetrics,
    InvalidRiskFreeRateError,
    TradeCostMetrics,
    TradeDateNotFoundError,
    ZoneMetrics,
)
from app.engine.segment_models import ZoneEvent

__all__ = [
    "compute_annualized_return",
    "compute_backtest_metrics",
    "compute_equity_series_metrics",
    "compute_first_return_to_initial_shares",
    "compute_maximum_drawdown",
    "compute_sharpe_ratio",
    "compute_trade_cost_metrics",
    "compute_zone_metrics",
]

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TRADING_DAYS_PER_YEAR = Decimal("252")


def compute_annualized_return(total_return: Decimal, periods: int) -> Decimal | None:
    if periods <= 0:
        return None
    if total_return <= -1:
        # A total wipeout is deliberately unreported rather than annualized (SPEC 21.2).
        return None
    return (_ONE + total_return) ** (_TRADING_DAYS_PER_YEAR / periods) - _ONE


def compute_sharpe_ratio(
    equities: Sequence[Decimal],
    annual_risk_free_rate: Decimal,
) -> Decimal | None:
    if annual_risk_free_rate <= -1:
        raise InvalidRiskFreeRateError(annual_risk_free_rate)
    if len(equities) < 3:
        return None  # fewer than two daily returns
    if any(previous <= 0 for previous in equities[:-1]):
        return None  # a required daily-return denominator is not positive

    daily_returns = [equities[i] / equities[i - 1] - _ONE for i in range(1, len(equities))]
    rf_daily = (_ONE + annual_risk_free_rate) ** (_ONE / _TRADING_DAYS_PER_YEAR) - _ONE
    excess = [daily_return - rf_daily for daily_return in daily_returns]

    n = len(excess)
    mean_excess = sum(excess, _ZERO) / n
    sample_variance = sum(((value - mean_excess) ** 2 for value in excess), _ZERO) / (n - 1)
    std_excess = sample_variance.sqrt()
    if std_excess == 0:
        return _ZERO if mean_excess == 0 else None
    return mean_excess / std_excess * _TRADING_DAYS_PER_YEAR.sqrt()


def compute_maximum_drawdown(
    equities: Sequence[Decimal],
    initial_equity: Decimal,
) -> Decimal:
    if not equities:
        raise EmptyEquitySeriesError()
    if initial_equity <= 0:
        raise ZeroInitialEquityError()

    running_peak = initial_equity
    maximum_drawdown = _ZERO
    for equity in equities:
        running_peak = max(running_peak, equity)
        drawdown = equity / running_peak - _ONE
        maximum_drawdown = min(maximum_drawdown, drawdown)
    return maximum_drawdown


def compute_equity_series_metrics(
    equities: Sequence[Decimal],
    *,
    initial_equity: Decimal,
    annual_risk_free_rate: Decimal,
) -> EquitySeriesMetrics:
    if not equities:
        raise EmptyEquitySeriesError()
    if initial_equity <= 0:
        raise ZeroInitialEquityError()

    final_equity = equities[-1]
    total_return = final_equity / initial_equity - _ONE
    return EquitySeriesMetrics(
        initial_equity=initial_equity,
        final_equity=final_equity,
        net_profit=final_equity - initial_equity,
        total_return=total_return,
        annualized_return=compute_annualized_return(total_return, len(equities) - 1),
        maximum_drawdown=compute_maximum_drawdown(equities, initial_equity),
        sharpe_ratio=compute_sharpe_ratio(equities, annual_risk_free_rate),
    )


def compute_trade_cost_metrics(actions: Sequence[SequencedAction]) -> TradeCostMetrics:
    total_commission = _ZERO
    total_slippage_cost = _ZERO
    executed_trades = 0
    skipped_trades = 0
    buy_count = 0
    sell_count = 0

    for sequenced in actions:
        action = sequenced.action
        if not isinstance(action, TradeResult):
            continue
        if action.status is TradeStatus.EXECUTED:
            executed_trades += 1
            if action.commission is not None:
                total_commission += action.commission
            if action.slippage_cost is not None:
                total_slippage_cost += action.slippage_cost
            if action.side is TradeSide.BUY:
                buy_count += 1
            else:
                sell_count += 1
        else:
            skipped_trades += 1

    return TradeCostMetrics(
        total_commission=total_commission,
        total_slippage_cost=total_slippage_cost,
        executed_trades=executed_trades,
        skipped_trades=skipped_trades,
        buy_count=buy_count,
        sell_count=sell_count,
    )


def compute_zone_metrics(
    daily_equity: Sequence[DailyEquityPoint],
    actions: Sequence[SequencedAction],
) -> ZoneMetrics:
    zone_event_counts = dict.fromkeys(ZoneEventType, 0)
    for sequenced in actions:
        action = sequenced.action
        if isinstance(action, ZoneEvent):
            zone_event_counts[action.event_type] += 1

    return ZoneMetrics(
        days_closed_in_a_zone=sum(
            1 for point in daily_equity if point.zone_at_close is ZoneState.IN_A
        ),
        days_closed_in_c_zone=sum(
            1 for point in daily_equity if point.zone_at_close is ZoneState.IN_C
        ),
        days_closed_outside_c=sum(
            1 for point in daily_equity if point.zone_at_close is ZoneState.OUTSIDE_C
        ),
        zone_event_counts=zone_event_counts,
    )


def compute_first_return_to_initial_shares(
    actions: Sequence[SequencedAction],
    *,
    initial_shares: int,
    bar_dates: Sequence[date],
) -> FirstReturnMetrics:
    ordered = sorted(actions, key=lambda sequenced: sequenced.event_sequence)
    sorted_dates = sorted(set(bar_dates))

    has_deviated = False
    for sequenced in ordered:
        action = sequenced.action
        if not isinstance(action, TradeResult) or action.status is not TradeStatus.EXECUTED:
            continue
        if not has_deviated:
            if action.shares_after != initial_shares:
                has_deviated = True
            continue  # the fill causing the first deviation is never itself a return
        if action.shares_after != initial_shares:
            continue
        try:
            days = sorted_dates.index(action.event_date)
        except ValueError:
            raise TradeDateNotFoundError(action.event_date) from None
        return FirstReturnMetrics(equity=action.equity_after, days=days)

    return FirstReturnMetrics(equity=None, days=None)


def compute_backtest_metrics(
    *,
    initial_equity: Decimal,
    daily_equity: Sequence[DailyEquityPoint],
    actions: Sequence[SequencedAction],
    bar_dates: Sequence[date],
    benchmark1: BenchmarkSeries,
    benchmark2: BenchmarkSeries,
    annual_risk_free_rate: Decimal,
) -> BacktestMetrics:
    if benchmark2.day_one_purchase is None:
        raise ValueError("Benchmark 2 series must carry its day-one purchase.")

    strategy = compute_equity_series_metrics(
        [point.equity for point in daily_equity],
        initial_equity=initial_equity,
        annual_risk_free_rate=annual_risk_free_rate,
    )
    benchmark1_metrics = compute_equity_series_metrics(
        [point.equity for point in benchmark1.points],
        initial_equity=initial_equity,
        annual_risk_free_rate=annual_risk_free_rate,
    )
    benchmark2_metrics = compute_equity_series_metrics(
        [point.equity for point in benchmark2.points],
        initial_equity=initial_equity,
        annual_risk_free_rate=annual_risk_free_rate,
    )

    # Benchmark 1 holds the initial portfolio untouched, so its constant share
    # count is exactly the run's initial_shares.
    initial_shares = benchmark1.points[0].shares

    return BacktestMetrics(
        strategy=strategy,
        trade_costs=compute_trade_cost_metrics(actions),
        zones=compute_zone_metrics(daily_equity, actions),
        first_return=compute_first_return_to_initial_shares(
            actions, initial_shares=initial_shares, bar_dates=bar_dates
        ),
        benchmark1=benchmark1_metrics,
        benchmark2=benchmark2_metrics,
        benchmark2_day_one_commission=benchmark2.day_one_purchase.commission,
        benchmark2_day_one_slippage_cost=benchmark2.day_one_purchase.slippage_cost,
    )
