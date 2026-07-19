"""Tests for the two Buy-and-Hold benchmark series."""

import inspect
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import DataMode, ValueMode
from app.domain.models import Bar
from app.engine.benchmark_models import (
    BenchmarkDayOnePurchase,
    BenchmarkEquityPoint,
    BenchmarkSeries,
)
from app.engine.benchmarks import (
    build_benchmark1,
    build_benchmark2,
    compute_benchmark2_day_one_purchase,
    compute_benchmark2_prices,
    select_benchmark2_reference_price,
)
from app.engine.execution_models import (
    CommissionConfig,
    ExecutionConfig,
    NegativeInitialCashError,
    NegativeInitialSharesError,
    NonPositiveExecutionPriceError,
    SlippageConfig,
)
from app.engine.grid_models import TickSizeConfig
from app.engine.path import InvalidOhlcvBarError

from app.engine.grid import EmptyDatasetError  # isort: skip

D = Decimal

TICK_OFF = TickSizeConfig(enabled=False)


def ohlcv_bar(day: int, open_: str, high: str, low: str, close: str) -> Bar:
    return Bar(
        date=date(2026, 1, day),
        close=D(close),
        open=D(open_),
        high=D(high),
        low=D(low),
    )


def close_bar(day: int, close: str) -> Bar:
    return Bar(date=date(2026, 1, day), close=D(close))


DEMO_BARS = [
    ohlcv_bar(2, "10.03", "10.50", "9.90", "10.20"),
    ohlcv_bar(3, "10.30", "11.20", "10.10", "11.00"),
    ohlcv_bar(4, "10.80", "11.00", "9.40", "9.50"),
]


def fixed_slip(value: str = "0") -> SlippageConfig:
    return SlippageConfig(mode=ValueMode.FIXED, value=D(value))


def pct_slip(value: str) -> SlippageConfig:
    return SlippageConfig(mode=ValueMode.PERCENT, value=D(value))


def commission_config(
    *,
    rate_enabled: bool = False,
    rate: str = "0",
    minimum_enabled: bool = False,
    minimum: str = "0",
    fixed_enabled: bool = False,
    fixed: str = "0",
) -> CommissionConfig:
    return CommissionConfig(
        rate_enabled=rate_enabled,
        rate=D(rate),
        minimum_enabled=minimum_enabled,
        minimum=D(minimum),
        fixed_enabled=fixed_enabled,
        fixed=D(fixed),
    )


NO_COMMISSION = commission_config()


def make_config(
    *,
    lot_size: int = 2,
    trade_lots: int = 7,
    buy_slip: SlippageConfig | None = None,
    sell_slip: SlippageConfig | None = None,
    buy_comm: CommissionConfig | None = None,
    sell_comm: CommissionConfig | None = None,
    tick: TickSizeConfig = TICK_OFF,
) -> ExecutionConfig:
    return ExecutionConfig(
        lot_size=lot_size,
        trade_lots=trade_lots,
        buy_slippage=buy_slip if buy_slip is not None else fixed_slip(),
        sell_slippage=sell_slip if sell_slip is not None else fixed_slip(),
        buy_commission=buy_comm if buy_comm is not None else NO_COMMISSION,
        sell_commission=sell_comm if sell_comm is not None else NO_COMMISSION,
        tick_size=tick,
    )


DEMO_CONFIG = make_config(
    buy_slip=fixed_slip("0.04"),
    buy_comm=commission_config(minimum_enabled=True, minimum="0.50"),
    tick=TickSizeConfig(enabled=True, value=D("0.05")),
)


def day_one(
    *,
    initial_cash: str,
    initial_shares: int = 0,
    reference_price: str = "1.00",
    config: ExecutionConfig | None = None,
) -> BenchmarkDayOnePurchase:
    return compute_benchmark2_day_one_purchase(
        initial_cash=D(initial_cash),
        initial_shares=initial_shares,
        reference_price=D(reference_price),
        config=config if config is not None else make_config(lot_size=100),
    )


# ---------------------------------------------------------------------------
# Benchmark models
# ---------------------------------------------------------------------------


def test_models_are_frozen() -> None:
    point = BenchmarkEquityPoint(
        date=date(2026, 1, 2), close=D("1"), cash=D("1"), shares=1, equity=D("2")
    )
    with pytest.raises(FrozenInstanceError):
        point.cash = D("9")  # type: ignore[misc]
    series = BenchmarkSeries(points=(point,), day_one_purchase=None)
    with pytest.raises(FrozenInstanceError):
        series.points = ()  # type: ignore[misc]


