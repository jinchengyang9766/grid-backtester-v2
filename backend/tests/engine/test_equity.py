"""Tests for initial-equity validation and daily/event equity capture."""

import inspect
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import SkipReason, TradeSide, TradeStatus, ZoneEventType, ZoneState
from app.domain.models import Bar
from app.engine.equity import (
    capture_daily_equity,
    capture_event_equity,
    compute_initial_equity,
)
from app.engine.equity_models import (
    InvalidEventSequenceError,
    NonPositiveRunningPeakError,
    SequencedAction,
    ZeroInitialEquityError,
)
from app.engine.execution_models import (
    NegativeInitialCashError,
    NegativeInitialSharesError,
    PortfolioState,
    TradeResult,
)
from app.engine.grid_models import ZoneBoundaries
from app.engine.segment_models import ZoneEvent

D = Decimal

BOUNDS = ZoneBoundaries(
    baseline=D("10"), a_lower=D("9"), a_upper=D("11"), c_lower=D("8"), c_upper=D("12")
)


def bar(day: int, close: str) -> Bar:
    return Bar(date=date(2026, 1, day), close=D(close))


def executed_trade(
    *,
    day: int = 2,
    side: TradeSide = TradeSide.BUY,
    grid_price: str = "10.00",
    execution_price: str = "10.00",
    shares: int = 6,
    commission: str = "0.00",
    slippage_cost: str = "0.00",
    cash_after: str = "40.00",
    shares_after: int = 6,
) -> TradeResult:
    return TradeResult(
        event_date=date(2026, 1, day),
        side=side,
        grid_price=D(grid_price),
        execution_price=D(execution_price),
        shares=shares,
        notional=D(execution_price) * shares,
        commission=D(commission),
        slippage_cost=D(slippage_cost),
        cash_after=D(cash_after),
        shares_after=shares_after,
        equity_after=D(cash_after) + shares_after * D(grid_price),
        status=TradeStatus.EXECUTED,
        skip_reason=None,
    )


def skipped_trade(
    *,
    day: int = 3,
    side: TradeSide = TradeSide.BUY,
    grid_price: str = "11.00",
    cash: str = "40.00",
    shares_held: int = 6,
) -> TradeResult:
    return TradeResult(
        event_date=date(2026, 1, day),
        side=side,
        grid_price=D(grid_price),
        execution_price=None,
        shares=6,
        notional=None,
        commission=None,
        slippage_cost=None,
        cash_after=D(cash),
        shares_after=shares_held,
        equity_after=D(cash) + shares_held * D(grid_price),
        status=TradeStatus.SKIPPED,
        skip_reason=SkipReason.INSUFFICIENT_CASH,
    )


def zone_event(*, day: int = 3, boundary: str = "11.00") -> ZoneEvent:
    return ZoneEvent(
        event_type=ZoneEventType.ENTER_C_ZONE,
        boundary_price=D(boundary),
        event_date=date(2026, 1, day),
        old_zone=ZoneState.IN_A,
        new_zone=ZoneState.IN_C,
    )


# ---------------------------------------------------------------------------
# Initial equity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mark", ["10.03", "10.20"])  # Open-style and Close-style marks
def test_initial_equity_cash_plus_shares(mark: str) -> None:
    equity = compute_initial_equity(initial_cash=D("100"), initial_shares=2, mark_price=D(mark))
    assert equity == D("100") + 2 * D(mark)


def test_initial_equity_cash_only_with_zero_shares_accepted() -> None:
    assert compute_initial_equity(
        initial_cash=D("100.1234"), initial_shares=0, mark_price=D("10")
    ) == D("100.1234")


def test_initial_equity_shares_only_with_zero_cash_accepted() -> None:
    assert compute_initial_equity(initial_cash=D("0"), initial_shares=3, mark_price=D("2.50")) == D(
        "7.50"
    )


