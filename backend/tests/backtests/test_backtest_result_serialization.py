"""Tests for canonical JSON serialization and the result_metrics projection."""

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

import pytest
from app.backtests.serialization import build_result_metrics, json_safe, plain_decimal
from app.domain.enums import DataMode, TradeSide, ValueMode
from app.domain.models import Bar
from app.engine import (
    BacktestConfig,
    BacktestResult,
    CommissionConfig,
    ExecutionConfig,
    SlippageConfig,
    TickSizeConfig,
    ValueConfig,
    run_backtest,
)

EXPECTED_METRIC_KEYS = {
    "initial_equity",
    "baseline",
    "a_lower",
    "a_upper",
    "c_lower",
    "c_upper",
    "grid_step",
    "grid_levels",
    "metrics",
    "benchmark1",
    "benchmark2",
    "final_state",
}


def zero_commission() -> CommissionConfig:
    return CommissionConfig(
        rate_enabled=False,
        rate=Decimal("0"),
        minimum_enabled=False,
        minimum=Decimal("0"),
        fixed_enabled=False,
        fixed=Decimal("0"),
    )


def small_config() -> BacktestConfig:
    no_slip = SlippageConfig(mode=ValueMode.FIXED, value=Decimal("0"))
    return BacktestConfig(
        data_mode=DataMode.CLOSE_ONLY,
        ohlc_path_mode=None,
        baseline_override=None,
        a_distance=ValueConfig(mode=ValueMode.FIXED, value=Decimal("2")),
        c_distance=ValueConfig(mode=ValueMode.FIXED, value=Decimal("4")),
        grid_step=ValueConfig(mode=ValueMode.FIXED, value=Decimal("1")),
        execution=ExecutionConfig(
            lot_size=1,
            trade_lots=1,
            buy_slippage=no_slip,
            sell_slippage=no_slip,
            buy_commission=zero_commission(),
            sell_commission=zero_commission(),
            tick_size=TickSizeConfig(enabled=False),
        ),
        initial_cash=Decimal("100"),
        initial_shares=0,
        annual_risk_free_rate=Decimal("0"),
    )


def small_result() -> BacktestResult:
    bars = [
        Bar(date=date(2026, 1, 5), close=Decimal("10")),
        Bar(date=date(2026, 1, 6), close=Decimal("9")),
        Bar(date=date(2026, 1, 7), close=Decimal("10")),
    ]
    return run_backtest(bars, small_config())


class TestPlainDecimal:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Decimal("1E+2"), "100"),
            (Decimal("1E-7"), "0.0000001"),
            (Decimal("0.00100"), "0.00100"),  # meaningful precision preserved
            (Decimal("-12.5"), "-12.5"),
            (Decimal("100000.00"), "100000.00"),
        ],
    )
    def test_fixed_point_never_scientific(self, value: Decimal, expected: str) -> None:
        text = plain_decimal(value)
        assert text == expected
        assert "e" not in text.lower()


class TestJsonSafe:
    def test_scalars_enums_dates_and_none(self) -> None:
        class Color(StrEnum):
            RED = "RED"

        assert json_safe(None) is None
        assert json_safe(True) is True
        assert json_safe(5) == 5
        assert json_safe("x") == "x"
        assert json_safe(Decimal("2.50")) == "2.50"
        assert json_safe(Color.RED) == "RED"
        assert json_safe(TradeSide.BUY) == "BUY"
        assert json_safe(date(2026, 1, 5)) == "2026-01-05"
        assert json_safe(datetime(2026, 1, 5, 12, 30)) == "2026-01-05T12:30:00"

    def test_dataclasses_tuples_and_mappings_recurse(self) -> None:
        @dataclass(frozen=True)
        class Inner:
            price: Decimal

        @dataclass(frozen=True)
        class Outer:
            name: str
            values: tuple[Inner, ...]
            counts: dict[TradeSide, int]

        serialized = json_safe(
            Outer(name="n", values=(Inner(Decimal("1.5")),), counts={TradeSide.SELL: 2})
        )
        assert serialized == {"name": "n", "values": [{"price": "1.5"}], "counts": {"SELL": 2}}

    def test_unsupported_objects_fail_loudly(self) -> None:
        with pytest.raises(TypeError):
            json_safe({1, 2, 3})
        with pytest.raises(TypeError):
            json_safe(object())
        with pytest.raises(TypeError):
            json_safe(1.5)  # floats are never accepted


