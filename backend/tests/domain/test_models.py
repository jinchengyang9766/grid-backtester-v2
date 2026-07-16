"""Tests for immutable domain dataclasses."""

import dataclasses
from datetime import date
from decimal import Decimal

import pytest
from app.domain import Bar, PathPoint


def test_bar_stores_ohlcv_row() -> None:
    bar = Bar(
        date=date(2020, 1, 2),
        open=Decimal("1.230"),
        high=Decimal("1.250"),
        low=Decimal("1.200"),
        close=Decimal("1.240"),
        volume=Decimal("1000000"),
    )
    assert bar.date == date(2020, 1, 2)
    assert bar.open == Decimal("1.230")
    assert bar.high == Decimal("1.250")
    assert bar.low == Decimal("1.200")
    assert bar.close == Decimal("1.240")
    assert bar.volume == Decimal("1000000")


def test_bar_supports_close_only_data() -> None:
    bar = Bar(date=date(2020, 1, 2), close=Decimal("1.240"))
    assert bar.close == Decimal("1.240")
    assert bar.open is None
    assert bar.high is None
    assert bar.low is None
    assert bar.volume is None


def test_bar_is_immutable() -> None:
    bar = Bar(date=date(2020, 1, 2), close=Decimal("1.240"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        bar.close = Decimal("2.000")  # type: ignore[misc]


def test_bar_decimal_fields_are_not_converted() -> None:
    close = Decimal("1.23456789")
    bar = Bar(date=date(2020, 1, 2), close=close)
    assert bar.close is close
    assert isinstance(bar.close, Decimal)
    assert not isinstance(bar.close, float)


def test_path_point_stores_fields() -> None:
    point = PathPoint(price=Decimal("10.05"), date=date(2020, 1, 2), is_bar_final=True)
    assert point.price == Decimal("10.05")
    assert point.date == date(2020, 1, 2)
    assert point.is_bar_final is True


def test_path_point_is_immutable() -> None:
    point = PathPoint(price=Decimal("10.05"), date=date(2020, 1, 2), is_bar_final=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        point.price = Decimal("11.00")  # type: ignore[misc]


def test_path_point_decimal_is_not_converted() -> None:
    price = Decimal("10.0500000")
    point = PathPoint(price=price, date=date(2020, 1, 2), is_bar_final=True)
    assert point.price is price
    assert isinstance(point.price, Decimal)
