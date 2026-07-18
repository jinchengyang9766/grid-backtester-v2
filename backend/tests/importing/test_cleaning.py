"""Tests for the deterministic data-cleaning pipeline."""

from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import DataMode
from app.importing.cleaning import (
    IncompleteOhlcMappingError,
    MissingRequiredColumnError,
    clean_rows,
    determine_data_mode,
)
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

OHLCV_MAPPING: dict[str, str] = {
    "date": "时间",
    "open": "开盘",
    "high": "最高",
    "low": "最低",
    "close": "收盘",
    "volume": "成交量",
}

CLOSE_ONLY_MAPPING: dict[str, str] = {"date": "时间", "close": "Close"}


def ohlcv_row(
    row_number: int,
    date_text: str = "2024/07/23",
    open_text: str = "1.0",
    high_text: str = "2.0",
    low_text: str = "0.5",
    close_text: str = "1.5",
    volume_text: str = "100",
) -> RawTdxRow:
    return RawTdxRow(
        row_number=row_number,
        values={
            "时间": date_text,
            "开盘": open_text,
            "最高": high_text,
            "最低": low_text,
            "收盘": close_text,
            "成交量": volume_text,
        },
    )


def close_only_row(row_number: int, date_text: str, close_text: str = "1.5") -> RawCsvRow:
    return RawCsvRow(row_number=row_number, values={"时间": date_text, "Close": close_text})


def clean_one_close_only(date_text: str, close_text: str = "1.5") -> CleaningResult:
    return clean_rows([close_only_row(1, date_text, close_text)], CLOSE_ONLY_MAPPING)


# ---------------------------------------------------------------------------
# Date handling
# ---------------------------------------------------------------------------


def test_exact_zero_padded_date_is_accepted() -> None:
    result = clean_one_close_only("2024/07/23")
    assert result.bars[0].date == date(2024, 7, 23)
    assert result.bad_rows == ()


def test_date_with_surrounding_whitespace_is_accepted() -> None:
    result = clean_one_close_only("  2024/07/23 \t")
    assert result.bars[0].date == date(2024, 7, 23)


@pytest.mark.parametrize(
    "date_text",
    [
        "2024-07-23",  # ISO dash form
        "20240723",  # digits only
        "2024/7/3",  # unpadded month/day
        "2024/07/23 15:00",  # timestamp
        "2024/07/23 15:00:00",  # timestamp with seconds
        "2024/02/30",  # impossible calendar date
        "",  # blank
        "   ",  # whitespace only
        "07/23/2024",  # month-first
        "23/07/2024",  # day-first
    ],
)
def test_rejected_date_forms(date_text: str) -> None:
    result = clean_one_close_only(date_text)
    assert result.bars == ()
    assert result.bad_rows[0].reason is BadRowReason.UNPARSEABLE_DATE


# ---------------------------------------------------------------------------
# Decimal handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("close_text", ["1", "1.25", "001.0500", " 1.25 "])
def test_accepted_numeric_forms(close_text: str) -> None:
    result = clean_one_close_only("2024/07/23", close_text)
    assert result.bad_rows == ()
    assert result.bars[0].close == Decimal(close_text.strip())


def test_decimal_trailing_zeros_are_preserved_and_float_is_never_used() -> None:
    result = clean_one_close_only("2024/07/23", "001.0500")
    close = result.bars[0].close
    assert type(close) is Decimal
    assert str(close) == "1.0500"


def test_zero_close_parses_but_is_rejected_as_non_positive() -> None:
    result = clean_one_close_only("2024/07/23", "0")
    assert result.bad_rows[0].reason is BadRowReason.NON_POSITIVE_PRICE


def test_negative_close_parses_but_is_rejected_as_non_positive() -> None:
    result = clean_one_close_only("2024/07/23", "-1")
    assert result.bad_rows[0].reason is BadRowReason.NON_POSITIVE_PRICE


@pytest.mark.parametrize(
    "close_text",
    ["1,000", "$1.25", "1%", "1e3", "NaN", "Infinity", ".5", "1.", "", "abc"],
)
def test_rejected_numeric_forms_for_close(close_text: str) -> None:
    result = clean_one_close_only("2024/07/23", close_text)
    assert result.bad_rows[0].reason is BadRowReason.MISSING_CLOSE


# ---------------------------------------------------------------------------
# Column mapping and DataMode
# ---------------------------------------------------------------------------


def test_full_ohlcv_mapping_gives_ohlcv_mode() -> None:
    assert determine_data_mode(OHLCV_MAPPING) is DataMode.OHLCV


def test_date_and_close_only_mapping_gives_close_only_mode() -> None:
    assert determine_data_mode(CLOSE_ONLY_MAPPING) is DataMode.CLOSE_ONLY