def test_initial_equity_zero_cash_and_zero_shares_rejected() -> None:
    with pytest.raises(ZeroInitialEquityError):
        compute_initial_equity(initial_cash=D("0"), initial_shares=0, mark_price=D("10"))


def test_initial_equity_decimal_precision_retained() -> None:
    equity = compute_initial_equity(
        initial_cash=D("100.1234"), initial_shares=1, mark_price=D("0.0001")
    )
    assert str(equity) == "100.1235"


def test_initial_equity_reuses_existing_validation() -> None:
    with pytest.raises(NegativeInitialCashError):
        compute_initial_equity(initial_cash=D("-1"), initial_shares=0, mark_price=D("10"))
    with pytest.raises(NegativeInitialSharesError):
        compute_initial_equity(initial_cash=D("1"), initial_shares=-1, mark_price=D("10"))


# ---------------------------------------------------------------------------
# Daily equity capture
# ---------------------------------------------------------------------------


def test_daily_capture_snapshots_exact_close_equity() -> None:
    point, peak = capture_daily_equity(
        bar=bar(2, "10.00"),
        portfolio=PortfolioState(cash=D("40.00"), shares=6),
        boundaries=BOUNDS,
        running_peak_before=D("100.00"),
    )
    assert point.date == date(2026, 1, 2)
    assert point.close == D("10.00")
    assert point.cash == D("40.00")
    assert point.shares == 6
    assert point.equity == D("100.00")
    assert point.drawdown == D("0")
    assert peak == D("100.00")


@pytest.mark.parametrize(
    ("close", "expected_zone"),
    [("10.00", ZoneState.IN_A), ("11.50", ZoneState.IN_C), ("12.50", ZoneState.OUTSIDE_C)],
)
def test_daily_capture_classifies_zone_at_close(close: str, expected_zone: ZoneState) -> None:
    point, _ = capture_daily_equity(
        bar=bar(2, close),
        portfolio=PortfolioState(cash=D("10"), shares=0),
        boundaries=BOUNDS,
        running_peak_before=D("10"),
    )
    assert point.zone_at_close is expected_zone


def test_daily_capture_running_peak_rises_with_new_high() -> None:
    point, peak = capture_daily_equity(
        bar=bar(2, "20.00"),
        portfolio=PortfolioState(cash=D("0"), shares=6),
        boundaries=BOUNDS,
        running_peak_before=D("100"),
    )
    assert point.equity == D("120.00")
    assert peak == D("120.00")
    assert point.drawdown == D("0")


def test_daily_capture_peak_remains_after_decline() -> None:
    point, peak = capture_daily_equity(
        bar=bar(2, "10.00"),
        portfolio=PortfolioState(cash=D("30"), shares=6),
        boundaries=BOUNDS,
        running_peak_before=D("100"),
    )
    assert point.equity == D("90.00")
    assert peak == D("100")
    assert point.drawdown == D("-0.1")


def test_daily_capture_zero_equity_gives_drawdown_minus_one() -> None:
    point, peak = capture_daily_equity(
        bar=bar(2, "10.00"),
        portfolio=PortfolioState(cash=D("0"), shares=0),
        boundaries=BOUNDS,
        running_peak_before=D("100"),
    )
    assert point.equity == D("0")
    assert point.drawdown == D("-1")
    assert peak == D("100")


@pytest.mark.parametrize("peak", ["0", "-5"])
def test_daily_capture_nonpositive_running_peak_rejected(peak: str) -> None:
    with pytest.raises(NonPositiveRunningPeakError) as exc_info:
        capture_daily_equity(
            bar=bar(2, "10.00"),
            portfolio=PortfolioState(cash=D("10"), shares=0),
            boundaries=BOUNDS,
            running_peak_before=D(peak),
        )
    assert exc_info.value.value == D(peak)


