"""Dataset preview/save request and response schemas (SPEC Section 25.2).

All Decimal values serialize as JSON strings (never floats) and all dates
as ISO YYYY-MM-DD. The response never exposes the source content hash,
owner user ID, raw file content, or cache expiry internals.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.datasets.preview_models import PreviewCacheEntry
from app.domain.models import Bar
from app.importing import BadRow, CleaningSummary, DuplicateRow

__all__ = [
    "DatasetDetailResponse",
    "DatasetListResponse",
    "DatasetPreviewResponse",
    "DatasetSaveRequest",
    "DatasetSavedResponse",
    "DatasetSummaryModel",
]

_PREVIEW_HEAD_TAIL = 50


def _decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


class PreviewBarModel(BaseModel):
    date: date
    open: str | None
    high: str | None
    low: str | None
    close: str
    volume: str | None

    @classmethod
    def from_bar(cls, bar: Bar) -> Self:
        return cls(
            date=bar.date,
            open=_decimal_string(bar.open),
            high=_decimal_string(bar.high),
            low=_decimal_string(bar.low),
            close=str(bar.close),
            volume=_decimal_string(bar.volume),
        )


class BadRowModel(BaseModel):
    row_number: int
    reason: str
    raw: dict[str, str]

    @classmethod
    def from_bad_row(cls, bad_row: BadRow) -> Self:
        return cls(row_number=bad_row.row_number, reason=bad_row.reason.value, raw=bad_row.raw)


class DuplicateRowModel(BaseModel):
    date: date
    kept_row_number: int
    discarded_row_number: int
    kept_raw: dict[str, str]
    discarded_raw: dict[str, str]
    reason: str

    @classmethod
    def from_duplicate_row(cls, duplicate: DuplicateRow) -> Self:
        return cls(
            date=duplicate.date,
            kept_row_number=duplicate.kept_row_number,
            discarded_row_number=duplicate.discarded_row_number,
            kept_raw=duplicate.kept_raw,
            discarded_raw=duplicate.discarded_raw,
            reason=duplicate.reason,
        )


class DateRangeModel(BaseModel):
    start: date
    end: date


class CleaningSummaryModel(BaseModel):
    total_rows_parsed: int
    valid_rows: int
    bad_rows: int
    duplicate_dates: int
    final_row_count: int
    date_range: DateRangeModel | None
    data_mode: str
    bad_row_reasons: dict[str, int]

    @classmethod
    def from_summary(cls, summary: CleaningSummary) -> Self:
        date_range = (
            None
            if summary.date_range is None
            else DateRangeModel(start=summary.date_range.start, end=summary.date_range.end)
        )
        return cls(
            total_rows_parsed=summary.total_rows_parsed,
            valid_rows=summary.valid_rows,
            bad_rows=summary.bad_rows,
            duplicate_dates=summary.duplicate_dates,
            final_row_count=summary.final_row_count,
            date_range=date_range,
            data_mode=summary.data_mode.value,
            bad_row_reasons={
                reason.value: count for reason, count in summary.bad_row_reasons.items()
            },
        )


def _select_preview_bars(bars: tuple[Bar, ...]) -> list[Bar]:
    if len(bars) <= 2 * _PREVIEW_HEAD_TAIL:
        return list(bars)
    return list(bars[:_PREVIEW_HEAD_TAIL]) + list(bars[-_PREVIEW_HEAD_TAIL:])


class DatasetPreviewResponse(BaseModel):
    detected_format: str
    detected_encoding: str
    auto_column_mapping: dict[str, str]
    column_mapping_used: dict[str, str]
    security_name: str | None
    security_code: str | None
    data_mode: str
    preview_rows: list[PreviewBarModel]
    bad_rows: list[BadRowModel]
    duplicate_rows: list[DuplicateRowModel]
    cleaning_summary: CleaningSummaryModel
    preview_token: str

    @classmethod
    def from_entry(cls, entry: PreviewCacheEntry, token: str) -> Self:
        return cls(
            detected_format=entry.detected_format,
            detected_encoding=entry.detected_encoding,
            auto_column_mapping=entry.auto_column_mapping,
            column_mapping_used=entry.column_mapping_used,
            security_name=entry.security_name,
            security_code=entry.security_code,
            data_mode=entry.data_mode.value,
            preview_rows=[
                PreviewBarModel.from_bar(bar) for bar in _select_preview_bars(entry.bars)
            ],
            bad_rows=[BadRowModel.from_bad_row(bad_row) for bad_row in entry.bad_rows],
            duplicate_rows=[
                DuplicateRowModel.from_duplicate_row(duplicate)
                for duplicate in entry.duplicate_rows
            ],
            cleaning_summary=CleaningSummaryModel.from_summary(entry.cleaning_summary),
            preview_token=token,
        )


class DatasetSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    preview_token: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _name_has_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must contain at least one non-whitespace character")
        return value


class DatasetSavedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    data_mode: str
    start_date: date
    end_date: date
    row_count: int
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _ensure_timezone_aware(cls, value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class DatasetSummaryModel(BaseModel):
    """Dataset list item: metadata only — never user_id, mappings, or bars."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: str
    original_filename: str
    security_name: str | None
    security_code: str | None
    data_mode: str
    start_date: date
    end_date: date
    row_count: int
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _ensure_timezone_aware(cls, value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class DatasetListResponse(BaseModel):
    items: list[DatasetSummaryModel]


class DatasetDetailResponse(DatasetSummaryModel):
    """Summary fields plus the structured JSON columns; still no PriceBars."""

    column_mapping: dict[str, Any]
    cleaning_summary: dict[str, Any]
