"""Deterministic order execution and ordered action materialization.

Implements SPEC Sections 16 (execution pipeline), 17 (constraints and skip
reasons), and the Section 15 anchor invariant: trade_anchor changes only on
a successful fill, to the canonical grid price, and nowhere else.
"""

from collections.abc import Sequence
from decimal import Decimal

from app.domain.enums import SkipReason, TradeSide, TradeStatus
from app.engine.costs import compute_commission, compute_execution_price
from app.engine.execution_models import (
    ExecutionConfig,
    InvalidLotSizeError,
    InvalidTradeLotsError,
    NegativeCommissionComponentError,
    NegativeInitialCashError,
    NegativeInitialSharesError,
    NegativeSlippageError,
    PortfolioState,
    TradeResult,
)
from app.engine.grid import NonPositiveTickSizeError
from app.engine.segment_models import (
    PlannedGridCrossing,
    SegmentTraversalState,
    ZoneEvent,
)

__all__ = [
    "create_portfolio_state",
    "execute_or_skip",
    "materialize_segment_actions",
    "order_share_quantity",
    "validate_execution_config",
]


def create_portfolio_state(initial_cash: Decimal, initial_shares: int) -> PortfolioState:
    if initial_cash < 0:
        raise NegativeInitialCashError(initial_cash)
    if initial_shares < 0:
        raise NegativeInitialSharesError(initial_shares)
    return PortfolioState(cash=initial_cash, shares=initial_shares)


def validate_execution_config(config: ExecutionConfig) -> None:
    if config.lot_size < 1:
        raise InvalidLotSizeError(config.lot_size)
    if config.trade_lots < 1:
        raise InvalidTradeLotsError(config.trade_lots)

    for side, slippage in (
        (TradeSide.BUY, config.buy_slippage),
        (TradeSide.SELL, config.sell_slippage),
    ):
        if slippage.value < 0:
            raise NegativeSlippageError(side=side, value=slippage.value)

    for side, commission in (
        (TradeSide.BUY, config.buy_commission),
        (TradeSide.SELL, config.sell_commission),
    ):
        # Only enabled components are validated; a disabled component's value
        # is never read (SPEC 19.1 / ED-25), so it is never validated either.
        if commission.rate_enabled and commission.rate < 0:
            raise NegativeCommissionComponentError(
                side=side, component="rate", value=commission.rate
            )
        if commission.minimum_enabled and commission.minimum < 0:
            raise NegativeCommissionComponentError(
                side=side, component="minimum", value=commission.minimum
            )
        if commission.fixed_enabled and commission.fixed < 0:
            raise NegativeCommissionComponentError(
                side=side, component="fixed", value=commission.fixed
            )

    if config.tick_size.enabled and (config.tick_size.value is None or config.tick_size.value <= 0):
        raise NonPositiveTickSizeError(
            f"Tick size must be a positive value when enabled; got {config.tick_size.value}."
        )


def order_share_quantity(config: ExecutionConfig) -> int:
    return config.trade_lots * config.lot_size


def execute_or_skip(
    crossing: PlannedGridCrossing,
    *,
    portfolio: PortfolioState,
    traversal: SegmentTraversalState,
    config: ExecutionConfig,
) -> TradeResult:
    side = crossing.side
    grid_price = crossing.grid_level
    slippage = config.buy_slippage if side is TradeSide.BUY else config.sell_slippage
    commission_config = config.buy_commission if side is TradeSide.BUY else config.sell_commission
    execution_price = compute_execution_price(
        grid_price=grid_price, side=side, slippage=slippage, tick_size=config.tick_size
    )
    order_shares = order_share_quantity(config)

    def skipped(reason: SkipReason) -> TradeResult:
        return TradeResult(
            event_date=crossing.event_date,
            side=side,
            grid_price=grid_price,
            execution_price=None,
            shares=order_shares,
            notional=None,
            commission=None,
            slippage_cost=None,
            cash_after=portfolio.cash,
            shares_after=portfolio.shares,
            equity_after=portfolio.cash + portfolio.shares * grid_price,
            status=TradeStatus.SKIPPED,
            skip_reason=reason,
        )

    if side is TradeSide.BUY:
        notional = execution_price * order_shares
        commission = compute_commission(notional, commission_config)
        total_cost = notional + commission
        if total_cost > portfolio.cash:
            return skipped(SkipReason.INSUFFICIENT_CASH)
        portfolio.cash -= total_cost
        portfolio.shares += order_shares
    else:
        # Shares are checked first; the cash-after-commission constraint is
        # only evaluated once the shares check passes (SPEC 16.3).
        if order_shares > portfolio.shares:
            return skipped(SkipReason.INSUFFICIENT_SHARES)
        notional = execution_price * order_shares
        commission = compute_commission(notional, commission_config)
        candidate_cash = portfolio.cash + notional - commission
        if candidate_cash < 0:
            return skipped(SkipReason.INSUFFICIENT_CASH_FOR_COMMISSION)
        portfolio.cash = candidate_cash
        portfolio.shares -= order_shares

    traversal.trade_anchor = grid_price  # canonical grid price, never execution price
    return TradeResult(
        event_date=crossing.event_date,
        side=side,
        grid_price=grid_price,
        execution_price=execution_price,
        shares=order_shares,
        notional=notional,
        commission=commission,
        slippage_cost=abs(execution_price - grid_price) * order_shares,
        cash_after=portfolio.cash,
        shares_after=portfolio.shares,
        equity_after=portfolio.cash + portfolio.shares * grid_price,
        status=TradeStatus.EXECUTED,
        skip_reason=None,
    )


def materialize_segment_actions(
    actions: Sequence[PlannedGridCrossing | ZoneEvent],
    *,
    portfolio: PortfolioState,
    traversal: SegmentTraversalState,
    config: ExecutionConfig,
) -> tuple[TradeResult | ZoneEvent, ...]:
    results: list[TradeResult | ZoneEvent] = []
    for action in actions:
        if isinstance(action, PlannedGridCrossing):
            results.append(
                execute_or_skip(action, portfolio=portfolio, traversal=traversal, config=config)
            )
        else:
            # Task 8 already applied the zone transition during planning; the
            # event passes through unchanged, in order, exactly once.
            results.append(action)
    return tuple(results)
