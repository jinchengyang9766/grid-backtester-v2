"""Tests for the pure-engine metric layer (SPEC Section 21)."""

import inspect
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import (
    DataMode,
    SkipReason,
    TradeSide,
    TradeStatus,
    ValueMode,
    ZoneEventType,
    ZoneState,
)
from app.domain.models import Bar
from app.engine.benchmark_models import BenchmarkSeries
from app.engine.benchmarks import build_benchmark1, build_benchmark2
from app.engine.equity import capture_daily_equity
from app.engine.equity_models import (
    DailyEquityPoint,
    SequencedAction,
    ZeroInitialEquityError,
)
from app.engine.execution_models import (
    CommissionConfig,
    ExecutionConfig,
    PortfolioState,
    SlippageConfig,
    TradeResult,
)
from app.engine.grid_models import TickSizeConfig, ZoneBoundaries
from app.engine.metric_models import (
    EmptyEquitySeriesError,
    InvalidRiskFreeRateError,
    TradeDateNotFoundError,
)
from app.engine.metrics import (
    compute_annualized_return,
    compute_backtest_metrics,
    compute_equity_series_metrics,
    compute_first_return_to_initial_shares,
    compute_maximum_drawdown,
    compute_sharpe_ratio,
    compute_trade_cost_metrics,
    compute_zone_metrics,
)
from app.engine.segment_models import ZoneEvent

D = Decimal
ZERO_RF = D("0")

BOUNDS = ZoneBoundaries(
    baseline=D("10"), a_lower=D("9"), a_upper=D("11"), c_lower=D("8"), c_upper=D("12")
)
BAR_DATES = [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)]


def trade(
    *,
    sequence: int,
    day: int,
    side: TradeSide = TradeSide.BUY,
    status: TradeStatus = TradeStatus.EXECUTED,
    grid_price: str = "10.00",
    shares: int = 6,
    commission: str = "0.00",
    slippage_cost: str = "0.00",
    cash_after: str = "40.00",
    shares_after: int = 6,
) -> SequencedAction:
    executed = status is TradeStatus.EXECUTED
    return SequencedAction(
        event_sequence=sequence,
        action=TradeResult(
            event_date=date(2026, 1, day),
            side=side,
            grid_price=D(grid_price),
            execution_price=D(grid_price) if executed else None,
            shares=shares,
            notional=D(grid_price) * shares if executed else None,
            commission=D(commission) if executed else None,
            slippage_cost=D(slippage_cost) if executed else None,
            cash_after=D(cash_after),
            shares_after=shares_after,
            equity_after=D(cash_after) + shares_after * D(grid_price),
            status=status,
            skip_reason=None if executed else SkipReason.INSUFFICIENT_CASH,
        ),
    )


def zone_action(
    *,
    sequence: int,
    day: int = 3,
    event_type: ZoneEventType = ZoneEventType.ENTER_C_ZONE,
) -> SequencedAction:
    return SequencedAction(
        event_sequence=sequence,
        action=ZoneEvent(
            event_type=event_type,
            boundary_price=D("11.00"),
            event_date=date(2026, 1, day),
            old_zone=ZoneState.IN_A,
            new_zone=ZoneState.IN_C,
        ),
    )


def daily_point(*, day: int, equity: str, zone: ZoneState = ZoneState.IN_A) -> DailyEquityPoint:
    return DailyEquityPoint(
        date=date(2026, 1, day),
        close=D("10.00"),
        cash=D(equity),
        shares=0,
        equity=D(equity),
        drawdown=D("0"),
        zone_at_close=zone,
    )


def no_cost_config(lot_size: int = 2) -> ExecutionConfig:
    no_slip = SlippageConfig(mode=ValueMode.FIXED, value=D("0"))
    no_comm = CommissionConfig(
        rate_enabled=False,
        rate=D("0"),
        minimum_enabled=False,
        minimum=D("0"),
        fixed_enabled=False,
        fixed=D("0"),
    )
    return ExecutionConfig(
        lot_size=lot_size,
        trade_lots=1,
        buy_slippage=no_slip,
        sell_slippage=no_slip,
        buy_commission=no_comm,
        sell_commission=no_comm,
        tick_size=TickSizeConfig(enabled=False),
    )


# ---------------------------------------------------------------------------
# Annualized return
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("periods", [0, -1])
def test_annualized_return_nonpositive_periods_gives_none(periods: int) -> None:
    assert compute_annualized_return(D("0.10"), periods) is None


