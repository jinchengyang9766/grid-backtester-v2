"""Tests for the complete deterministic backtest orchestration loop."""

import inspect
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import (
    DataMode,
    OHLCPathMode,
    SkipReason,
    TradeSide,
    TradeStatus,
    ValueMode,
    ZoneEventType,
    ZoneState,
)
from app.domain.models import Bar
from app.engine.backtest import run_backtest
from app.engine.backtest_models import BacktestConfig, BacktestResult, FinalBacktestState
from app.engine.equity_models import ZeroInitialEquityError
from app.engine.execution_models import (
    CommissionConfig,
    ExecutionConfig,
    InvalidLotSizeError,
    NegativeInitialCashError,
    NegativeInitialSharesError,
    SlippageConfig,
    TradeResult,
)
from app.engine.grid import InvalidZoneConfigError
from app.engine.grid_models import TickSizeConfig, ValueConfig
from app.engine.metric_models import InvalidRiskFreeRateError
from app.engine.path import OhlcPathModeRequiredError
from app.engine.segment_models import ZoneEvent

from app.engine.grid import EmptyDatasetError  # isort: skip

D = Decimal


def close_bar(day: int, close: str) -> Bar:
    return Bar(date=date(2026, 1, day), close=D(close))


def ohlcv_bar(day: int, open_: str, high: str, low: str, close: str) -> Bar:
    return Bar(date=date(2026, 1, day), close=D(close), open=D(open_), high=D(high), low=D(low))


def fixed(value: str) -> ValueConfig:
    return ValueConfig(mode=ValueMode.FIXED, value=D(value))


def no_commission() -> CommissionConfig:
    return CommissionConfig(
        rate_enabled=False,
        rate=D("0"),
        minimum_enabled=False,
        minimum=D("0"),
        fixed_enabled=False,
        fixed=D("0"),
    )


def fixed_commission(value: str) -> CommissionConfig:
    return CommissionConfig(
        rate_enabled=False,
        rate=D("0"),
        minimum_enabled=False,
        minimum=D("0"),
        fixed_enabled=True,
        fixed=D(value),
    )


def execution_config(
    *,
    lot_size: int = 1,
    trade_lots: int = 1,
    buy_commission: CommissionConfig | None = None,
    sell_commission: CommissionConfig | None = None,
) -> ExecutionConfig:
    no_slip = SlippageConfig(mode=ValueMode.FIXED, value=D("0"))
    return ExecutionConfig(
        lot_size=lot_size,
        trade_lots=trade_lots,
        buy_slippage=no_slip,
        sell_slippage=no_slip,
        buy_commission=buy_commission if buy_commission is not None else no_commission(),
        sell_commission=sell_commission if sell_commission is not None else no_commission(),
        tick_size=TickSizeConfig(enabled=False),
    )


def make_config(
    *,
    data_mode: DataMode = DataMode.CLOSE_ONLY,
    ohlc_path_mode: OHLCPathMode | None = None,
    baseline_override: str | None = None,
    execution: ExecutionConfig | None = None,
    initial_cash: str = "100",
    initial_shares: int = 0,
    annual_risk_free_rate: str = "0",
    a_distance: str = "2",
    c_distance: str = "4",
    grid_step: str = "1",
) -> BacktestConfig:
    return BacktestConfig(
        data_mode=data_mode,
        ohlc_path_mode=ohlc_path_mode,
        baseline_override=None if baseline_override is None else D(baseline_override),
        a_distance=fixed(a_distance),
        c_distance=fixed(c_distance),
        grid_step=fixed(grid_step),
        execution=execution if execution is not None else execution_config(),
        initial_cash=D(initial_cash),
        initial_shares=initial_shares,
        annual_risk_free_rate=D(annual_risk_free_rate),
    )


DEMO_BARS = [
    close_bar(2, "10"),
    close_bar(3, "9"),
    close_bar(4, "8"),
    close_bar(5, "9"),
    close_bar(6, "10"),
]


def run_demo() -> BacktestResult:
    return run_backtest(DEMO_BARS, make_config())


def trades_of(result: BacktestResult) -> list[TradeResult]:
    return [
        sequenced.action
        for sequenced in result.actions
        if isinstance(sequenced.action, TradeResult)
    ]


