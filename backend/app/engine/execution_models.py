"""Execution configuration, portfolio state, trade results, and their exceptions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import SkipReason, TradeSide, TradeStatus, ValueMode
from app.engine.grid_models import TickSizeConfig

__all__ = [
    "CommissionConfig",
    "ExecutionConfig",
    "InvalidLotSizeError",
    "InvalidTradeLotsError",
    "NegativeCommissionComponentError",
    "NegativeInitialCashError",
    "NegativeInitialSharesError",
    "NegativeSlippageError",
    "NonPositiveExecutionPriceError",
    "PortfolioState",
    "SlippageConfig",
    "TradeResult",
]


@dataclass(frozen=True, slots=True)
class SlippageConfig:
    """Percent values are decimal fractions (0.001 = 0.1%)."""

    mode: ValueMode
    value: Decimal


@dataclass(frozen=True, slots=True)
class CommissionConfig:
    rate_enabled: bool
    rate: Decimal
    minimum_enabled: bool
    minimum: Decimal
    fixed_enabled: bool
    fixed: Decimal


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    lot_size: int
    trade_lots: int
    buy_slippage: SlippageConfig
    sell_slippage: SlippageConfig
    buy_commission: CommissionConfig
    sell_commission: CommissionConfig
    tick_size: TickSizeConfig


@dataclass(slots=True)
class PortfolioState:
    """Deliberately mutable: execution debits/credits it in place."""

    cash: Decimal
    shares: int


@dataclass(frozen=True, slots=True)
class TradeResult:
    event_date: date
    side: TradeSide
    grid_price: Decimal
    execution_price: Decimal | None
    shares: int
    notional: Decimal | None
    commission: Decimal | None
    slippage_cost: Decimal | None
    cash_after: Decimal
    shares_after: int
    equity_after: Decimal
    status: TradeStatus
    skip_reason: SkipReason | None


class NegativeInitialCashError(Exception):
    def __init__(self, initial_cash: Decimal) -> None:
        super().__init__(f"Initial cash must be >= 0; got {initial_cash}.")
        self.initial_cash = initial_cash


class NegativeInitialSharesError(Exception):
    def __init__(self, initial_shares: int) -> None:
        super().__init__(f"Initial shares must be >= 0; got {initial_shares}.")
        self.initial_shares = initial_shares


class InvalidLotSizeError(Exception):
    def __init__(self, lot_size: int) -> None:
        super().__init__(f"lot_size must be >= 1; got {lot_size}.")
        self.lot_size = lot_size


class InvalidTradeLotsError(Exception):
    def __init__(self, trade_lots: int) -> None:
        super().__init__(f"trade_lots must be >= 1; got {trade_lots}.")
        self.trade_lots = trade_lots


class NegativeSlippageError(Exception):
    def __init__(self, side: TradeSide, value: Decimal) -> None:
        super().__init__(f"{side.value} slippage must be >= 0; got {value}.")
        self.side = side
        self.value = value


class NegativeCommissionComponentError(Exception):
    def __init__(self, side: TradeSide, component: str, value: Decimal) -> None:
        super().__init__(
            f"Enabled {side.value} commission component '{component}' must be >= 0; got {value}."
        )
        self.side = side
        self.component = component
        self.value = value


class NonPositiveExecutionPriceError(Exception):
    def __init__(self, grid_price: Decimal, execution_price: Decimal) -> None:
        super().__init__(
            f"Execution price {execution_price} for grid price {grid_price} is not positive; "
            "the slippage/tick configuration is nonsensical for this price."
        )
        self.grid_price = grid_price
        self.execution_price = execution_price