def test_ohlcv_mapping_without_volume_is_still_ohlcv() -> None:
    mapping = {field: header for field, header in OHLCV_MAPPING.items() if field != "volume"}
    assert determine_data_mode(mapping) is DataMode.OHLCV


def test_missing_date_mapping_is_rejected() -> None:
    with pytest.raises(MissingRequiredColumnError):
        determine_data_mode({"close": "收盘"})


def test_missing_close_mapping_is_rejected() -> None:
    with pytest.raises(MissingRequiredColumnError):
        determine_data_mode({"date": "时间"})


@pytest.mark.parametrize("partial_fields", [("open",), ("open", "high"), ("high", "low")])
def test_partial_ohlc_mapping_is_rejected_never_close_only(partial_fields: tuple[str, ...]) -> None:
    mapping = {"date": "时间", "close": "收盘"}
    mapping.update({field: OHLCV_MAPPING[field] for field in partial_fields})
    with pytest.raises(IncompleteOhlcMappingError):
        determine_data_mode(mapping)


def test_mapping_to_header_absent_from_rows_is_missing_required() -> None:
    rows = [close_only_row(1, "2024/07/23")]
    with pytest.raises(MissingRequiredColumnError):
        clean_rows(rows, {"date": "时间", "close": "NoSuchHeader"})


def test_ohlc_mapping_to_absent_headers_is_rejected_not_silently_close_only() -> None:
    rows = [RawTdxRow(row_number=1, values={"时间": "2024/07/23", "收盘": "1.5", "开盘": "1.0"})]
    mapping = {"date": "时间", "close": "收盘", "open": "开盘", "high": "最高", "low": "最低"}
    with pytest.raises(IncompleteOhlcMappingError):
        clean_rows(rows, mapping)


# ---------------------------------------------------------------------------
# First-matched-reason ordering
# ---------------------------------------------------------------------------


def test_bad_date_wins_over_bad_close() -> None:
    row = ohlcv_row(1, date_text="not-a-date", close_text="garbage")
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows[0].reason is BadRowReason.UNPARSEABLE_DATE


def test_bad_close_wins_over_negative_ohlc() -> None:
    row = ohlcv_row(1, close_text="garbage", open_text="-1")
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows[0].reason is BadRowReason.MISSING_CLOSE


def test_negative_parsed_ohlc_gives_non_positive_price_before_missing_ohlc() -> None:
    row = ohlcv_row(1, open_text="-1", high_text="garbage")
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows[0].reason is BadRowReason.NON_POSITIVE_PRICE


def test_malformed_ohlc_gives_missing_ohlc_field() -> None:
    row = ohlcv_row(1, high_text="garbage")
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows[0].reason is BadRowReason.MISSING_OHLC_FIELD


def test_blank_ohlc_gives_missing_ohlc_field() -> None:
    row = ohlcv_row(1, low_text="")
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows[0].reason is BadRowReason.MISSING_OHLC_FIELD


@pytest.mark.parametrize(
    ("open_text", "high_text", "low_text", "close_text"),
    [
        ("1.0", "0.9", "1.0", "1.0"),  # High < Low
        ("2.0", "1.5", "1.0", "1.2"),  # High < Open
        ("1.0", "1.5", "0.9", "1.6"),  # High < Close
        ("0.8", "1.5", "0.9", "1.2"),  # Low > Open
        ("1.0", "1.5", "0.9", "0.85"),  # Low > Close
    ],
)
def test_inconsistent_ohlc_gives_invalid_ohlc_range(
    open_text: str, high_text: str, low_text: str, close_text: str
) -> None:
    row = ohlcv_row(
        1, open_text=open_text, high_text=high_text, low_text=low_text, close_text=close_text
    )
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows[0].reason is BadRowReason.INVALID_OHLC_RANGE


@pytest.mark.parametrize("volume_text", ["1e3", "1,000", "NaN", "Infinity", "abc", ".5"])
def test_unparseable_volume_gives_invalid_volume(volume_text: str) -> None:
    row = ohlcv_row(1, volume_text=volume_text)
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows[0].reason is BadRowReason.INVALID_VOLUME


def test_negative_parsed_volume_gives_negative_volume() -> None:
    row = ohlcv_row(1, volume_text="-5")
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows[0].reason is BadRowReason.NEGATIVE_VOLUME


def test_only_one_reason_is_recorded_per_row() -> None:
    row = ohlcv_row(1, date_text="bad", close_text="bad", open_text="-1", volume_text="NaN")
    result = clean_rows([row], OHLCV_MAPPING)
    assert len(result.bad_rows) == 1
    assert result.bad_rows[0].reason is BadRowReason.UNPARSEABLE_DATE