def zone_events_of(result: BacktestResult) -> list[ZoneEvent]:
    return [
        sequenced.action for sequenced in result.actions if isinstance(sequenced.action, ZoneEvent)
    ]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_result_models_are_frozen_tuples_of_decimals() -> None:
    config = make_config()
    result = run_demo()
    with pytest.raises(FrozenInstanceError):
        config.initial_cash = D("1")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.initial_equity = D("1")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.final_state.cash = D("1")  # type: ignore[misc]
    assert isinstance(result.actions, tuple)
    assert isinstance(result.event_equity, tuple)
    assert isinstance(result.daily_equity, tuple)
    assert type(result.initial_equity) is Decimal
    assert type(result.final_state.cash) is Decimal
    assert type(result.daily_equity[0].equity) is Decimal
    assert isinstance(result.final_state, FinalBacktestState)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_empty_bars_rejected() -> None:
    with pytest.raises(EmptyDatasetError):
        run_backtest([], make_config())


def test_invalid_execution_config_propagates() -> None:
    config = make_config(execution=execution_config(lot_size=0))
    with pytest.raises(InvalidLotSizeError):
        run_backtest(DEMO_BARS, config)


def test_zero_initial_equity_rejected_before_processing() -> None:
    with pytest.raises(ZeroInitialEquityError):
        run_backtest(DEMO_BARS, make_config(initial_cash="0", initial_shares=0))


def test_negative_initial_cash_and_shares_rejected() -> None:
    with pytest.raises(NegativeInitialCashError):
        run_backtest(DEMO_BARS, make_config(initial_cash="-1"))
    with pytest.raises(NegativeInitialSharesError):
        run_backtest(DEMO_BARS, make_config(initial_shares=-1))


def test_ohlcv_without_path_mode_rejected() -> None:
    bars = [ohlcv_bar(2, "10", "10", "9", "10")]
    with pytest.raises(OhlcPathModeRequiredError):
        run_backtest(bars, make_config(data_mode=DataMode.OHLCV, ohlc_path_mode=None))


def test_invalid_grid_config_propagates() -> None:
    config = make_config(a_distance="4", c_distance="4")
    with pytest.raises(InvalidZoneConfigError):
        run_backtest(DEMO_BARS, config)


def test_invalid_risk_free_rate_propagates() -> None:
    with pytest.raises(InvalidRiskFreeRateError):
        run_backtest(DEMO_BARS, make_config(annual_risk_free_rate="-1"))


def test_inputs_are_not_mutated() -> None:
    bars = [close_bar(2, "10"), close_bar(3, "9")]
    config = make_config()
    run_backtest(bars, config)
    assert bars == [close_bar(2, "10"), close_bar(3, "9")]
    assert config == make_config()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_ohlcv_cursor_and_anchor_begin_at_first_open_not_baseline() -> None:
    bars = [ohlcv_bar(2, "10.5", "10.5", "10.4", "10.4")]
    config = make_config(
        data_mode=DataMode.OHLCV,
        ohlc_path_mode=OHLCPathMode.AUTO,
        baseline_override="100",
    )
    result = run_backtest(bars, config)
    # No trades: OUTSIDE_C the whole run, far below the baseline-100 grid.
    assert result.actions == ()
    assert result.final_state.trade_anchor == D("10.5")  # first Open, not baseline 100
    assert result.final_state.market_cursor == D("10.4")  # final Close
    assert result.final_state.zone_state is ZoneState.OUTSIDE_C  # from the first actual point
    assert result.grid_setup.baseline == D("100")


def test_close_only_cursor_and_anchor_begin_at_first_close() -> None:
    result = run_backtest([close_bar(2, "10")], make_config())
    assert result.final_state.trade_anchor == D("10")
    assert result.final_state.market_cursor == D("10")
    assert result.final_state.zone_state is ZoneState.IN_A


def test_same_initial_portfolio_for_strategy_and_benchmarks() -> None:
    result = run_backtest(DEMO_BARS, make_config(initial_cash="100", initial_shares=3))
    assert result.benchmark1.points[0].cash == D("100")
    assert result.benchmark1.points[0].shares == 3
    purchase = result.benchmark2.day_one_purchase
    assert purchase is not None
    assert purchase.shares_after == 3 + purchase.shares_purchased
    assert result.daily_equity[0].cash == D("100")
    assert result.daily_equity[0].shares == 3