def test_daily_capture_does_not_mutate_inputs() -> None:
    portfolio = PortfolioState(cash=D("40.00"), shares=6)
    the_bar = bar(2, "10.00")
    capture_daily_equity(
        bar=the_bar, portfolio=portfolio, boundaries=BOUNDS, running_peak_before=D("100")
    )
    assert portfolio.cash == D("40.00")
    assert portfolio.shares == 6
    assert the_bar == bar(2, "10.00")


def test_daily_capture_output_is_frozen_and_uses_no_execution_price() -> None:
    point, _ = capture_daily_equity(
        bar=bar(2, "10.00"),
        portfolio=PortfolioState(cash=D("40"), shares=6),
        boundaries=BOUNDS,
        running_peak_before=D("100"),
    )
    with pytest.raises(FrozenInstanceError):
        point.equity = D("0")  # type: ignore[misc]
    source = inspect.getsource(capture_daily_equity)
    assert "execution_price" not in source
    assert "grid_price" not in source
    assert "market_cursor" not in source


# ---------------------------------------------------------------------------
# Event equity capture
# ---------------------------------------------------------------------------


def test_event_capture_executed_trade_uses_grid_price_not_execution_price() -> None:
    trade = executed_trade(grid_price="10.00", execution_price="10.05")
    point = capture_event_equity(
        sequenced_action=SequencedAction(event_sequence=1, action=trade),
        portfolio=PortfolioState(cash=D("999"), shares=999),  # must be ignored for trades
    )
    assert point.date == trade.event_date
    assert point.event_sequence == 1
    assert point.market_price == D("10.00")
    assert point.cash == trade.cash_after
    assert point.shares == trade.shares_after
    assert point.equity == trade.equity_after
    assert point.equity != trade.cash_after + trade.shares_after * D("10.05")


def test_event_capture_skipped_trade_also_produces_point() -> None:
    trade = skipped_trade(cash="40.00", shares_held=6, grid_price="11.00")
    point = capture_event_equity(
        sequenced_action=SequencedAction(event_sequence=2, action=trade),
        portfolio=PortfolioState(cash=D("40.00"), shares=6),
    )
    assert point.event_sequence == 2
    assert point.cash == D("40.00")
    assert point.shares == 6
    assert point.equity == D("40.00") + 6 * D("11.00")
    assert point.equity == trade.equity_after


def test_event_capture_zone_event_uses_boundary_price_and_portfolio() -> None:
    event = zone_event(day=3, boundary="11.00")
    portfolio = PortfolioState(cash=D("40.00"), shares=6)
    point = capture_event_equity(
        sequenced_action=SequencedAction(event_sequence=3, action=event),
        portfolio=portfolio,
    )
    assert point.date == date(2026, 1, 3)
    assert point.event_sequence == 3
    assert point.market_price == D("11.00")
    assert point.cash == D("40.00")
    assert point.shares == 6
    assert point.equity == D("106.00")
    assert portfolio.cash == D("40.00")  # zone events never change the portfolio
    assert portfolio.shares == 6


@pytest.mark.parametrize("sequence", [0, -1])
def test_event_capture_nonpositive_sequence_rejected(sequence: int) -> None:
    with pytest.raises(InvalidEventSequenceError) as exc_info:
        capture_event_equity(
            sequenced_action=SequencedAction(event_sequence=sequence, action=executed_trade()),
            portfolio=PortfolioState(cash=D("0"), shares=0),
        )
    assert exc_info.value.event_sequence == sequence


def test_event_capture_output_frozen_and_decimal_precision_preserved() -> None:
    trade = executed_trade(grid_price="10.1000", cash_after="40.0000")
    point = capture_event_equity(
        sequenced_action=SequencedAction(event_sequence=1, action=trade),
        portfolio=PortfolioState(cash=D("0"), shares=0),
    )
    with pytest.raises(FrozenInstanceError):
        point.cash = D("0")  # type: ignore[misc]
    assert str(point.equity) == str(trade.equity_after)
