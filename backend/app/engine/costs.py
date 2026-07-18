"""Slippage and commission calculations under the frozen SPEC 9.3 ordering.

The pipeline for one attempt is: canonical grid price -> slippage ->
execution-price tick rounding -> notional -> commission. The canonical grid
price is never re-rounded here, and commission is never tick-rounded.
"""

from decimal import Decimal

from app.domain.enums import TradeSide, ValueMode
from app.engine.execution_models import (
    CommissionConfig,
    NonPositiveExecutionPriceError,
    SlippageConfig,
)
from app.engine.grid import NonPositiveTickSizeError, round_to_tick
from app.engine.grid_models import TickSizeConfig

__all__ = [
    "compute_commission",
    "compute_execution_price",
    "compute_slippage_amount",
]

_ZERO = Decimal("0")


def compute_slippage_amount(grid_price: Decimal, config: SlippageConfig) -> Decimal:
    if config.mode is ValueMode.FIXED:
        return config.value
    return grid_price * config.value


def compute_execution_price(
    *,
    grid_price: Decimal,
    side: TradeSide,
    slippage: SlippageConfig,
    tick_size: TickSizeConfig,
) -> Decimal:
    slippage_amount = compute_slippage_amount(grid_price, slippage)
    if side is TradeSide.BUY:
        raw_execution_price = grid_price + slippage_amount
    else:
        raw_execution_price = grid_price - slippage_amount

    if tick_size.enabled:
        if tick_size.value is None or tick_size.value <= 0:
            raise NonPositiveTickSizeError(
                f"Tick size must be a positive value when enabled; got {tick_size.value}."
            )
        execution_price = round_to_tick(raw_execution_price, tick_size.value)
    else:
        execution_price = raw_execution_price

    if execution_price <= 0:
        raise NonPositiveExecutionPriceError(grid_price=grid_price, execution_price=execution_price)
    return execution_price


def compute_commission(notional: Decimal, config: CommissionConfig) -> Decimal:
    percentage_component = notional * config.rate if config.rate_enabled else _ZERO
    if config.minimum_enabled:
        percentage_component = max(percentage_component, config.minimum)
    return percentage_component + (config.fixed if config.fixed_enabled else _ZERO)