# ---------------------------------------------------------------------------
# One-Bar runs
# ---------------------------------------------------------------------------


def test_close_only_single_bar_run() -> None:
    result = run_backtest([close_bar(2, "10")], make_config())
    assert result.actions == ()
    assert result.event_equity == ()
    assert len(result.daily_equity) == 1
    assert result.daily_equity[0].date == date(2026, 1, 2)
    assert result.daily_equity[0].equity == D("100")
    assert result.final_state.market_cursor == D("10")
    assert result.final_state.trade_anchor == D("10")
    assert result.metrics.strategy.annualized_return is None
    assert result.metrics.strategy.sharpe_ratio is None


def test_ohlcv_single_bar_run_processes_full_intraday_path() -> None:
    # AUTO with Close >= Open walks Open -> Low -> High -> Close: 10 -> 9 -> 10 -> 10.
    bars = [ohlcv_bar(2, "10", "10", "9", "10")]
    config = make_config(data_mode=DataMode.OHLCV, ohlc_path_mode=OHLCPathMode.AUTO)
    result = run_backtest(bars, config)
    sides = [(t.side, t.grid_price) for t in trades_of(result)]
    assert sides == [(TradeSide.BUY, D("9")), (TradeSide.SELL, D("10"))]
    assert len(result.daily_equity) == 1
    # The intraday round trip is already inside the day's Close snapshot.
    assert result.daily_equity[0].cash == D("101")
    assert result.daily_equity[0].shares == 0
    assert result.daily_equity[0].equity == D("101")


# ---------------------------------------------------------------------------
# Daily capture timing
# ---------------------------------------------------------------------------


def test_close_only_first_day_captured_before_first_segment() -> None:
    # 10 -> 9 executes a BUY, but Day 1's snapshot must predate it.
    result = run_backtest([close_bar(2, "10"), close_bar(3, "9")], make_config())
    assert result.daily_equity[0].cash == D("100")
    assert result.daily_equity[0].shares == 0
    assert result.daily_equity[1].cash == D("91")
    assert result.daily_equity[1].shares == 1


def test_overnight_trade_cannot_change_prior_day_snapshot() -> None:
    bars = [
        ohlcv_bar(2, "10", "10", "9", "9"),  # HIGH_FIRST: 10 -> 10 -> 9 -> 9, BUY at 9
        ohlcv_bar(3, "10", "10", "10", "10"),  # overnight 9 -> 10 executes the SELL
    ]
    config = make_config(data_mode=DataMode.OHLCV, ohlc_path_mode=OHLCPathMode.AUTO)
    result = run_backtest(bars, config)

    buy, sell = trades_of(result)
    assert (buy.side, buy.event_date) == (TradeSide.BUY, date(2026, 1, 2))
    assert (sell.side, sell.event_date) == (TradeSide.SELL, date(2026, 1, 3))

    day1, day2 = result.daily_equity
    assert (day1.cash, day1.shares) == (D("91"), 1)  # pre-SELL portfolio preserved
    assert day1.equity == D("100")
    assert (day2.cash, day2.shares) == (D("101"), 0)  # post-SELL portfolio
    assert [point.date for point in result.daily_equity] == [bar.date for bar in bars]
    assert [point.close for point in result.daily_equity] == [bar.close for bar in bars]


def test_exactly_one_daily_point_per_bar_in_bar_order() -> None:
    result = run_demo()
    assert len(result.daily_equity) == len(DEMO_BARS)
    assert [point.date for point in result.daily_equity] == [bar.date for bar in DEMO_BARS]
    assert [point.close for point in result.daily_equity] == [bar.close for bar in DEMO_BARS]


# ---------------------------------------------------------------------------
# Event sequencing
# ---------------------------------------------------------------------------


def test_event_sequences_are_globally_contiguous() -> None:
    result = run_demo()
    sequences = [sequenced.event_sequence for sequenced in result.actions]
    assert sequences == list(range(1, len(result.actions) + 1))
    assert sequences[0] == 1
    assert len(result.actions) == len(result.event_equity)
    for sequenced, point in zip(result.actions, result.event_equity, strict=True):
        assert sequenced.event_sequence == point.event_sequence
        assert sequenced.action.event_date == point.date