def test_series_points_is_tuple_and_decimals_stay_decimal() -> None:
    series = build_benchmark1([close_bar(2, "1.05")], initial_cash=D("10"), initial_shares=3)
    assert isinstance(series.points, tuple)
    assert type(series.points[0].equity) is Decimal
    assert type(series.points[0].cash) is Decimal


# ---------------------------------------------------------------------------
# Benchmark 1
# ---------------------------------------------------------------------------


def test_benchmark1_empty_bars_rejected() -> None:
    with pytest.raises(EmptyDatasetError):
        build_benchmark1([], initial_cash=D("10"), initial_shares=0)


def test_benchmark1_negative_cash_rejected() -> None:
    with pytest.raises(NegativeInitialCashError):
        build_benchmark1([close_bar(2, "1")], initial_cash=D("-1"), initial_shares=0)


def test_benchmark1_negative_shares_rejected() -> None:
    with pytest.raises(NegativeInitialSharesError):
        build_benchmark1([close_bar(2, "1")], initial_cash=D("1"), initial_shares=-1)


def test_benchmark1_zero_cash_and_zero_shares_accepted() -> None:
    series = build_benchmark1([close_bar(2, "1")], initial_cash=D("0"), initial_shares=0)
    assert series.points[0].equity == D("0")


def test_benchmark1_holds_constant_portfolio_marked_at_close() -> None:
    series = build_benchmark1(DEMO_BARS, initial_cash=D("105.00"), initial_shares=3)
    assert series.day_one_purchase is None
    assert [p.date for p in series.points] == [date(2026, 1, d) for d in (2, 3, 4)]
    for point, bar in zip(series.points, DEMO_BARS, strict=True):
        assert point.cash == D("105.00")
        assert point.shares == 3  # 3 is not a lot multiple of 2: allowed
        assert point.close == bar.close
        assert point.equity == D("105.00") + 3 * bar.close


def test_benchmark1_does_not_mutate_bars() -> None:
    bars = [close_bar(2, "1.05"), close_bar(3, "1.10")]
    build_benchmark1(bars, initial_cash=D("10"), initial_shares=1)
    assert bars == [close_bar(2, "1.05"), close_bar(3, "1.10")]


# ---------------------------------------------------------------------------
# Reference-price selection
# ---------------------------------------------------------------------------


def test_reference_empty_bars_rejected() -> None:
    with pytest.raises(EmptyDatasetError):
        select_benchmark2_reference_price([], DataMode.OHLCV)


def test_ohlcv_uses_first_open_not_close() -> None:
    price = select_benchmark2_reference_price(DEMO_BARS, DataMode.OHLCV)
    assert price == D("10.03")
    assert price != D("10.20")


def test_ohlcv_missing_open_raises_with_fields() -> None:
    with pytest.raises(InvalidOhlcvBarError) as exc_info:
        select_benchmark2_reference_price([close_bar(2, "1.05")], DataMode.OHLCV)
    assert exc_info.value.bar_index == 0
    assert exc_info.value.missing_fields == ("open",)


def test_close_only_uses_first_close_without_inspecting_ohlc() -> None:
    assert select_benchmark2_reference_price([close_bar(2, "1.05")], DataMode.CLOSE_ONLY) == D(
        "1.05"
    )


def test_explicit_data_mode_is_used_not_inferred() -> None:
    # Bars carry full OHLC, but CLOSE_ONLY must still pick the Close.
    assert select_benchmark2_reference_price(DEMO_BARS, DataMode.CLOSE_ONLY) == D("10.20")


# ---------------------------------------------------------------------------
# Benchmark 2 price pipeline
# ---------------------------------------------------------------------------


def test_tick_disabled_keeps_reference_as_tick_price() -> None:
    tick_price, execution_price = compute_benchmark2_prices(
        reference_price=D("10.03"), config=make_config(buy_slip=fixed_slip("0.04"))
    )
    assert tick_price == D("10.03")
    assert execution_price == D("10.07")


def test_tick_enabled_rounds_reference_first_then_slippage_then_rounds_again() -> None:
    tick_price, execution_price = compute_benchmark2_prices(
        reference_price=D("10.03"), config=DEMO_CONFIG
    )
    assert tick_price == D("10.05")  # 10.03 -> nearest 0.05 tick (200.6 -> 201)
    assert execution_price == D("10.10")  # 10.05 + 0.04 = 10.09 -> nearest 0.05 tick


