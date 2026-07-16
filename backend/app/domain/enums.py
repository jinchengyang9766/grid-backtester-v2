"""Domain enums shared by the pure backtest engine."""

from enum import StrEnum

__all__ = [
    "DataMode",
    "OHLCPathMode",
    "SkipReason",
    "TradeSide",
    "TradeStatus",
    "ValueMode",
    "ZoneEventType",
    "ZoneState",
]


class DataMode(StrEnum):
    OHLCV = "OHLCV"
    CLOSE_ONLY = "CLOSE_ONLY"


class OHLCPathMode(StrEnum):
    HIGH_FIRST = "HIGH_FIRST"
    LOW_FIRST = "LOW_FIRST"
    AUTO = "AUTO"


class ZoneState(StrEnum):
    IN_A = "IN_A"
    IN_C = "IN_C"
    OUTSIDE_C = "OUTSIDE_C"


class ValueMode(StrEnum):
    PERCENT = "PERCENT"
    FIXED = "FIXED"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(StrEnum):
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"


class SkipReason(StrEnum):
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_SHARES = "INSUFFICIENT_SHARES"
    INSUFFICIENT_CASH_FOR_COMMISSION = "INSUFFICIENT_CASH_FOR_COMMISSION"


class ZoneEventType(StrEnum):
    ENTER_C_ZONE = "ENTER_C_ZONE"
    EXIT_C_ZONE = "EXIT_C_ZONE"
    OUTSIDE_C_BOUNDARY = "OUTSIDE_C_BOUNDARY"
    RETURN_INSIDE_C_BOUNDARY = "RETURN_INSIDE_C_BOUNDARY"