def test_flat_segments_allocate_no_sequence() -> None:
    result = run_backtest(
        [close_bar(2, "10"), close_bar(3, "10"), close_bar(4, "9")], make_config()
    )
    assert [sequenced.event_sequence for sequenced in result.actions] == [1]
    assert isinstance(result.actions[0].action, TradeResult)


def test_skipped_trades_and_zone_events_receive_sequences() -> None:
    # SELL with zero shares is skipped but still sequenced.
    result = run_backtest([close_bar(2, "10"), close_bar(3, "11")], make_config())
    (skipped,) = trades_of(result)
    assert skipped.status is TradeStatus.SKIPPED
    assert result.actions[0].event_sequence == 1
    assert len(result.event_equity) == 1  # skipped trade still produces Event Equity

    zone_run = run_backtest(
        [close_bar(2, "15"), close_bar(3, "9")],
        make_config(baseline_override="10", initial_shares=2),
    )
    assert all(
        sequenced.event_sequence == index + 1 for index, sequenced in enumerate(zone_run.actions)
    )
    assert zone_events_of(zone_run)  # zone events participate in the same sequence


# ---------------------------------------------------------------------------
# Immediate Event Equity
# ---------------------------------------------------------------------------


def test_zone_events_snapshot_portfolio_before_later_trades_in_same_segment() -> None:
    # OUTSIDE_C -> RETURN_INSIDE_C -> EXIT_C -> three BUYs, all in one segment.
    result = run_backtest(
        [close_bar(2, "15"), close_bar(3, "9")],
        make_config(baseline_override="10", initial_cash="100", initial_shares=2),
    )
    kinds = [
        sequenced.action.event_type
        if isinstance(sequenced.action, ZoneEvent)
        else sequenced.action.side
        for sequenced in result.actions
    ]
    assert kinds == [
        ZoneEventType.RETURN_INSIDE_C_BOUNDARY,
        ZoneEventType.EXIT_C_ZONE,
        TradeSide.BUY,
        TradeSide.BUY,
        TradeSide.BUY,
    ]

    return_point, exit_point, buy1, buy2, buy3 = result.event_equity
    # Zone events snapshot the pre-BUY portfolio (cash 100, shares 2).
    assert (return_point.cash, return_point.shares) == (D("100"), 2)
    assert return_point.market_price == D("14")  # C upper boundary price
    assert return_point.equity == D("128")
    assert (exit_point.cash, exit_point.shares) == (D("100"), 2)
    assert exit_point.market_price == D("12")  # A upper boundary price
    assert exit_point.equity == D("124")
    # Later BUYs did not retroactively alter the earlier snapshots above.
    assert buy1.equity == D("122")  # 89 + 3 * 11
    assert buy2.equity == D("119")  # 79 + 4 * 10
    assert buy3.equity == D("115")  # 70 + 5 * 9

    # Transitions were applied exactly once each: final zone is IN_A.
    assert result.final_state.zone_state is ZoneState.IN_A
    assert len(zone_events_of(result)) == 2
    assert result.final_state.trade_anchor == D("9")


def test_executed_trade_event_equity_uses_canonical_grid_price() -> None:
    result = run_demo()
    for sequenced, point in zip(result.actions, result.event_equity, strict=True):
        action = sequenced.action
        assert isinstance(action, TradeResult)
        assert point.market_price == action.grid_price
        assert point.equity == action.equity_after


# ---------------------------------------------------------------------------
# Execution integration
# ---------------------------------------------------------------------------


def test_demo_buy_sell_progression_and_final_state() -> None:
    result = run_demo()
    trades = trades_of(result)
    assert [(t.side, t.grid_price, t.status) for t in trades] == [
        (TradeSide.BUY, D("9"), TradeStatus.EXECUTED),
        (TradeSide.BUY, D("8"), TradeStatus.EXECUTED),
        (TradeSide.SELL, D("9"), TradeStatus.EXECUTED),
        (TradeSide.SELL, D("10"), TradeStatus.EXECUTED),
    ]
    assert result.final_state.cash == D("102")
    assert result.final_state.shares == 0
    assert result.final_state.trade_anchor == D("10")
    assert result.final_state.market_cursor == D("10")
    assert result.final_state.zone_state is ZoneState.IN_A