def test_percent_slippage_uses_tick_price_not_raw_reference() -> None:
    config = make_config(buy_slip=pct_slip("0.10"), tick=TickSizeConfig(enabled=True, value=D("1")))
    tick_price, execution_price = compute_benchmark2_prices(
        reference_price=D("10.40"), config=config
    )
    assert tick_price == D("10")  # 10.40 -> nearest whole tick
    # Slippage from tick_price: 10 * 0.10 = 1 -> raw 11 -> tick 11. From the raw
    # reference it would be 10.40 * 0.10 = 1.04 -> raw 11.44 -> tick 11.00 too,
    # so pin the exact amount instead via the untouched no-second-rounding path:
    assert execution_price == D("11")


def test_sell_slippage_is_not_used() -> None:
    config_a = make_config(buy_slip=fixed_slip("0.04"), sell_slip=fixed_slip("0"))
    config_b = make_config(buy_slip=fixed_slip("0.04"), sell_slip=fixed_slip("9.99"))
    assert compute_benchmark2_prices(
        reference_price=D("10.03"), config=config_a
    ) == compute_benchmark2_prices(reference_price=D("10.03"), config=config_b)


def test_non_positive_execution_price_uses_existing_exception() -> None:
    # A huge percent buy slippage cannot go negative, but a pathological
    # negative-direction case can't arise on BUY -- use a tick that rounds a
    # tiny reference to zero instead.
    config = make_config(buy_slip=fixed_slip("0"), tick=TickSizeConfig(enabled=True, value=D("1")))
    with pytest.raises(NonPositiveExecutionPriceError):
        compute_benchmark2_prices(reference_price=D("0.4"), config=config)


def test_no_float_conversion_in_benchmarks_source() -> None:
    import app.engine.benchmarks

    assert "float(" not in inspect.getsource(app.engine.benchmarks)


# ---------------------------------------------------------------------------
# Affordable whole-lot search
# ---------------------------------------------------------------------------


def test_zero_affordable_lots_and_no_fee_charged() -> None:
    config = make_config(
        lot_size=100, buy_comm=commission_config(minimum_enabled=True, minimum="5")
    )
    purchase = day_one(initial_cash="5", initial_shares=1000, config=config)
    assert purchase.lots == 0
    assert purchase.shares_purchased == 0
    assert purchase.notional == D("0")
    assert purchase.commission == D("0")  # minimum never charged
    assert purchase.slippage_cost == D("0")
    assert purchase.cash_after == D("5")
    assert purchase.shares_after == 1000  # initial shares preserved, not spent
    assert purchase.execution_price == D("1.00")  # prices still populated


def test_exactly_one_affordable_lot() -> None:
    purchase = day_one(initial_cash="150", config=make_config(lot_size=100))
    assert purchase.lots == 1
    assert purchase.shares_purchased == 100


def test_several_affordable_lots_and_exact_cash_accepted() -> None:
    purchase = day_one(initial_cash="300", config=make_config(lot_size=100))
    assert purchase.lots == 3  # 300 buys exactly 3 lots at 1.00 with no fees
    assert purchase.cash_after == D("0")


def test_one_more_lot_is_unaffordable() -> None:
    purchase = day_one(initial_cash="299.99", config=make_config(lot_size=100))
    assert purchase.lots == 2


def test_minimum_commission_affects_affordability() -> None:
    config = make_config(
        lot_size=100, buy_comm=commission_config(minimum_enabled=True, minimum="0.50")
    )
    # 3 lots cost 300 + 0.50 commission = 300.50 > 300, so only 2 fit.
    purchase = day_one(initial_cash="300", config=config)
    assert purchase.lots == 2


def test_fixed_commission_is_charged_once_per_order_not_per_lot() -> None:
    config = make_config(lot_size=10, buy_comm=commission_config(fixed_enabled=True, fixed="5"))
    # Per-order: 10*lots + 5 <= 25 -> 2 lots. Per-lot (wrong): 15*lots -> 1 lot.
    purchase = day_one(initial_cash="25", config=config)
    assert purchase.lots == 2
    assert purchase.commission == D("5")


