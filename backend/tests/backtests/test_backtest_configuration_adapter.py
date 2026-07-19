"""Tests for the API-to-engine configuration adapter."""

import json
from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from app.api.schemas.backtests import (
    BacktestConfigurationInput,
    BacktestCreateRequest,
    SlippageInput,
)
from app.backtests.configuration import adapt_configuration, generate_backtest_name
from app.domain.enums import DataMode, OHLCPathMode, ValueMode
from pydantic import ValidationError


def base_configuration(**overrides: Any) -> dict[str, Any]:
    configuration: dict[str, Any] = {
        "initial_cash": "100000.00",
        "initial_shares": 0,
        "lot_size": 100,
        "trade_lots": 1,
        "baseline": None,
        "a_distance": {"mode": "PERCENT", "value": "0.05"},
        "c_distance": {"mode": "PERCENT", "value": "0.15"},
        "grid_step": {"mode": "PERCENT", "value": "0.01"},
        "tick_size": {"enabled": False, "value": None},
        "ohlc_path_mode": "AUTO",
        "buy_commission": {
            "rate_enabled": True,
            "rate": "0.0003",
            "minimum_enabled": True,
            "minimum": "5.00",
            "fixed_enabled": False,
            "fixed": "0",
        },
        "sell_commission": {
            "rate_enabled": True,
            "rate": "0.0003",
            "minimum_enabled": True,
            "minimum": "5.00",
            "fixed_enabled": False,
            "fixed": "0",
        },
        "slippage": {"shared": True, "mode": "FIXED", "value": "0.001", "buy": None, "sell": None},
        "risk_free_rate_annual": "0.0",
    }
    configuration.update(overrides)
    return configuration


def parse(**overrides: Any) -> BacktestConfigurationInput:
    return BacktestConfigurationInput(**base_configuration(**overrides))


def assert_no_float(value: object) -> None:
    assert not isinstance(value, float), f"float found: {value!r}"
    if isinstance(value, dict):
        for key, item in value.items():
            assert_no_float(key)
            assert_no_float(item)
    elif isinstance(value, list | tuple):
        for item in value:
            assert_no_float(item)
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            assert_no_float(getattr(value, field.name))