def test_annualized_return_total_wipeout_gives_none() -> None:
    assert compute_annualized_return(D("-1"), 5) is None


def test_annualized_return_positive() -> None:
    assert compute_annualized_return(D("0.10"), 126) == D("0.21")  # (1.1)^2 - 1


def test_annualized_return_negative_above_minus_one() -> None:
    assert compute_annualized_return(D("-0.19"), 126) == D("-0.3439")  # (0.81)^2 - 1


def test_annualized_return_252_periods_reproduces_total_return() -> None:
    assert compute_annualized_return(D("0.10"), 252) == D("0.10")


# ---------------------------------------------------------------------------
# Sharpe ratio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rate", ["-1", "-1.5"])
def test_sharpe_invalid_risk_free_rate_rejected(rate: str) -> None:
    with pytest.raises(InvalidRiskFreeRateError) as exc_info:
        compute_sharpe_ratio([D("100"), D("110"), D("100")], D(rate))
    assert exc_info.value.value == D(rate)


def test_sharpe_flat_equity_with_zero_rate_gives_zero() -> None:
    assert compute_sharpe_ratio([D("100"), D("100"), D("100")], ZERO_RF) == D("0")


def test_sharpe_nonzero_constant_excess_with_zero_variance_gives_none() -> None:
    # Flat equity, positive risk-free rate: every excess return equals -rf_daily.
    assert compute_sharpe_ratio([D("100"), D("100"), D("100")], D("0.03")) is None


@pytest.mark.parametrize("rate", ["0.03", "-0.5"])
def test_sharpe_valid_positive_and_negative_rates_produce_a_value(rate: str) -> None:
    result = compute_sharpe_ratio([D("100"), D("110"), D("100")], D(rate))
    assert isinstance(result, Decimal)


@pytest.mark.parametrize("equities", [["100"], ["100", "110"]])
def test_sharpe_fewer_than_two_returns_gives_none(equities: list[str]) -> None:
    assert compute_sharpe_ratio([D(value) for value in equities], ZERO_RF) is None


def test_sharpe_uses_sample_standard_deviation() -> None:
    # Returns 0 and 0.2: sample stdev sqrt(0.02), population stdev 0.1.
    result = compute_sharpe_ratio([D("100"), D("100"), D("120")], ZERO_RF)
    expected_sample = D("0.1") / D("0.02").sqrt() * D("252").sqrt()
    population_value = D("252").sqrt()  # (0.1 / 0.1) * sqrt(252)
    assert result == expected_sample
    assert result != population_value


def test_sharpe_zero_numerator_equity_is_allowed() -> None:
    # Denominators 100 and 50 are positive; the final 0 only feeds a -1 return.
    assert isinstance(compute_sharpe_ratio([D("100"), D("50"), D("0")], ZERO_RF), Decimal)


def test_sharpe_zero_previous_equity_gives_none_before_division() -> None:
    assert compute_sharpe_ratio([D("100"), D("0"), D("50")], ZERO_RF) is None


def test_sharpe_negative_previous_equity_defensively_gives_none() -> None:
    assert compute_sharpe_ratio([D("100"), D("-1"), D("50")], ZERO_RF) is None


def test_metrics_module_is_decimal_only() -> None:
    import app.engine.metrics

    source = inspect.getsource(app.engine.metrics)
    assert "float(" not in source
    assert "import math" not in source
    assert "statistics" not in source


# ---------------------------------------------------------------------------
# Maximum drawdown
# ---------------------------------------------------------------------------


def test_max_drawdown_flat_and_rising_series_give_zero() -> None:
    assert compute_maximum_drawdown([D("100"), D("100")], D("100")) == D("0")
    assert compute_maximum_drawdown([D("100"), D("110"), D("120")], D("100")) == D("0")


def test_max_drawdown_decline_is_exact() -> None:
    assert compute_maximum_drawdown([D("100"), D("80")], D("100")) == D("-0.2")


def test_max_drawdown_recovery_does_not_erase_history() -> None:
    assert compute_maximum_drawdown([D("100"), D("50"), D("120")], D("100")) == D("-0.5")


def test_max_drawdown_zero_equity_gives_minus_one() -> None:
    assert compute_maximum_drawdown([D("100"), D("0")], D("100")) == D("-1")


def test_max_drawdown_initial_equity_seeds_running_peak() -> None:
    # Without the seed the first point would define the peak and give 0.
    assert compute_maximum_drawdown([D("90"), D("95")], D("100")) == D("-0.1")


