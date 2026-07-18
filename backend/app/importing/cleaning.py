"""Deterministic cleaning of raw structural-parser rows into immutable Bars."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.domain.enums import DataMode
from app.domain.models import Bar
from app.importing.cleaning_models import (
    DUPLICATE_DATE_DISCARDED,
    BadRow,
    BadRowReason,
    CleaningResult,
    CleaningSummary,
    DateRange,
    DuplicateRow,
)
from app.importing.csv_parser import RawCsvRow
from app.importing.tdx import RawTdxRow

__all__ = [
    "IncompleteOhlcMappingError",
    "MissingRequiredColumnError",
    "clean_rows",
    "determine_data_mode",
]

_DATE_FORMAT = "%Y/%m/%d"
_DATE_PATTERN = re.compile(r"^\d{4}/\d{2}/\d{2}$")
_NUMERIC_PATTERN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_REQUIRED_FIELDS = ("date", "close")
_OHLC_FIELDS = ("open", "high", "low")


class MissingRequiredColumnError(Exception):
    pass


class IncompleteOhlcMappingError(Exception):
    pass


def determine_data_mode(column_mapping: Mapping[str, str]) -> DataMode:
    missing = [field for field in _REQUIRED_FIELDS if field not in column_mapping]
    if missing:
        raise MissingRequiredColumnError(f"Required column(s) not mapped: {', '.join(missing)}.")
    mapped_ohlc = [field for field in _OHLC_FIELDS if field in column_mapping]
    if len(mapped_ohlc) == len(_OHLC_FIELDS):
        return DataMode.OHLCV
    if not mapped_ohlc:
        return DataMode.CLOSE_ONLY
    raise IncompleteOhlcMappingError(
        "Open/High/Low must be mapped together or not at all; "
        f"only mapped: {', '.join(mapped_ohlc)}."
    )


@dataclass(frozen=True, slots=True)
class _ValidRow:
    row_number: int
    date: date
    close: Decimal
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    volume: Decimal | None
    raw: dict[str, str]


def _parse_date(raw: str) -> date | None:
    trimmed = raw.strip()
    if _DATE_PATTERN.match(trimmed) is None:
        return None
    try:
        return datetime.strptime(trimmed, _DATE_FORMAT).date()
    except ValueError:
        return None


def _parse_decimal(raw: str) -> Decimal | None:
    trimmed = raw.strip()
    if _NUMERIC_PATTERN.match(trimmed) is None:
        return None
    return Decimal(trimmed)


def _effective_mapping(
    rows: Sequence[RawTdxRow | RawCsvRow],
    column_mapping: Mapping[str, str],
) -> dict[str, str]:
    if not rows:
        return dict(column_mapping)
    available = rows[0].values.keys()
    return {field: header for field, header in column_mapping.items() if header in available}


def _validate_row(
    row: RawTdxRow | RawCsvRow,
    mapping: Mapping[str, str],
    data_mode: DataMode,
) -> _ValidRow | BadRow:
    raw = dict(row.values)

    def field_text(field: str) -> str:
        header = mapping.get(field)
        return "" if header is None else raw.get(header, "")

    def bad(reason: BadRowReason) -> BadRow:
        return BadRow(row_number=row.row_number, reason=reason, raw=raw)

    parsed_date = _parse_date(field_text("date"))
    if parsed_date is None:
        return bad(BadRowReason.UNPARSEABLE_DATE)

    close = _parse_decimal(field_text("close"))
    if close is None:
        return bad(BadRowReason.MISSING_CLOSE)

    open_: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    if data_mode is DataMode.OHLCV:
        open_ = _parse_decimal(field_text("open"))
        high = _parse_decimal(field_text("high"))
        low = _parse_decimal(field_text("low"))

    present_prices = [price for price in (open_, high, low, close) if price is not None]
    if any(price <= 0 for price in present_prices):
        return bad(BadRowReason.NON_POSITIVE_PRICE)

    if data_mode is DataMode.OHLCV:
        if open_ is None or high is None or low is None:
            return bad(BadRowReason.MISSING_OHLC_FIELD)
        if high < low or high < open_ or high < close or low > open_ or low > close:
            return bad(BadRowReason.INVALID_OHLC_RANGE)

    volume: Decimal | None = None
    volume_text = field_text("volume").strip()
    if volume_text != "":
        volume = _parse_decimal(volume_text)
        if volume is None:
            return bad(BadRowReason.INVALID_VOLUME)
        if volume < 0:
            return bad(BadRowReason.NEGATIVE_VOLUME)

    return _ValidRow(
        row_number=row.row_number,
        date=parsed_date,
        close=close,
        open=open_,
        high=high,
        low=low,
        volume=volume,
        raw=raw,
    )


def _to_bar(row: _ValidRow, data_mode: DataMode) -> Bar:
    if data_mode is DataMode.CLOSE_ONLY:
        return Bar(date=row.date, close=row.close)
    return Bar(
        date=row.date,
        close=row.close,
        open=row.open,
        high=row.high,
        low=row.low,
        volume=row.volume,
    )


def _deduplicate(
    valid_rows: Sequence[_ValidRow],
    data_mode: DataMode,
) -> tuple[tuple[Bar, ...], tuple[DuplicateRow, ...]]:
    rows_by_date: dict[date, list[_ValidRow]] = {}
    for row in valid_rows:
        rows_by_date.setdefault(row.date, []).append(row)

    bars: list[Bar] = []
    duplicates: list[DuplicateRow] = []
    for bar_date in sorted(rows_by_date):
        group = rows_by_date[bar_date]
        kept = max(group, key=lambda row: row.row_number)
        for discarded in sorted(group, key=lambda row: row.row_number):
            if discarded is kept:
                continue
            duplicates.append(
                DuplicateRow(
                    date=bar_date,
                    kept_row_number=kept.row_number,
                    discarded_row_number=discarded.row_number,
                    kept_raw=kept.raw,
                    discarded_raw=discarded.raw,
                    reason=DUPLICATE_DATE_DISCARDED,
                )
            )
        bars.append(_to_bar(kept, data_mode))
    return tuple(bars), tuple(duplicates)


def clean_rows(
    rows: Sequence[RawTdxRow | RawCsvRow],
    column_mapping: Mapping[str, str],
) -> CleaningResult:
    mapping = _effective_mapping(rows, column_mapping)
    data_mode = determine_data_mode(mapping)

    valid_rows: list[_ValidRow] = []
    bad_rows: list[BadRow] = []
    for row in rows:
        validated = _validate_row(row, mapping, data_mode)
        if isinstance(validated, BadRow):
            bad_rows.append(validated)
        else:
            valid_rows.append(validated)

    bars, duplicate_rows = _deduplicate(valid_rows, data_mode)

    reason_counts = {reason: 0 for reason in BadRowReason}
    for bad_row in bad_rows:
        reason_counts[bad_row.reason] += 1

    date_range = DateRange(start=bars[0].date, end=bars[-1].date) if bars else None
    summary = CleaningSummary(
        total_rows_parsed=len(rows),
        valid_rows=len(valid_rows),
        bad_rows=len(bad_rows),
        duplicate_dates=len(duplicate_rows),
        final_row_count=len(bars),
        date_range=date_range,
        data_mode=data_mode,
        bad_row_reasons=reason_counts,
    )
    return CleaningResult(
        data_mode=data_mode,
        bars=bars,
        bad_rows=tuple(bad_rows),
        duplicate_rows=duplicate_rows,
        summary=summary,
    )