def test_skip_does_not_stop_segment_or_update_anchor() -> None:
    # 10 -> 8 attempts BUY at 9 (unaffordable) then BUY at 8 (affordable).
    result = run_backtest([close_bar(2, "10"), close_bar(3, "8")], make_config(initial_cash="8.50"))
    first, second = trades_of(result)
    assert (first.grid_price, first.status) == (D("9"), TradeStatus.SKIPPED)
    assert first.skip_reason is SkipReason.INSUFFICIENT_CASH
    assert (second.grid_price, second.status) == (D("8"), TradeStatus.EXECUTED)
    assert result.final_state.trade_anchor == D("8")  # never the skipped 9
    assert result.final_state.cash == D("0.50")
    assert result.final_state.shares == 1


def test_skipped_sell_leaves_state_unchanged() -> None:
    result = run_backtest([close_bar(2, "10"), close_bar(3, "11")], make_config())
    (skipped,) = trades_of(result)
    assert skipped.status is TradeStatus.SKIPPED
    assert skipped.skip_reason is SkipReason.INSUFFICIENT_SHARES
    assert result.final_state.cash == D("100")
    assert result.final_state.shares == 0
    assert result.final_state.trade_anchor == D("10")  # unchanged by the skip
    assert result.final_state.market_cursor == D("11")  # cursor still advanced


# ---------------------------------------------------------------------------
# Zone integration
# ---------------------------------------------------------------------------


def test_zone_transitions_preserve_anchor_and_gate_trading() -> None:
    bars = [close_bar(2, "10"), close_bar(3, "13"), close_bar(4, "9")]
    result = run_backtest(bars, make_config(initial_cash="100", initial_shares=5))

    labels = [
        sequenced.action.event_type
        if isinstance(sequenced.action, ZoneEvent)
        else (sequenced.action.side, sequenced.action.grid_price)
        for sequenced in result.actions
    ]
    assert labels == [
        (TradeSide.SELL, D("11")),
        (TradeSide.SELL, D("12")),
        ZoneEventType.ENTER_C_ZONE,
        ZoneEventType.EXIT_C_ZONE,
        (TradeSide.BUY, D("11")),
        (TradeSide.BUY, D("10")),
        (TradeSide.BUY, D("9")),
    ]
    # Anchor was 12 when C was entered; still 12 when A resumed (preserved
    # through both transitions), so the first buy back is 11 < 12.
    assert result.daily_equity[1].zone_at_close is ZoneState.IN_C
    assert result.daily_equity[2].zone_at_close is ZoneState.IN_A
    assert result.metrics.zones.days_closed_in_a_zone == 2
    assert result.metrics.zones.days_closed_in_c_zone == 1
    assert result.metrics.zones.zone_event_counts[ZoneEventType.ENTER_C_ZONE] == 1
    assert result.metrics.zones.zone_event_counts[ZoneEventType.EXIT_C_ZONE] == 1
    assert result.final_state.zone_state is ZoneState.IN_A


# ---------------------------------------------------------------------------
# Metrics integration
# ---------------------------------------------------------------------------


def test_demo_metrics_come_from_daily_equity() -> None:
    result = run_demo()
    equities = [point.equity for point in result.daily_equity]
    assert equities == [D("100"), D("100"), D("99"), D("101"), D("102")]
    strategy = result.metrics.strategy
    assert strategy.initial_equity == D("100")
    assert strategy.final_equity == D("102")
    assert strategy.net_profit == D("2")
    assert strategy.total_return == D("0.02")
    assert strategy.maximum_drawdown == D("-0.01")  # 99/100 - 1, from daily equity

    costs = result.metrics.trade_costs
    assert costs.executed_trades == 4
    assert costs.skipped_trades == 0
    assert costs.buy_count == 2
    assert costs.sell_count == 2
    assert costs.total_commission == D("0")

    # Benchmark 2 bought 10 shares on day one; that purchase is not a strategy
    # trade and its costs are reported separately.
    purchase = result.benchmark2.day_one_purchase
    assert purchase is not None
    assert purchase.shares_purchased == 10
    assert result.metrics.benchmark2_day_one_commission == D("0")
    assert result.metrics.benchmark2_day_one_slippage_cost == D("0")

    first_return = result.metrics.first_return
    assert first_return.equity == D("102")
    assert first_return.days == 4

    assert result.metrics.benchmark1.final_equity == D("100")
    assert result.metrics.benchmark2.final_equity == D("100")  # 10 shares back at 10