def test_max_drawdown_result_is_nonpositive() -> None:
    assert compute_maximum_drawdown([D("100"), D("150")], D("100")) <= 0


def test_max_drawdown_validation() -> None:
    with pytest.raises(EmptyEquitySeriesError):
        compute_maximum_drawdown([], D("100"))
    with pytest.raises(ZeroInitialEquityError):
        compute_maximum_drawdown([D("100")], D("0"))


# ---------------------------------------------------------------------------
# Equity-series metrics
# ---------------------------------------------------------------------------


def test_series_metrics_empty_series_rejected() -> None:
    with pytest.raises(EmptyEquitySeriesError):
        compute_equity_series_metrics([], initial_equity=D("100"), annual_risk_free_rate=ZERO_RF)


def test_series_metrics_zero_initial_equity_rejected() -> None:
    with pytest.raises(ZeroInitialEquityError):
        compute_equity_series_metrics(
            [D("100")], initial_equity=D("0"), annual_risk_free_rate=ZERO_RF
        )


def test_series_metrics_basic_values() -> None:
    metrics = compute_equity_series_metrics(
        [D("110")], initial_equity=D("100"), annual_risk_free_rate=ZERO_RF
    )
    assert metrics.initial_equity == D("100")
    assert metrics.final_equity == D("110")
    assert metrics.net_profit == D("10")
    assert metrics.total_return == D("0.1")
    assert metrics.annualized_return is None  # zero elapsed periods
    assert metrics.sharpe_ratio is None
    assert metrics.maximum_drawdown == D("0")


def test_series_metrics_zero_final_equity_gives_total_return_minus_one() -> None:
    metrics = compute_equity_series_metrics(
        [D("0")], initial_equity=D("100"), annual_risk_free_rate=ZERO_RF
    )
    assert metrics.total_return == D("-1")
    assert metrics.net_profit == D("-100")
    assert metrics.annualized_return is None
    assert metrics.maximum_drawdown == D("-1")


def test_series_metrics_wire_component_functions() -> None:
    equities = [D("100"), D("100"), D("120")]
    metrics = compute_equity_series_metrics(
        equities, initial_equity=D("100"), annual_risk_free_rate=ZERO_RF
    )
    assert metrics.total_return == D("0.2")
    assert metrics.annualized_return == compute_annualized_return(D("0.2"), 2)
    assert metrics.sharpe_ratio == compute_sharpe_ratio(equities, ZERO_RF)
    assert metrics.maximum_drawdown == compute_maximum_drawdown(equities, D("100"))


# ---------------------------------------------------------------------------
# Trade and cost metrics
# ---------------------------------------------------------------------------


def test_trade_costs_empty_input_all_zeros() -> None:
    metrics = compute_trade_cost_metrics([])
    assert metrics.total_commission == D("0")
    assert metrics.total_slippage_cost == D("0")
    assert (metrics.executed_trades, metrics.skipped_trades) == (0, 0)
    assert (metrics.buy_count, metrics.sell_count) == (0, 0)


def test_trade_costs_full_accounting() -> None:
    actions = [
        trade(sequence=1, day=2, side=TradeSide.BUY, commission="1.23", slippage_cost="0.45"),
        trade(sequence=2, day=3, side=TradeSide.SELL, commission="2.00", slippage_cost="0.10"),
        trade(sequence=3, day=3, side=TradeSide.BUY, status=TradeStatus.SKIPPED),
        trade(sequence=4, day=4, side=TradeSide.SELL, status=TradeStatus.SKIPPED),
        zone_action(sequence=5),
    ]
    metrics = compute_trade_cost_metrics(actions)
    assert metrics.total_commission == D("3.23")
    assert metrics.total_slippage_cost == D("0.55")
    assert metrics.executed_trades == 2
    assert metrics.skipped_trades == 2
    assert metrics.buy_count == 1  # skipped BUY/SELL never count
    assert metrics.sell_count == 1
    assert compute_trade_cost_metrics(list(reversed(actions))) == metrics


# ---------------------------------------------------------------------------
# Zone metrics
# ---------------------------------------------------------------------------