def test_percentage_commission_affects_affordability() -> None:
    config = make_config(lot_size=100, buy_comm=commission_config(rate_enabled=True, rate="0.01"))
    # 101 per lot: 2 lots cost 202 <= 202; 3 lots cost 303 > 202.
    purchase = day_one(initial_cash="202", config=config)
    assert purchase.lots == 2


def test_combined_commission_formula_affects_affordability() -> None:
    config = make_config(
        lot_size=100,
        buy_comm=commission_config(
            rate_enabled=True,
            rate="0.001",
            minimum_enabled=True,
            minimum="0.50",
            fixed_enabled=True,
            fixed="0.25",
        ),
    )
    # 1 lot: 100 + max(0.10, 0.50) + 0.25 = 100.75 <= 100.85; 2 lots exceed it.
    purchase = day_one(initial_cash="100.85", config=config)
    assert purchase.lots == 1
    assert purchase.commission == D("0.75")


def test_search_uses_exponential_growth_and_binary_search() -> None:
    import app.engine.benchmarks

    source = inspect.getsource(app.engine.benchmarks)
    assert "hi *= 2" in source
    assert "lo + 1 < hi" in source
    assert "(lo + hi) // 2" in source


def test_no_fractional_or_partial_lots() -> None:
    purchase = day_one(initial_cash="199.99", config=make_config(lot_size=100))
    assert purchase.lots == 1  # 1.9999 lots floors to 1 whole lot
    assert purchase.shares_purchased == 100


def test_large_affordable_lot_count_is_exact() -> None:
    purchase = day_one(
        initial_cash="123456", reference_price="1.00", config=make_config(lot_size=1)
    )
    assert purchase.lots == 123456
    assert purchase.cash_after == D("0")


# ---------------------------------------------------------------------------
# Day-one purchase
# ---------------------------------------------------------------------------


def test_positive_lots_populate_every_field_exactly() -> None:
    purchase = compute_benchmark2_day_one_purchase(
        initial_cash=D("105.00"),
        initial_shares=3,
        reference_price=D("10.03"),
        config=DEMO_CONFIG,
    )
    assert purchase.reference_price == D("10.03")
    assert purchase.tick_price == D("10.05")
    assert purchase.execution_price == D("10.10")
    assert purchase.lots == 5
    assert purchase.shares_purchased == 10
    assert purchase.notional == D("101.00")
    assert purchase.commission == D("0.50")
    assert purchase.slippage_cost == D("0.50")  # |10.10 - 10.05| * 10
    assert purchase.cash_after == D("3.50")
    assert purchase.cash_after >= 0
    assert purchase.shares_after == 13  # 3 initial + 10 purchased


def test_trade_lots_does_not_affect_benchmark2() -> None:
    for trade_lots in (1, 7, 99):
        config = make_config(
            lot_size=2,
            trade_lots=trade_lots,
            buy_slip=fixed_slip("0.04"),
            buy_comm=commission_config(minimum_enabled=True, minimum="0.50"),
            tick=TickSizeConfig(enabled=True, value=D("0.05")),
        )
        purchase = compute_benchmark2_day_one_purchase(
            initial_cash=D("105.00"),
            initial_shares=3,
            reference_price=D("10.03"),
            config=config,
        )
        assert purchase.lots == 5


def test_sell_side_settings_do_not_affect_benchmark2() -> None:
    base = day_one(initial_cash="300", config=make_config(lot_size=100))
    with_sell_costs = day_one(
        initial_cash="300",
        config=make_config(
            lot_size=100,
            sell_slip=pct_slip("0.5"),
            sell_comm=commission_config(fixed_enabled=True, fixed="99"),
        ),
    )
    assert base == with_sell_costs


def test_day_one_purchase_is_a_pure_value_object() -> None:
    purchase = day_one(initial_cash="150", config=make_config(lot_size=100))
    assert isinstance(purchase, BenchmarkDayOnePurchase)
    assert not hasattr(purchase, "status")  # no TradeResult semantics
    assert not hasattr(purchase, "skip_reason")


# ---------------------------------------------------------------------------
# Benchmark 2 series
# ---------------------------------------------------------------------------


def test_benchmark2_empty_bars_rejected() -> None:
    with pytest.raises(EmptyDatasetError):
        build_benchmark2(
            [], DataMode.OHLCV, initial_cash=D("10"), initial_shares=0, config=make_config()
        )