class TestEngineConfigMapping:
    def test_decimals_remain_decimal_and_no_float(self) -> None:
        adapted = adapt_configuration(parse(), data_mode=DataMode.OHLCV)
        config = adapted.engine_config
        assert isinstance(config.initial_cash, Decimal)
        assert isinstance(config.a_distance.value, Decimal)
        assert isinstance(config.execution.buy_commission.rate, Decimal)
        assert isinstance(config.execution.buy_slippage.value, Decimal)
        assert isinstance(config.annual_risk_free_rate, Decimal)
        assert_no_float(config)

    def test_percent_and_fixed_value_mapping(self) -> None:
        adapted = adapt_configuration(
            parse(
                a_distance={"mode": "PERCENT", "value": "0.05"},
                grid_step={"mode": "FIXED", "value": "0.01"},
            ),
            data_mode=DataMode.OHLCV,
        )
        assert adapted.engine_config.a_distance.mode is ValueMode.PERCENT
        assert adapted.engine_config.a_distance.value == Decimal("0.05")
        assert adapted.engine_config.grid_step.mode is ValueMode.FIXED
        assert adapted.engine_config.grid_step.value == Decimal("0.01")

    def test_baseline_null_and_explicit(self) -> None:
        assert (
            adapt_configuration(parse(), data_mode=DataMode.OHLCV).engine_config.baseline_override
            is None
        )
        adapted = adapt_configuration(parse(baseline="1.25"), data_mode=DataMode.OHLCV)
        assert adapted.engine_config.baseline_override == Decimal("1.25")

    def test_tick_size_enabled_and_disabled(self) -> None:
        disabled = adapt_configuration(parse(), data_mode=DataMode.OHLCV)
        assert disabled.engine_config.execution.tick_size.enabled is False
        assert disabled.engine_config.execution.tick_size.value is None
        enabled = adapt_configuration(
            parse(tick_size={"enabled": True, "value": "0.001"}), data_mode=DataMode.OHLCV
        )
        assert enabled.engine_config.execution.tick_size.enabled is True
        assert enabled.engine_config.execution.tick_size.value == Decimal("0.001")

    @pytest.mark.parametrize("mode", ["HIGH_FIRST", "LOW_FIRST", "AUTO"])
    def test_ohlcv_path_mode_mapping(self, mode: str) -> None:
        adapted = adapt_configuration(parse(ohlc_path_mode=mode), data_mode=DataMode.OHLCV)
        assert adapted.engine_config.ohlc_path_mode is OHLCPathMode(mode)
        assert adapted.ohlc_path_mode == mode
        assert adapted.engine_config.data_mode is DataMode.OHLCV

    def test_close_only_canonicalizes_path_mode_to_null(self) -> None:
        adapted = adapt_configuration(parse(ohlc_path_mode="AUTO"), data_mode=DataMode.CLOSE_ONLY)
        assert adapted.engine_config.data_mode is DataMode.CLOSE_ONLY
        assert adapted.engine_config.ohlc_path_mode is None
        assert adapted.ohlc_path_mode is None
        assert adapted.configuration_json["ohlc_path_mode"] is None

    def test_commission_exact_mapping_with_disabled_flags(self) -> None:
        adapted = adapt_configuration(
            parse(
                buy_commission={
                    "rate_enabled": False,
                    "rate": "0.0003",
                    "minimum_enabled": False,
                    "minimum": "5.00",
                    "fixed_enabled": False,
                    "fixed": "2.50",
                }
            ),
            data_mode=DataMode.OHLCV,
        )
        commission = adapted.engine_config.execution.buy_commission
        # Disabled flags never erase the stored values.
        assert commission.rate_enabled is False
        assert commission.rate == Decimal("0.0003")
        assert commission.minimum_enabled is False
        assert commission.minimum == Decimal("5.00")
        assert commission.fixed_enabled is False
        assert commission.fixed == Decimal("2.50")

    def test_shared_slippage_maps_identically_to_both_sides(self) -> None:
        adapted = adapt_configuration(parse(), data_mode=DataMode.OHLCV)
        execution = adapted.engine_config.execution
        assert execution.buy_slippage == execution.sell_slippage
        assert execution.buy_slippage.mode is ValueMode.FIXED
        assert execution.buy_slippage.value == Decimal("0.001")

    def test_separate_slippage_maps_independently(self) -> None:
        adapted = adapt_configuration(
            parse(
                slippage={
                    "shared": False,
                    "mode": None,
                    "value": None,
                    "buy": {"mode": "PERCENT", "value": "0.002"},
                    "sell": {"mode": "FIXED", "value": "0.005"},
                }
            ),
            data_mode=DataMode.OHLCV,
        )
        execution = adapted.engine_config.execution
        assert execution.buy_slippage.mode is ValueMode.PERCENT
        assert execution.buy_slippage.value == Decimal("0.002")
        assert execution.sell_slippage.mode is ValueMode.FIXED
        assert execution.sell_slippage.value == Decimal("0.005")