def test_zone_metrics_counts_days_and_events() -> None:
    daily = [
        daily_point(day=2, equity="100", zone=ZoneState.IN_A),
        daily_point(day=3, equity="100", zone=ZoneState.IN_A),
        daily_point(day=4, equity="100", zone=ZoneState.IN_C),
        daily_point(day=5, equity="100", zone=ZoneState.OUTSIDE_C),
    ]
    actions = [
        zone_action(sequence=1, event_type=ZoneEventType.ENTER_C_ZONE),
        zone_action(sequence=2, event_type=ZoneEventType.EXIT_C_ZONE),
        zone_action(sequence=3, event_type=ZoneEventType.ENTER_C_ZONE),
        zone_action(sequence=4, event_type=ZoneEventType.OUTSIDE_C_BOUNDARY),
        trade(sequence=5, day=2),  # trades never count as zone events
    ]
    metrics = compute_zone_metrics(daily, actions)
    assert metrics.days_closed_in_a_zone == 2
    assert metrics.days_closed_in_c_zone == 1
    assert metrics.days_closed_outside_c == 1
    assert metrics.zone_event_counts == {
        ZoneEventType.ENTER_C_ZONE: 2,
        ZoneEventType.EXIT_C_ZONE: 1,
        ZoneEventType.OUTSIDE_C_BOUNDARY: 1,
        ZoneEventType.RETURN_INSIDE_C_BOUNDARY: 0,
    }


def test_zone_metrics_empty_inputs_keep_all_event_keys() -> None:
    metrics = compute_zone_metrics([], [])
    assert metrics.days_closed_in_a_zone == 0
    assert metrics.days_closed_in_c_zone == 0
    assert metrics.days_closed_outside_c == 0
    assert metrics.zone_event_counts == dict.fromkeys(ZoneEventType, 0)


# ---------------------------------------------------------------------------
# First return to initial share position
# ---------------------------------------------------------------------------


def assert_none_pair(actions: list[SequencedAction], initial_shares: int = 0) -> None:
    result = compute_first_return_to_initial_shares(
        actions, initial_shares=initial_shares, bar_dates=BAR_DATES
    )
    assert result.equity is None
    assert result.days is None


def test_first_return_no_trades_gives_none_pair() -> None:
    assert_none_pair([])
    assert_none_pair([zone_action(sequence=1)])


def test_first_return_only_skipped_trades_gives_none_pair() -> None:
    assert_none_pair([trade(sequence=1, day=2, status=TradeStatus.SKIPPED, shares_after=0)])


def test_first_return_never_deviating_executed_trades_give_none_pair() -> None:
    assert_none_pair([trade(sequence=1, day=2, shares_after=0)], initial_shares=0)


def test_first_return_first_deviation_is_not_a_return() -> None:
    assert_none_pair([trade(sequence=1, day=2, shares_after=6)], initial_shares=0)


def test_first_return_detects_later_executed_return() -> None:
    actions = [
        trade(sequence=1, day=2, side=TradeSide.BUY, shares_after=6, cash_after="40.00"),
        trade(
            sequence=4,
            day=4,
            side=TradeSide.SELL,
            shares_after=0,
            cash_after="100.00",
            grid_price="10.00",
        ),
    ]
    result = compute_first_return_to_initial_shares(actions, initial_shares=0, bar_dates=BAR_DATES)
    assert result.equity == D("100.00")  # the qualifying trade's equity_after
    assert result.days == 2  # zero-based index of 2026-01-04


def test_first_return_skipped_apparent_return_is_ignored() -> None:
    assert_none_pair(
        [
            trade(sequence=1, day=2, shares_after=6),
            trade(sequence=2, day=3, status=TradeStatus.SKIPPED, shares_after=0),
        ]
    )


def test_first_return_uses_sequence_order_not_input_order_and_keeps_input() -> None:
    late_return = trade(sequence=4, day=4, side=TradeSide.SELL, shares_after=0)
    deviation = trade(sequence=1, day=2, shares_after=6)
    actions = [late_return, zone_action(sequence=2), deviation]
    snapshot = list(actions)
    result = compute_first_return_to_initial_shares(
        actions, initial_shares=0, bar_dates=[BAR_DATES[2], BAR_DATES[0], BAR_DATES[1]]
    )
    assert result.days == 2  # bar_dates are sorted before indexing
    assert result.equity is not None
    assert actions == snapshot


def test_first_return_missing_trade_date_raises() -> None:
    actions = [
        trade(sequence=1, day=2, shares_after=6),
        trade(sequence=2, day=9, side=TradeSide.SELL, shares_after=0),
    ]
    with pytest.raises(TradeDateNotFoundError) as exc_info:
        compute_first_return_to_initial_shares(actions, initial_shares=0, bar_dates=BAR_DATES)
    assert exc_info.value.event_date == date(2026, 1, 9)