# ---------------------------------------------------------------------------
# Close-only bar construction
# ---------------------------------------------------------------------------


def test_close_only_bar_has_only_date_and_close() -> None:
    result = clean_one_close_only("2024/07/23", "1.0500")
    bar = result.bars[0]
    assert bar.date == date(2024, 7, 23)
    assert bar.close == Decimal("1.0500")
    assert bar.open is None
    assert bar.high is None
    assert bar.low is None
    assert bar.volume is None
    assert result.data_mode is DataMode.CLOSE_ONLY


def test_close_only_ignores_unmapped_source_columns() -> None:
    row = RawCsvRow(
        row_number=1,
        values={"时间": "2024/07/23", "Close": "1.5", "MA5": "whatever", "备注": "x"},
    )
    result = clean_rows([row], CLOSE_ONLY_MAPPING)
    assert result.bad_rows == ()
    assert result.bars[0].close == Decimal("1.5")


# ---------------------------------------------------------------------------
# OHLCV bar construction
# ---------------------------------------------------------------------------


def test_ohlcv_bar_is_complete() -> None:
    row = ohlcv_row(
        1,
        open_text="1.00",
        high_text="2.50",
        low_text="0.50",
        close_text="1.75",
        volume_text="1000",
    )
    result = clean_rows([row], OHLCV_MAPPING)
    bar = result.bars[0]
    assert bar.open == Decimal("1.00")
    assert bar.high == Decimal("2.50")
    assert bar.low == Decimal("0.50")
    assert bar.close == Decimal("1.75")
    assert bar.volume == Decimal("1000")
    assert result.data_mode is DataMode.OHLCV


def test_blank_volume_becomes_none_and_is_valid() -> None:
    row = ohlcv_row(1, volume_text="   ")
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows == ()
    assert result.bars[0].volume is None


def test_zero_volume_is_valid() -> None:
    row = ohlcv_row(1, volume_text="0")
    result = clean_rows([row], OHLCV_MAPPING)
    assert result.bad_rows == ()
    assert result.bars[0].volume == Decimal("0")


# ---------------------------------------------------------------------------
# Pipeline: sorting, duplicates, and summary
# ---------------------------------------------------------------------------


def test_later_rows_survive_earlier_bad_rows() -> None:
    rows = [
        close_only_row(1, "garbage"),
        close_only_row(2, "2024/07/23"),
        close_only_row(3, "also-garbage"),
        close_only_row(4, "2024/07/24"),
    ]
    result = clean_rows(rows, CLOSE_ONLY_MAPPING)
    assert [bar.date for bar in result.bars] == [date(2024, 7, 23), date(2024, 7, 24)]
    assert [bad.row_number for bad in result.bad_rows] == [1, 3]


def test_descending_input_becomes_ascending_output() -> None:
    rows = [
        close_only_row(1, "2024/07/25"),
        close_only_row(2, "2024/07/24"),
        close_only_row(3, "2024/07/23"),
    ]
    result = clean_rows(rows, CLOSE_ONLY_MAPPING)
    assert [bar.date for bar in result.bars] == [
        date(2024, 7, 23),
        date(2024, 7, 24),
        date(2024, 7, 25),
    ]


def test_duplicate_date_keeps_greatest_original_row_number() -> None:
    rows = [
        close_only_row(1, "2024/07/23", "1.0"),
        close_only_row(2, "2024/07/23", "2.0"),
        close_only_row(3, "2024/07/23", "3.0"),
    ]
    result = clean_rows(rows, CLOSE_ONLY_MAPPING)
    assert len(result.bars) == 1
    assert result.bars[0].close == Decimal("3.0")
    assert len(result.duplicate_rows) == 2
    assert [dup.discarded_row_number for dup in result.duplicate_rows] == [1, 2]
    assert all(dup.kept_row_number == 3 for dup in result.duplicate_rows)
    assert all(dup.reason == DUPLICATE_DATE_DISCARDED for dup in result.duplicate_rows)
    assert result.duplicate_rows[0].discarded_raw["Close"] == "1.0"
    assert result.duplicate_rows[0].kept_raw["Close"] == "3.0"


