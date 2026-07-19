"""Daily Close Equity and Event-Level Equity capture (SPEC 17.1 and 22).

Capture timing belongs to the Task 12 orchestrator: it validates initial
equity, initializes the running peak to that initial equity, and calls
capture_daily_equity exactly once per Bar at that Bar's final path point.
The functions here only snapshot already-produced state; they never mutate
the portfolio, execute actions, or allocate event sequences.
"""

from decimal import Decimal

from app.domain.models import Bar
from app.engine.equity_models import (
    DailyEquityPoint,
    EventEquityPoint,
    InvalidEventSequenceError,
    NonPositiveRunningPeakError,
    SequencedAction,
    ZeroInitialEquityError,
)
from app.engine.execution import create_portfolio_state
from app.engine.execution_models import PortfolioState, TradeResult
from app.engine.grid import classify_zone
from app.engine.grid_models import ZoneBoundaries

__all__ = [
    "capture_daily_equity",
    "capture_event_equity",
    "compute_initial_equity",
]

_ONE = Decimal("1")


def compute_initial_equity(
    *,
    initial_cash: Decimal,
    initial_shares: int,
    mark_price: Decimal,
) -> Decimal:
    create_portfolio_state(initial_cash, initial_shares)  # reuse nonnegative validation
    initial_equity = initial_cash + initial_shares * mark_price
    if initial_equity == 0:
        raise ZeroInitialEquityError()
    return initial_equity


def capture_daily_equity(
    *,
    bar: Bar,
    portfolio: PortfolioState,
    boundaries: ZoneBoundaries,
    running_peak_before: Decimal,
) -> tuple[DailyEquityPoint, Decimal]:
    """Snapshot one Bar's close equity; the seeded running peak keeps the
    drawdown denominator positive even when equity itself reaches zero."""
    if running_peak_before <= 0:
        raise NonPositiveRunningPeakError(running_peak_before)

    equity = portfolio.cash + portfolio.shares * bar.close
    running_peak_after = max(running_peak_before, equity)
    drawdown = equity / running_peak_after - _ONE
    point = DailyEquityPoint(
        date=bar.date,
        close=bar.close,
        cash=portfolio.cash,
        shares=portfolio.shares,
        equity=equity,
        drawdown=drawdown,
        zone_at_close=classify_zone(bar.close, boundaries),
    )
    return point, running_peak_after


def capture_event_equity(
    *,
    sequenced_action: SequencedAction,
    portfolio: PortfolioState,
) -> EventEquityPoint:
    """Mark equity at the action's market price: a trade's canonical grid price
    (never its execution price) or a zone event's boundary price (SPEC 16.4)."""
    if sequenced_action.event_sequence < 1:
        raise InvalidEventSequenceError(sequenced_action.event_sequence)

    action = sequenced_action.action
    if isinstance(action, TradeResult):
        return EventEquityPoint(
            date=action.event_date,
            event_sequence=sequenced_action.event_sequence,
            market_price=action.grid_price,
            cash=action.cash_after,
            shares=action.shares_after,
            equity=action.cash_after + action.shares_after * action.grid_price,
        )
    return EventEquityPoint(
        date=action.event_date,
        event_sequence=sequenced_action.event_sequence,
        market_price=action.boundary_price,
        cash=portfolio.cash,
        shares=portfolio.shares,
        equity=portfolio.cash + portfolio.shares * action.boundary_price,
    )