def test_first_return_deviates_but_never_returns_gives_none_pair() -> None:
    assert_none_pair(
        [trade(sequence=1, day=2, shares_after=6), trade(sequence=2, day=3, shares_after=12)]
    )


def test_first_return_with_positive_initial_shares() -> None:
    actions = [
        trade(sequence=1, day=2, side=TradeSide.SELL, shares_after=0, cash_after="100.00"),
        trade(sequence=2, day=3, side=TradeSide.BUY, shares_after=6, cash_after="40.00"),
    ]
    result = compute_first_return_to_initial_shares(actions, initial_shares=6, bar_dates=BAR_DATES)
    assert result.equity == D("40.00") + 6 * D("10.00")
    assert result.days == 1


# ---------------------------------------------------------------------------
# Complete aggregation
# ---------------------------------------------------------------------------


def build_strategy_daily_points() -> list[DailyEquityPoint]:
    captures = [
        (Bar(date=BAR_DATES[0], close=D("10.00")), PortfolioState(cash=D("100.00"), shares=0)),
        (Bar(date=BAR_DATES[1], close=D("11.50")), PortfolioState(cash=D("40.00"), shares=6)),
        (Bar(date=BAR_DATES[2], close=D("12.50")), PortfolioState(cash=D("100.00"), shares=0)),
    ]
    points: list[DailyEquityPoint] = []
    peak = D("100.00")  # the validated initial equity seeds the running peak
    for the_bar, portfolio in captures:
        point, peak = capture_daily_equity(
            bar=the_bar, portfolio=portfolio, boundaries=BOUNDS, running_peak_before=peak
        )
        points.append(point)
    return points


def build_strategy_actions() -> list[SequencedAction]:
    return [
        trade(sequence=1, day=2, side=TradeSide.BUY, shares_after=6, cash_after="40.00"),
        trade(sequence=2, day=3, status=TradeStatus.SKIPPED, grid_price="11.00"),
        zone_action(sequence=3, day=3),
        trade(sequence=4, day=4, side=TradeSide.SELL, shares_after=0, cash_after="100.00"),
    ]


def build_full_metrics_inputs() -> tuple[
    list[DailyEquityPoint], list[SequencedAction], BenchmarkSeries, BenchmarkSeries
]:
    bars = [
        Bar(date=BAR_DATES[0], close=D("10.00")),
        Bar(date=BAR_DATES[1], close=D("11.50")),
        Bar(date=BAR_DATES[2], close=D("12.50")),
    ]
    benchmark1 = build_benchmark1(bars, initial_cash=D("100.00"), initial_shares=0)
    benchmark2 = build_benchmark2(
        bars,
        DataMode.CLOSE_ONLY,
        initial_cash=D("100.00"),
        initial_shares=0,
        config=no_cost_config(),
    )
    return build_strategy_daily_points(), build_strategy_actions(), benchmark1, benchmark2


def test_backtest_metrics_full_aggregation() -> None:
    daily, actions, benchmark1, benchmark2 = build_full_metrics_inputs()
    metrics = compute_backtest_metrics(
        initial_equity=D("100.00"),
        daily_equity=daily,
        actions=actions,
        bar_dates=BAR_DATES,
        benchmark1=benchmark1,
        benchmark2=benchmark2,
        annual_risk_free_rate=ZERO_RF,
    )

    assert metrics.strategy.final_equity == D("100.00")
    assert metrics.strategy.net_profit == D("0.00")
    assert metrics.strategy.total_return == D("0")
    assert metrics.strategy.annualized_return == D("0")
    assert metrics.strategy.maximum_drawdown == D("100.00") / D("109.00") - 1
    assert metrics.strategy.sharpe_ratio is not None

    # Every series is compared from the same full-run initial equity.
    assert metrics.strategy.initial_equity == D("100.00")
    assert metrics.benchmark1.initial_equity == D("100.00")
    assert metrics.benchmark2.initial_equity == D("100.00")

    assert metrics.benchmark1.final_equity == D("100.00")
    assert metrics.benchmark1.total_return == D("0")
    assert metrics.benchmark1.sharpe_ratio == D("0")
    assert metrics.benchmark1.maximum_drawdown == D("0")

    assert metrics.benchmark2.final_equity == D("125.00")
    assert metrics.benchmark2.total_return == D("0.25")
    assert metrics.benchmark2.maximum_drawdown == D("0")

    # Strategy costs stay separate from Benchmark 2's one-time purchase costs.
    assert metrics.trade_costs.executed_trades == 2
    assert metrics.trade_costs.skipped_trades == 1
    assert metrics.trade_costs.buy_count == 1
    assert metrics.trade_costs.sell_count == 1
    assert metrics.benchmark2_day_one_commission == D("0")
    assert metrics.benchmark2_day_one_slippage_cost == D("0")

    assert metrics.zones.days_closed_in_a_zone == 1
    assert metrics.zones.days_closed_in_c_zone == 1
    assert metrics.zones.days_closed_outside_c == 1
    assert metrics.zones.zone_event_counts[ZoneEventType.ENTER_C_ZONE] == 1

    assert metrics.first_return.equity == D("100.00")
    assert metrics.first_return.days == 2

    with pytest.raises(FrozenInstanceError):
        metrics.strategy = metrics.benchmark1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        metrics.strategy.final_equity = D("0")  # type: ignore[misc]