def assert_no_float(value: object) -> None:
    assert not isinstance(value, float)
    if isinstance(value, dict):
        for item in value.values():
            assert_no_float(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_float(item)


class TestResultMetricsProjection:
    def test_exact_key_set_and_grid_levels(self) -> None:
        metrics = build_result_metrics(small_result())
        assert set(metrics) == EXPECTED_METRIC_KEYS
        grid_levels = metrics["grid_levels"]
        assert isinstance(grid_levels, list)
        assert grid_levels == ["8", "9", "10", "11", "12"]
        assert all(isinstance(level, str) for level in grid_levels)

    def test_strategy_benchmark_and_final_state_blocks(self) -> None:
        metrics = build_result_metrics(small_result())
        nested = metrics["metrics"]
        assert isinstance(nested, dict)
        assert set(nested) == {
            "strategy",
            "trade_costs",
            "zones",
            "first_return",
            "benchmark1",
            "benchmark2",
            "benchmark2_day_one_commission",
            "benchmark2_day_one_slippage_cost",
        }
        strategy = nested["strategy"]
        assert isinstance(strategy, dict)
        assert set(strategy) == {
            "initial_equity",
            "final_equity",
            "net_profit",
            "total_return",
            "annualized_return",
            "maximum_drawdown",
            "sharpe_ratio",
        }
        trade_costs = nested["trade_costs"]
        assert isinstance(trade_costs, dict)
        assert set(trade_costs) == {
            "total_commission",
            "total_slippage_cost",
            "executed_trades",
            "skipped_trades",
            "buy_count",
            "sell_count",
        }
        zones = nested["zones"]
        assert isinstance(zones, dict)
        zone_counts = zones["zone_event_counts"]
        assert isinstance(zone_counts, dict)
        assert set(zone_counts) == {
            "ENTER_C_ZONE",
            "EXIT_C_ZONE",
            "OUTSIDE_C_BOUNDARY",
            "RETURN_INSIDE_C_BOUNDARY",
        }
        first_return = nested["first_return"]
        assert isinstance(first_return, dict)
        assert set(first_return) == {"equity", "days"}

        benchmark2 = metrics["benchmark2"]
        assert isinstance(benchmark2, dict)
        assert set(benchmark2) == {"points", "day_one_purchase"}
        purchase = benchmark2["day_one_purchase"]
        assert isinstance(purchase, dict)
        assert set(purchase) == {
            "reference_price",
            "tick_price",
            "execution_price",
            "lots",
            "shares_purchased",
            "notional",
            "commission",
            "slippage_cost",
            "cash_after",
            "shares_after",
        }
        final_state = metrics["final_state"]
        assert isinstance(final_state, dict)
        assert set(final_state) == {
            "cash",
            "shares",
            "market_cursor",
            "trade_anchor",
            "zone_state",
        }

    def test_no_float_and_json_serializable(self) -> None:
        metrics = build_result_metrics(small_result())
        json.dumps(metrics)
        assert_no_float(metrics)

    def test_no_normalized_series_duplicated(self) -> None:
        metrics = build_result_metrics(small_result())
        for forbidden in ("actions", "event_equity", "daily_equity", "trades", "zone_events"):
            assert forbidden not in metrics

    def test_repeated_serialization_is_deterministic(self) -> None:
        result = small_result()
        assert build_result_metrics(result) == build_result_metrics(result)
        assert json.dumps(build_result_metrics(result)) == json.dumps(build_result_metrics(result))
