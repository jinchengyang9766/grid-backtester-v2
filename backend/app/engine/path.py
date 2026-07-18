"""Deterministic price-path construction, segmentation, and initial state.

Implements SPEC Sections 6, 10.2, 11.1, 11.2, and the path-construction
metadata portion of 11.6. The path is one continuous point sequence across
the whole dataset; the overnight gap Close[i] -> Open[i+1] is an ordinary
adjacent pair, never a reset.
"""

from collections.abc import Sequence
from decimal import Decimal

from app.domain.enums import DataMode, OHLCPathMode
from app.domain.models import Bar, PathPoint
from app.engine.grid import EmptyDatasetError, classify_zone
from app.engine.grid_models import ZoneBoundaries
from app.engine.path_models import InitialPathState, PathSegment

__all__ = [
    "InvalidOhlcvBarError",
    "OhlcPathModeRequiredError",
    "build_close_only_path",
    "build_ohlcv_path",
    "build_path_segments",
    "build_price_path",
    "initialize_path_state",
    "select_ohlc_midpoints",
]


class InvalidOhlcvBarError(Exception):
    def __init__(self, bar_index: int, missing_fields: tuple[str, ...]) -> None:
        super().__init__(
            f"Bar at index {bar_index} is missing OHLCV field(s): {', '.join(missing_fields)}."
        )
        self.bar_index = bar_index
        self.missing_fields = missing_fields


class OhlcPathModeRequiredError(Exception):
    pass


def select_ohlc_midpoints(
    bar: Bar,
    mode: OHLCPathMode,
    *,
    bar_index: int = 0,
) -> tuple[Decimal, Decimal]:
    open_, high, low = bar.open, bar.high, bar.low
    if open_ is None or high is None or low is None:
        missing = tuple(
            name for name, value in (("open", open_), ("high", high), ("low", low)) if value is None
        )
        raise InvalidOhlcvBarError(bar_index=bar_index, missing_fields=missing)

    if mode is OHLCPathMode.HIGH_FIRST:
        return high, low
    if mode is OHLCPathMode.LOW_FIRST:
        return low, high
    # AUTO: evaluated independently per Bar (SPEC 11.2).
    if bar.close >= open_:
        return low, high
    return high, low


def build_ohlcv_path(bars: Sequence[Bar], mode: OHLCPathMode) -> tuple[PathPoint, ...]:
    if not bars:
        raise EmptyDatasetError("Cannot build a price path from an empty dataset.")

    points: list[PathPoint] = []
    for index, bar in enumerate(bars):
        mid1, mid2 = select_ohlc_midpoints(bar, mode, bar_index=index)
        assert bar.open is not None  # validated by select_ohlc_midpoints
        points.append(PathPoint(price=bar.open, date=bar.date, is_bar_final=False))
        points.append(PathPoint(price=mid1, date=bar.date, is_bar_final=False))
        points.append(PathPoint(price=mid2, date=bar.date, is_bar_final=False))
        points.append(PathPoint(price=bar.close, date=bar.date, is_bar_final=True))
    return tuple(points)


def build_close_only_path(bars: Sequence[Bar]) -> tuple[PathPoint, ...]:
    if not bars:
        raise EmptyDatasetError("Cannot build a price path from an empty dataset.")
    return tuple(PathPoint(price=bar.close, date=bar.date, is_bar_final=True) for bar in bars)


def build_price_path(
    bars: Sequence[Bar],
    data_mode: DataMode,
    *,
    ohlc_path_mode: OHLCPathMode | None = None,
) -> tuple[PathPoint, ...]:
    if data_mode is DataMode.OHLCV:
        if ohlc_path_mode is None:
            raise OhlcPathModeRequiredError("DataMode.OHLCV requires an OHLCPathMode.")
        return build_ohlcv_path(bars, ohlc_path_mode)
    return build_close_only_path(bars)


def build_path_segments(points: Sequence[PathPoint]) -> tuple[PathSegment, ...]:
    if not points:
        raise EmptyDatasetError("Cannot build segments from an empty path.")
    return tuple(
        PathSegment(start=start, end=end) for start, end in zip(points, points[1:], strict=False)
    )


def initialize_path_state(
    points: Sequence[PathPoint],
    boundaries: ZoneBoundaries,
) -> InitialPathState:
    if not points:
        raise EmptyDatasetError("Cannot initialize path state from an empty path.")
    first_price = points[0].price
    return InitialPathState(
        market_cursor=first_price,
        trade_anchor=first_price,
        zone_state=classify_zone(first_price, boundaries),
    )