def test_initial_equity_seeded_drawdown_is_preserved() -> None:
    # A day-one buy commission drags the first close equity below the initial
    # equity; the seed makes that an immediate drawdown, not a fresh peak.
    bars = [
        ohlcv_bar(2, "10", "10", "9", "9"),
        ohlcv_bar(3, "9", "9", "9", "9"),
    ]
    config = make_config(
        data_mode=DataMode.OHLCV,
        ohlc_path_mode=OHLCPathMode.AUTO,
        execution=execution_config(buy_commission=fixed_commission("1")),
    )
    result = run_backtest(bars, config)
    assert result.initial_equity == D("100")
    assert result.daily_equity[0].equity == D("99")  # 90 cash + 1 share * 9
    assert result.daily_equity[0].drawdown == D("-0.01")
    assert result.metrics.strategy.maximum_drawdown == D("-0.01")


def test_zero_strategy_equity_is_handled_safely() -> None:
    # Selling the only share with commission == notional leaves cash 0, shares 0.
    config = make_config(
        initial_cash="0",
        initial_shares=1,
        execution=execution_config(sell_commission=fixed_commission("11")),
    )
    result = run_backtest([close_bar(2, "10"), close_bar(3, "11")], config)
    (sell,) = trades_of(result)
    assert sell.status is TradeStatus.EXECUTED
    assert result.final_state.cash == D("0")
    assert result.final_state.shares == 0
    assert result.daily_equity[1].equity == D("0")
    assert result.daily_equity[1].drawdown == D("-1")
    assert result.metrics.strategy.total_return == D("-1")
    assert result.metrics.strategy.annualized_return is None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_repeated_runs_are_equal_and_leak_no_state() -> None:
    bars = list(DEMO_BARS)
    config = make_config()
    first = run_backtest(bars, config)
    second = run_backtest(bars, config)
    assert first == second
    assert second.daily_equity[0].cash == D("100")  # second run began fresh
    assert bars == DEMO_BARS
    assert config == make_config()


# ---------------------------------------------------------------------------
# Final-state consistency
# ---------------------------------------------------------------------------


def test_final_state_is_consistent_with_daily_equity_and_metrics() -> None:
    result = run_demo()
    final_daily = result.daily_equity[-1]
    assert result.final_state.market_cursor == DEMO_BARS[-1].close
    assert final_daily.equity == result.final_state.cash + result.final_state.shares * D("10")
    assert result.metrics.strategy.final_equity == final_daily.equity
    assert [sequenced.event_sequence for sequenced in result.actions] == [
        point.event_sequence for point in result.event_equity
    ]


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def test_public_imports_work_from_app_engine() -> None:
    import app.engine as engine_pkg

    for name in ("BacktestConfig", "FinalBacktestState", "BacktestResult", "run_backtest"):
        assert hasattr(engine_pkg, name), name
        assert name in engine_pkg.__all__


def test_prior_task_exports_remain_available() -> None:
    import app.engine as engine_pkg

    for name in (
        "build_grid_setup",
        "build_price_path",
        "plan_segment_actions",
        "execute_or_skip",
        "capture_daily_equity",
        "capture_event_equity",
        "compute_initial_equity",
        "build_benchmark1",
        "build_benchmark2",
        "compute_backtest_metrics",
        "validate_execution_config",
        "round_to_tick",
    ):
        assert callable(getattr(engine_pkg, name)), name


def test_backtest_modules_have_no_forbidden_dependencies() -> None:
    import app.engine.backtest
    import app.engine.backtest_models

    for module in (app.engine.backtest, app.engine.backtest_models):
        source = inspect.getsource(module).lower()
        for forbidden in (
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "app.importing",
            "numpy",
            "pandas",
            "celery",
            "redis",
            "optimization",
            "persistence",
        ):
            assert forbidden not in source, f"{module.__name__} contains {forbidden!r}"


def test_config_replacement_produces_new_frozen_config() -> None:
    config = make_config()
    changed = replace(config, initial_cash=D("55"))
    assert changed.initial_cash == D("55")
    assert config.initial_cash == D("100")