def test_backtest_metrics_requires_benchmark2_purchase() -> None:
    daily, actions, benchmark1, _ = build_full_metrics_inputs()
    with pytest.raises(ValueError, match="day-one purchase"):
        compute_backtest_metrics(
            initial_equity=D("100.00"),
            daily_equity=daily,
            actions=actions,
            bar_dates=BAR_DATES,
            benchmark1=benchmark1,
            benchmark2=benchmark1,  # benchmark1 carries no day-one purchase
            annual_risk_free_rate=ZERO_RF,
        )


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def test_public_imports_work_from_app_engine() -> None:
    import app.engine as engine_pkg

    for name in (
        "DailyEquityPoint",
        "EventEquityPoint",
        "SequencedAction",
        "EquitySeriesMetrics",
        "TradeCostMetrics",
        "ZoneMetrics",
        "FirstReturnMetrics",
        "BacktestMetrics",
        "ZeroInitialEquityError",
        "InvalidRiskFreeRateError",
        "EmptyEquitySeriesError",
        "NonPositiveRunningPeakError",
        "TradeDateNotFoundError",
        "InvalidEventSequenceError",
        "compute_initial_equity",
        "capture_daily_equity",
        "capture_event_equity",
        "compute_annualized_return",
        "compute_sharpe_ratio",
        "compute_maximum_drawdown",
        "compute_equity_series_metrics",
        "compute_trade_cost_metrics",
        "compute_zone_metrics",
        "compute_first_return_to_initial_shares",
        "compute_backtest_metrics",
    ):
        assert hasattr(engine_pkg, name), name
        assert name in engine_pkg.__all__


def test_prior_task_exports_remain_available() -> None:
    import app.engine as engine_pkg

    for name in (
        "build_grid_setup",
        "build_price_path",
        "plan_segment_actions",
        "execute_or_skip",
        "materialize_segment_actions",
        "validate_execution_config",
        "compute_commission",
        "compute_execution_price",
        "round_to_tick",
        "build_benchmark1",
        "build_benchmark2",
        "compute_benchmark2_day_one_purchase",
        "select_benchmark2_reference_price",
    ):
        assert callable(getattr(engine_pkg, name)), name


def test_equity_and_metric_modules_have_no_forbidden_dependencies() -> None:
    import app.engine.equity
    import app.engine.equity_models
    import app.engine.metric_models
    import app.engine.metrics

    modules = (
        app.engine.equity,
        app.engine.equity_models,
        app.engine.metrics,
        app.engine.metric_models,
    )
    for module in modules:
        source = inspect.getsource(module).lower()
        for forbidden in (
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "numpy",
            "pandas",
            "app.importing",
            "app.db",
            "optimization",
        ):
            assert forbidden not in source, f"{module.__name__} contains {forbidden!r}"


def test_no_backtest_loop_or_database_event_model_introduced() -> None:
    import app.engine as engine_pkg

    assert not hasattr(engine_pkg, "run_backtest")
    assert not hasattr(engine_pkg, "BacktestEvent")
    for module_name in ("app.engine.equity", "app.engine.metrics"):
        module = __import__(module_name, fromlist=["_"])
        source = inspect.getsource(module)
        assert "build_price_path" not in source
        assert "plan_segment_actions" not in source
        assert "execute_or_skip" not in source
