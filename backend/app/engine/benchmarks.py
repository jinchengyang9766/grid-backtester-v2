"""Deterministic Buy-and-Hold benchmark series (SPEC Section 20).

Benchmark 2's day-one buy reuses the exact strategy execution-price and
commission functions — first-price tick normalization, buy slippage from the
tick price, second tick normalization, then commission on the whole candidate
notional. The affordable-lot count comes from the frozen exponential-growth
plus binary-search algorithm, never a one-lot-at-a-time loop.
"""

from collections.abc import Sequence
from decimal import Decimal

from app.domain.enums import DataMode, TradeSide
from app.domain.models import Bar
from app.engine.benchmark_models import (
    BenchmarkDayOnePurchase,
    BenchmarkEquityPoint,
    BenchmarkSeries,
)
from app.engine.costs import compute_commission, compute_execution_price
from app.engine.execution import create_portfolio_state, validate_execution_config
from app.engine.execution_models import CommissionConfig, ExecutionConfig
from app.engine.grid import EmptyDatasetError, NonPositiveTickSizeError, round_to_tick
from app.engine.path import InvalidOhlcvBarError

__all__ = [
    "build_benchmark1",
    "build_benchmark2",
    "compute_benchmark2_day_one_purchase",
    "compute_benchmark2_prices",
    "select_benchmark2_reference_price",
]

_ZERO = Decimal("0")


def build_benchmark1(
    bars: Sequence[Bar],
    *,
    initial_cash: Decimal,
    initial_shares: int,
) -> BenchmarkSeries:
    if not bars:
        raise EmptyDatasetError("Cannot build a benchmark from an empty dataset.")
    create_portfolio_state(initial_cash, initial_shares)  # reuse nonnegative validation

    points = tuple(
        BenchmarkEquityPoint(
            date=bar.date,
            close=bar.close,
            cash=initial_cash,
            shares=initial_shares,
            equity=initial_cash + initial_shares * bar.close,
        )
        for bar in bars
    )
    return BenchmarkSeries(points=points, day_one_purchase=None)


def select_benchmark2_reference_price(bars: Sequence[Bar], data_mode: DataMode) -> Decimal:
    if not bars:
        raise EmptyDatasetError("Cannot build a benchmark from an empty dataset.")
    if data_mode is DataMode.OHLCV:
        if bars[0].open is None:
            raise InvalidOhlcvBarError(bar_index=0, missing_fields=("open",))
        return bars[0].open
    return bars[0].close


def compute_benchmark2_prices(
    *,
    reference_price: Decimal,
    config: ExecutionConfig,
) -> tuple[Decimal, Decimal]:
    tick = config.tick_size
    if tick.enabled:
        if tick.value is None or tick.value <= 0:
            raise NonPositiveTickSizeError(
                f"Tick size must be a positive value when enabled; got {tick.value}."
            )
        tick_price = round_to_tick(reference_price, tick.value)
    else:
        tick_price = reference_price

    execution_price = compute_execution_price(
        grid_price=tick_price,
        side=TradeSide.BUY,
        slippage=config.buy_slippage,
        tick_size=config.tick_size,
    )
    return tick_price, execution_price


def _max_affordable_lots(
    *,
    initial_cash: Decimal,
    execution_price: Decimal,
    lot_size: int,
    commission_config: CommissionConfig,
) -> int:
    def affordable(lots: int) -> bool:
        if lots == 0:
            return True  # by definition, without calling compute_commission
        shares = lots * lot_size
        notional = execution_price * shares
        commission = compute_commission(notional, commission_config)
        return notional + commission <= initial_cash

    lo, hi = 0, 1
    while affordable(hi):
        lo = hi
        hi *= 2
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if affordable(mid):
            lo = mid
        else:
            hi = mid
    return lo


def compute_benchmark2_day_one_purchase(
    *,
    initial_cash: Decimal,
    initial_shares: int,
    reference_price: Decimal,
    config: ExecutionConfig,
) -> BenchmarkDayOnePurchase:
    validate_execution_config(config)
    create_portfolio_state(initial_cash, initial_shares)  # reuse nonnegative validation

    tick_price, execution_price = compute_benchmark2_prices(
        reference_price=reference_price, config=config
    )
    lots = _max_affordable_lots(
        initial_cash=initial_cash,
        execution_price=execution_price,
        lot_size=config.lot_size,
        commission_config=config.buy_commission,
    )

    if lots == 0:
        # No order is attempted: nothing changes and no fee is ever charged.
        return BenchmarkDayOnePurchase(
            reference_price=reference_price,
            tick_price=tick_price,
            execution_price=execution_price,
            lots=0,
            shares_purchased=0,
            notional=_ZERO,
            commission=_ZERO,
            slippage_cost=_ZERO,
            cash_after=initial_cash,
            shares_after=initial_shares,
        )

    shares_purchased = lots * config.lot_size
    notional = execution_price * shares_purchased
    commission = compute_commission(notional, config.buy_commission)
    return BenchmarkDayOnePurchase(
        reference_price=reference_price,
        tick_price=tick_price,
        execution_price=execution_price,
        lots=lots,
        shares_purchased=shares_purchased,
        notional=notional,
        commission=commission,
        slippage_cost=abs(execution_price - tick_price) * shares_purchased,
        cash_after=initial_cash - notional - commission,
        shares_after=initial_shares + shares_purchased,
    )


def build_benchmark2(
    bars: Sequence[Bar],
    data_mode: DataMode,
    *,
    initial_cash: Decimal,
    initial_shares: int,
    config: ExecutionConfig,
) -> BenchmarkSeries:
    if not bars:
        raise EmptyDatasetError("Cannot build a benchmark from an empty dataset.")
    reference_price = select_benchmark2_reference_price(bars, data_mode)
    purchase = compute_benchmark2_day_one_purchase(
        initial_cash=initial_cash,
        initial_shares=initial_shares,
        reference_price=reference_price,
        config=config,
    )
    points = tuple(
        BenchmarkEquityPoint(
            date=bar.date,
            close=bar.close,
            cash=purchase.cash_after,
            shares=purchase.shares_after,
            equity=purchase.cash_after + purchase.shares_after * bar.close,
        )
        for bar in bars
    )
    return BenchmarkSeries(points=points, day_one_purchase=purchase)
