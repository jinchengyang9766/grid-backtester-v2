"""Immutable result models produced by the deterministic data-cleaning pipeline."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from app.domain.enums import DataMode
from app.domain.models import Bar

__all__ = [
    "BadRow",
    "BadRowReason",
    "CleaningResult",
    "CleaningSummary",
    "DUPLICATE_DATE_DISCARDED",
    "DateRange",
    "DuplicateRow",
]


class BadRowReason(StrEnum):
    UNPARSEABLE_DATE = "UNPARSEABLE_DATE"
    MISSING_CLOSE = "MISSING_CLOSE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    MISSING_OHLC_FIELD = "MISSING_OHLC_FIELD"
    INVALID_OHLC_RANGE = "INVALID_OHLC_RANGE"
    INVALID_VOLUME = "INVALID_VOLUME"
    NEGATIVE_VOLUME = "NEGATIVE_VOLUME"


DUPLICATE_DATE_DISCARDED: Final[str] = "DUPLICATE_DATE_DISCARDED"


@dataclass(frozen=True, slots=True)
class BadRow:
    row_number: int
    reason: BadRowReason
    raw: dict[str, str]


@dataclass(frozen=True, slots=True)
class DuplicateRow:
    date: date
    kept_row_number: int
    discarded_row_number: int
    kept_raw: dict[str, str]
    discarded_raw: dict[str, str]
    reason: str


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class CleaningSummary:
    total_rows_parsed: int
    valid_rows: int
    bad_rows: int
    duplicate_dates: int
    final_row_count: int
    date_range: DateRange | None
    data_mode: DataMode
    bad_row_reasons: dict[BadRowReason, int]


@dataclass(frozen=True, slots=True)
class CleaningResult:
    data_mode: DataMode
    bars: tuple[Bar, ...]
    bad_rows: tuple[BadRow, ...]
    duplicate_rows: tuple[DuplicateRow, ...]
    summary: CleaningSummary
