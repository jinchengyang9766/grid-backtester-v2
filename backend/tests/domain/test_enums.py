"""Tests for domain enums."""

from app.domain import (
    DataMode,
    OHLCPathMode,
    SkipReason,
    TradeSide,
    TradeStatus,
    ValueMode,
    ZoneEventType,
    ZoneState,
)


def test_data_mode_values() -> None:
    assert DataMode.OHLCV == "OHLCV"
    assert DataMode.CLOSE_ONLY == "CLOSE_ONLY"


def test_ohlc_path_mode_values() -> None:
    assert OHLCPathMode.HIGH_FIRST == "HIGH_FIRST"
    assert OHLCPathMode.LOW_FIRST == "LOW_FIRST"
    assert OHLCPathMode.AUTO == "AUTO"


def test_zone_state_values() -> None:
    assert ZoneState.IN_A == "IN_A"
    assert ZoneState.IN_C == "IN_C"
    assert ZoneState.OUTSIDE_C == "OUTSIDE_C"


def test_value_mode_values() -> None:
    assert ValueMode.PERCENT == "PERCENT"
    assert ValueMode.FIXED == "FIXED"


def test_trade_side_values() -> None:
    assert TradeSide.BUY == "BUY"
    assert TradeSide.SELL == "SELL"


def test_trade_status_values() -> None:
    assert TradeStatus.EXECUTED == "EXECUTED"
    assert TradeStatus.SKIPPED == "SKIPPED"


def test_skip_reason_values() -> None:
    assert SkipReason.INSUFFICIENT_CASH == "INSUFFICIENT_CASH"
    assert SkipReason.INSUFFICIENT_SHARES == "INSUFFICIENT_SHARES"
    assert SkipReason.INSUFFICIENT_CASH_FOR_COMMISSION == "INSUFFICIENT_CASH_FOR_COMMISSION"


def test_zone_event_type_values() -> None:
    assert ZoneEventType.ENTER_C_ZONE == "ENTER_C_ZONE"
    assert ZoneEventType.EXIT_C_ZONE == "EXIT_C_ZONE"
    assert ZoneEventType.OUTSIDE_C_BOUNDARY == "OUTSIDE_C_BOUNDARY"
    assert ZoneEventType.RETURN_INSIDE_C_BOUNDARY == "RETURN_INSIDE_C_BOUNDARY"


def test_enum_members_behave_as_strings() -> None:
    assert isinstance(DataMode.OHLCV, str)
    assert isinstance(ZoneState.IN_A, str)
    assert str(TradeSide.BUY) == "BUY"
    assert f"side={TradeSide.SELL}" == "side=SELL"