def test_sorting_does_not_change_which_duplicate_is_last_in_file_order() -> None:
    rows = [
        close_only_row(1, "2024/07/24", "9.0"),
        close_only_row(2, "2024/07/23", "1.0"),
        close_only_row(3, "2024/07/25", "5.0"),
        close_only_row(4, "2024/07/23", "2.0"),
    ]
    result = clean_rows(rows, CLOSE_ONLY_MAPPING)
    kept_23 = next(bar for bar in result.bars if bar.date == date(2024, 7, 23))
    assert kept_23.close == Decimal("2.0")
    assert len(result.duplicate_rows) == 1
    assert result.duplicate_rows[0] == DuplicateRow(
        date=date(2024, 7, 23),
        kept_row_number=4,
        discarded_row_number=2,
        kept_raw={"时间": "2024/07/23", "Close": "2.0"},
        discarded_raw={"时间": "2024/07/23", "Close": "1.0"},
        reason=DUPLICATE_DATE_DISCARDED,
    )


def test_summary_counts_satisfy_required_arithmetic() -> None:
    rows = [
        close_only_row(1, "garbage"),
        close_only_row(2, "2024/07/23", "1.0"),
        close_only_row(3, "2024/07/23", "2.0"),
        close_only_row(4, "2024/07/24"),
    ]
    result = clean_rows(rows, CLOSE_ONLY_MAPPING)
    summary = result.summary
    assert summary.total_rows_parsed == 4
    assert summary.bad_rows == 1
    assert summary.valid_rows == 3
    assert summary.duplicate_dates == 1
    assert summary.final_row_count == 2
    assert summary.final_row_count == summary.valid_rows - summary.duplicate_dates
    assert summary.duplicate_dates == len(result.duplicate_rows)


def test_date_range_uses_final_bars() -> None:
    rows = [
        close_only_row(1, "2024/07/25"),
        close_only_row(2, "2024/07/23"),
        close_only_row(3, "bad-date"),
    ]
    result = clean_rows(rows, CLOSE_ONLY_MAPPING)
    assert result.summary.date_range == DateRange(start=date(2024, 7, 23), end=date(2024, 7, 25))


def test_empty_final_result_has_none_date_range() -> None:
    rows = [close_only_row(1, "garbage")]
    result = clean_rows(rows, CLOSE_ONLY_MAPPING)
    assert result.bars == ()
    assert result.summary.date_range is None
    assert result.summary.final_row_count == 0


def test_empty_input_produces_empty_result() -> None:
    result = clean_rows([], CLOSE_ONLY_MAPPING)
    assert result.bars == ()
    assert result.summary.total_rows_parsed == 0
    assert result.summary.date_range is None


def test_summary_includes_zero_counts_for_every_reason() -> None:
    rows = [close_only_row(1, "garbage"), close_only_row(2, "2024/07/23")]
    result = clean_rows(rows, CLOSE_ONLY_MAPPING)
    reasons = result.summary.bad_row_reasons
    assert set(reasons) == set(BadRowReason)
    assert reasons[BadRowReason.UNPARSEABLE_DATE] == 1
    assert reasons[BadRowReason.NEGATIVE_VOLUME] == 0
    assert reasons[BadRowReason.INVALID_VOLUME] == 0


def test_bad_row_preserves_raw_values_and_stable_row_number() -> None:
    row = ohlcv_row(7, date_text="garbage")
    result = clean_rows([row], OHLCV_MAPPING)
    bad = result.bad_rows[0]
    assert bad == BadRow(row_number=7, reason=BadRowReason.UNPARSEABLE_DATE, raw=row.values)


def test_raw_tdx_and_raw_csv_rows_both_work() -> None:
    tdx_result = clean_rows([ohlcv_row(1)], OHLCV_MAPPING)
    csv_result = clean_rows([close_only_row(1, "2024/07/23")], CLOSE_ONLY_MAPPING)
    assert tdx_result.summary.final_row_count == 1
    assert csv_result.summary.final_row_count == 1


def test_summary_data_mode_matches_result_data_mode() -> None:
    result = clean_rows([ohlcv_row(1)], OHLCV_MAPPING)
    assert result.summary.data_mode is result.data_mode is DataMode.OHLCV
    assert isinstance(result.summary, CleaningSummary)


def test_public_imports_work_from_app_importing() -> None:
    import app.importing as importing_pkg

    assert importing_pkg.clean_rows is clean_rows
    assert importing_pkg.determine_data_mode is determine_data_mode
    assert importing_pkg.BadRow is BadRow
    assert importing_pkg.BadRowReason is BadRowReason
    assert importing_pkg.CleaningResult is CleaningResult
    assert importing_pkg.CleaningSummary is CleaningSummary
    assert importing_pkg.DateRange is DateRange
    assert importing_pkg.DuplicateRow is DuplicateRow
    assert importing_pkg.DUPLICATE_DATE_DISCARDED == DUPLICATE_DATE_DISCARDED
    assert importing_pkg.MissingRequiredColumnError is MissingRequiredColumnError
    assert importing_pkg.IncompleteOhlcMappingError is IncompleteOhlcMappingError