class TestSlippageShapeValidation:
    @pytest.mark.parametrize(
        "payload",
        [
            {"shared": True, "mode": None, "value": None, "buy": None, "sell": None},
            {
                "shared": True,
                "mode": "FIXED",
                "value": "0.001",
                "buy": {"mode": "FIXED", "value": "1"},
                "sell": None,
            },
            {"shared": False, "mode": None, "value": None, "buy": None, "sell": None},
            {
                "shared": False,
                "mode": "FIXED",
                "value": "0.001",
                "buy": {"mode": "FIXED", "value": "1"},
                "sell": {"mode": "FIXED", "value": "1"},
            },
        ],
    )
    def test_invalid_mixed_shapes_rejected(self, payload: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            SlippageInput(**payload)


class TestCanonicalConfigurationJson:
    def test_json_safe_plain_strings_and_no_float(self) -> None:
        adapted = adapt_configuration(parse(baseline="1.25"), data_mode=DataMode.OHLCV)
        document = adapted.configuration_json
        json.dumps(document)  # must be JSON-serializable as-is
        assert_no_float(document)
        assert document["initial_cash"] == "100000.00"
        assert document["baseline"] == "1.25"
        assert document["a_distance"] == {"mode": "PERCENT", "value": "0.05"}
        assert document["tick_size"] == {"enabled": False, "value": None}
        buy_commission = document["buy_commission"]
        assert isinstance(buy_commission, dict)
        assert buy_commission["rate"] == "0.0003"
        assert document["slippage"] == {
            "shared": True,
            "mode": "FIXED",
            "value": "0.001",
            "buy": None,
            "sell": None,
        }
        assert document["initial_shares"] == 0
        assert document["lot_size"] == 100

    def test_separate_slippage_json_is_canonical(self) -> None:
        adapted = adapt_configuration(
            parse(
                slippage={
                    "shared": False,
                    "mode": None,
                    "value": None,
                    "buy": {"mode": "PERCENT", "value": "0.002"},
                    "sell": {"mode": "FIXED", "value": "0.005"},
                }
            ),
            data_mode=DataMode.OHLCV,
        )
        assert adapted.configuration_json["slippage"] == {
            "shared": False,
            "mode": None,
            "value": None,
            "buy": {"mode": "PERCENT", "value": "0.002"},
            "sell": {"mode": "FIXED", "value": "0.005"},
        }


class TestRequestSchema:
    def test_unknown_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BacktestConfigurationInput.model_validate({**base_configuration(), "surprise": 1})
        with pytest.raises(ValidationError):
            BacktestCreateRequest.model_validate(
                {"dataset_id": 1, "configuration": base_configuration(), "user_id": 7}
            )

    def test_whitespace_only_name_rejected_and_valid_name_trimmed(self) -> None:
        with pytest.raises(ValidationError):
            BacktestCreateRequest.model_validate(
                {"dataset_id": 1, "name": "   ", "configuration": base_configuration()}
            )
        request = BacktestCreateRequest.model_validate(
            {"dataset_id": 1, "name": "  My Run  ", "configuration": base_configuration()}
        )
        assert request.name == "My Run"


class TestNameGeneration:
    def test_percent_grid_label(self) -> None:
        configuration = parse(grid_step={"mode": "PERCENT", "value": "0.02"})
        name = generate_backtest_name(
            security_code="159825",
            dataset_name="ignored",
            grid_step=configuration.grid_step,
            today=date(2026, 7, 19),
        )
        assert name == "159825 — A Grid 2% — 2026-07-19"

    def test_fixed_grid_label(self) -> None:
        configuration = parse(grid_step={"mode": "FIXED", "value": "0.01"})
        name = generate_backtest_name(
            security_code="159825",
            dataset_name="ignored",
            grid_step=configuration.grid_step,
            today=date(2026, 7, 19),
        )
        assert name == "159825 — A Grid 0.01 — 2026-07-19"

    def test_blank_security_code_falls_back_to_dataset_name(self) -> None:
        configuration = parse(grid_step={"mode": "PERCENT", "value": "0.015"})
        name = generate_backtest_name(
            security_code="   ",
            dataset_name="My Dataset",
            grid_step=configuration.grid_step,
            today=date(2026, 1, 2),
        )
        assert name == "My Dataset — A Grid 1.5% — 2026-01-02"

    def test_injected_date_is_deterministic(self) -> None:
        configuration = parse()
        first = generate_backtest_name(
            security_code="X",
            dataset_name="d",
            grid_step=configuration.grid_step,
            today=date(2030, 12, 31),
        )
        assert first.endswith("2030-12-31")
