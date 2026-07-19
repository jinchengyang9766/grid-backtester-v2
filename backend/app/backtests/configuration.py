"""Adapter from the API request schema to the pure-engine configuration.

The engine never sees Pydantic/FastAPI/SQLAlchemy objects; this module maps
request models onto the existing frozen engine dataclasses and produces the
canonical JSON-safe configuration document persisted on BacktestRun.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.api.schemas.backtests import (
    BacktestConfigurationInput,
    CommissionInput,
    SlippageInput,
    ValueInput,
)
from app.backtests.serialization import JsonValue, plain_decimal
from app.domain.enums import DataMode, OHLCPathMode, ValueMode
from app.engine import (
    BacktestConfig,
    CommissionConfig,
    ExecutionConfig,
    SlippageConfig,
    TickSizeConfig,
    ValueConfig,
)

__all__ = ["AdaptedConfiguration", "adapt_configuration", "generate_backtest_name"]


@dataclass(frozen=True, slots=True)
class AdaptedConfiguration:
    engine_config: BacktestConfig
    configuration_json: dict[str, JsonValue]
    ohlc_path_mode: str | None


def _value_config(value_input: ValueInput) -> ValueConfig:
    return ValueConfig(mode=ValueMode(value_input.mode), value=value_input.value)


def _commission_config(commission: CommissionInput) -> CommissionConfig:
    return CommissionConfig(
        rate_enabled=commission.rate_enabled,
        rate=commission.rate,
        minimum_enabled=commission.minimum_enabled,
        minimum=commission.minimum,
        fixed_enabled=commission.fixed_enabled,
        fixed=commission.fixed,
    )


def _slippage_configs(slippage: SlippageInput) -> tuple[SlippageConfig, SlippageConfig]:
    if slippage.shared:
        assert slippage.mode is not None and slippage.value is not None  # schema-guaranteed
        shared = SlippageConfig(mode=ValueMode(slippage.mode), value=slippage.value)
        return shared, shared
    assert slippage.buy is not None and slippage.sell is not None  # schema-guaranteed
    return (
        SlippageConfig(mode=ValueMode(slippage.buy.mode), value=slippage.buy.value),
        SlippageConfig(mode=ValueMode(slippage.sell.mode), value=slippage.sell.value),
    )


def _optional_decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else plain_decimal(value)


def _value_json(value_input: ValueInput) -> dict[str, JsonValue]:
    return {"mode": value_input.mode, "value": plain_decimal(value_input.value)}


def _commission_json(commission: CommissionInput) -> dict[str, JsonValue]:
    return {
        "rate_enabled": commission.rate_enabled,
        "rate": plain_decimal(commission.rate),
        "minimum_enabled": commission.minimum_enabled,
        "minimum": plain_decimal(commission.minimum),
        "fixed_enabled": commission.fixed_enabled,
        "fixed": plain_decimal(commission.fixed),
    }


def _slippage_json(slippage: SlippageInput) -> dict[str, JsonValue]:
    if slippage.shared:
        assert slippage.mode is not None and slippage.value is not None
        return {
            "shared": True,
            "mode": slippage.mode,
            "value": plain_decimal(slippage.value),
            "buy": None,
            "sell": None,
        }
    assert slippage.buy is not None and slippage.sell is not None
    return {
        "shared": False,
        "mode": None,
        "value": None,
        "buy": {"mode": slippage.buy.mode, "value": plain_decimal(slippage.buy.value)},
        "sell": {"mode": slippage.sell.mode, "value": plain_decimal(slippage.sell.value)},
    }


def adapt_configuration(
    configuration: BacktestConfigurationInput, *, data_mode: DataMode
) -> AdaptedConfiguration:
    """Map the request onto engine config plus the canonical persisted JSON.

    For CLOSE_ONLY datasets a supplied ohlc_path_mode is canonicalized to
    null (the wizard disables the field; SPEC defines no rejection) so it
    can never alter engine behavior.
    """
    canonical_path_mode = configuration.ohlc_path_mode if data_mode is DataMode.OHLCV else None
    buy_slippage, sell_slippage = _slippage_configs(configuration.slippage)
    execution = ExecutionConfig(
        lot_size=configuration.lot_size,
        trade_lots=configuration.trade_lots,
        buy_slippage=buy_slippage,
        sell_slippage=sell_slippage,
        buy_commission=_commission_config(configuration.buy_commission),
        sell_commission=_commission_config(configuration.sell_commission),
        tick_size=TickSizeConfig(
            enabled=configuration.tick_size.enabled, value=configuration.tick_size.value
        ),
    )
    engine_config = BacktestConfig(
        data_mode=data_mode,
        ohlc_path_mode=(None if canonical_path_mode is None else OHLCPathMode(canonical_path_mode)),
        baseline_override=configuration.baseline,
        a_distance=_value_config(configuration.a_distance),
        c_distance=_value_config(configuration.c_distance),
        grid_step=_value_config(configuration.grid_step),
        execution=execution,
        initial_cash=configuration.initial_cash,
        initial_shares=configuration.initial_shares,
        annual_risk_free_rate=configuration.risk_free_rate_annual,
    )
    configuration_json: dict[str, JsonValue] = {
        "initial_cash": plain_decimal(configuration.initial_cash),
        "initial_shares": configuration.initial_shares,
        "lot_size": configuration.lot_size,
        "trade_lots": configuration.trade_lots,
        "baseline": _optional_decimal_string(configuration.baseline),
        "a_distance": _value_json(configuration.a_distance),
        "c_distance": _value_json(configuration.c_distance),
        "grid_step": _value_json(configuration.grid_step),
        "tick_size": {
            "enabled": configuration.tick_size.enabled,
            "value": _optional_decimal_string(configuration.tick_size.value),
        },
        "ohlc_path_mode": canonical_path_mode,
        "buy_commission": _commission_json(configuration.buy_commission),
        "sell_commission": _commission_json(configuration.sell_commission),
        "slippage": _slippage_json(configuration.slippage),
        "risk_free_rate_annual": plain_decimal(configuration.risk_free_rate_annual),
    }
    return AdaptedConfiguration(
        engine_config=engine_config,
        configuration_json=configuration_json,
        ohlc_path_mode=canonical_path_mode,
    )


def _step_label(grid_step: ValueInput) -> str:
    if grid_step.mode == "PERCENT":
        percent = grid_step.value * Decimal("100")
        text = plain_decimal(percent)
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return f"{text}%"
    text = plain_decimal(grid_step.value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def generate_backtest_name(
    *,
    security_code: str | None,
    dataset_name: str,
    grid_step: ValueInput,
    today: date,
) -> str:
    """`{security_code or dataset name} — A Grid {step} — {YYYY-MM-DD}` (UTC date)."""
    label = security_code if security_code and security_code.strip() else dataset_name
    return f"{label} — A Grid {_step_label(grid_step)} — {today.isoformat()}"