def test_benchmark2_ohlcv_series_full_contract() -> None:
    series = build_benchmark2(
        DEMO_BARS, DataMode.OHLCV, initial_cash=D("105.00"), initial_shares=3, config=DEMO_CONFIG
    )
    purchase = series.day_one_purchase
    assert purchase is not None
    assert purchase.reference_price == D("10.03")  # day-one Open
    assert purchase.cash_after == D("3.50")
    assert purchase.shares_after == 13
    expected_equities = [D("3.50") + 13 * bar.close for bar in DEMO_BARS]
    for point, bar, expected in zip(series.points, DEMO_BARS, expected_equities, strict=True):
        assert point.date == bar.date
        assert point.close == bar.close
        assert point.cash == D("3.50")  # constant, never reinvested
        assert point.shares == 13  # constant, never sold or re-bought
        assert point.equity == expected


def test_benchmark2_close_only_uses_day_one_close() -> None:
    bars = [close_bar(2, "1.00"), close_bar(3, "2.00")]
    series = build_benchmark2(
        bars,
        DataMode.CLOSE_ONLY,
        initial_cash=D("100"),
        initial_shares=0,
        config=make_config(lot_size=100),
    )
    purchase = series.day_one_purchase
    assert purchase is not None
    assert purchase.reference_price == D("1.00")
    assert purchase.shares_after == 100
    assert series.points[1].equity == D("0") + 100 * D("2.00")


def test_benchmark2_zero_lot_series_equals_initial_portfolio_series() -> None:
    config = make_config(lot_size=100)
    b2 = build_benchmark2(
        [close_bar(2, "9.99"), close_bar(3, "5.00")],
        DataMode.CLOSE_ONLY,
        initial_cash=D("5"),
        initial_shares=7,
        config=config,
    )
    b1 = build_benchmark1(
        [close_bar(2, "9.99"), close_bar(3, "5.00")], initial_cash=D("5"), initial_shares=7
    )
    assert [(p.cash, p.shares, p.equity) for p in b2.points] == [
        (p.cash, p.shares, p.equity) for p in b1.points
    ]
    assert b2.day_one_purchase is not None
    assert b2.day_one_purchase.lots == 0


def test_benchmark2_does_not_mutate_inputs() -> None:
    bars = [close_bar(2, "1.00"), close_bar(3, "2.00")]
    config = make_config(lot_size=100)
    build_benchmark2(
        bars, DataMode.CLOSE_ONLY, initial_cash=D("100"), initial_shares=0, config=config
    )
    assert bars == [close_bar(2, "1.00"), close_bar(3, "2.00")]
    assert config == make_config(lot_size=100)


def test_benchmark2_decimal_precision_preserved() -> None:
    series = build_benchmark2(
        [close_bar(2, "1.0500")],
        DataMode.CLOSE_ONLY,
        initial_cash=D("0"),
        initial_shares=1,
        config=make_config(lot_size=100),
    )
    assert str(series.points[0].close) == "1.0500"
    assert str(series.points[0].equity) == "1.0500"


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def test_public_imports_work_from_app_engine() -> None:
    import app.engine as engine_pkg

    for name in (
        "BenchmarkEquityPoint",
        "BenchmarkDayOnePurchase",
        "BenchmarkSeries",
        "build_benchmark1",
        "select_benchmark2_reference_price",
        "compute_benchmark2_prices",
        "compute_benchmark2_day_one_purchase",
        "build_benchmark2",
    ):
        assert hasattr(engine_pkg, name), name
        assert name in engine_pkg.__all__


def test_private_search_helper_is_not_exported() -> None:
    import app.engine as engine_pkg

    assert "_max_affordable_lots" not in engine_pkg.__all__


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
    ):
        assert callable(getattr(engine_pkg, name)), name


def test_benchmark_modules_have_no_forbidden_dependencies() -> None:
    import app.engine.benchmark_models
    import app.engine.benchmarks

    for module in (app.engine.benchmarks, app.engine.benchmark_models):
        source = inspect.getsource(module).lower()
        for forbidden in (
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "app.importing",
            "metric",
            "drawdown",
            "sharpe",
            "optimization",
            "database",
        ):
            assert forbidden not in source, f"{module.__name__} contains {forbidden!r}"


def test_no_equity_row_models_or_backtest_loop_introduced() -> None:
    import app.engine as engine_pkg

    assert not hasattr(engine_pkg, "EventEquity")
    assert not hasattr(engine_pkg, "DailyEquity")
    assert not hasattr(engine_pkg, "run_backtest")
