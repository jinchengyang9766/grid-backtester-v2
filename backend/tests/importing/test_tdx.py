"""Tests for structural TongdaXin text parsing."""

import pytest
from app.importing.tdx import (
    HeaderNotFoundError,
    RawTdxRow,
    TdxParseResult,
    is_footer_line,
    parse_tdx_text,
)


def test_title_lines_before_header_are_ignored() -> None:
    text = (
        "某ETF(159825)\n"
        "时间\t开盘\t最高\t最低\t收盘\t成交量\n"
        "2020-01-02\t1.0\t1.1\t0.9\t1.05\t1000\n"
    )
    result = parse_tdx_text(text)
    assert result.header == ("时间", "开盘", "最高", "最低", "收盘", "成交量")


def test_first_line_with_two_recognized_headers_becomes_header() -> None:
    text = "junk line with no headers\n时间\t收盘\n2020-01-02\t1.05\n"
    result = parse_tdx_text(text)
    assert result.header == ("时间", "收盘")


def test_chinese_headers_auto_map_correctly() -> None:
    text = "时间\t开盘\t最高\t最低\t收盘\t成交量\n2020-01-02\t1.0\t1.1\t0.9\t1.05\t1000\n"
    result = parse_tdx_text(text)
    assert result.auto_column_mapping == {
        "date": "时间",
        "open": "开盘",
        "high": "最高",
        "low": "最低",
        "close": "收盘",
        "volume": "成交量",
    }


def test_normal_rows_align_positionally() -> None:
    text = "时间\t收盘\n2020-01-02\t1.05\n2020-01-03\t1.10\n"
    result = parse_tdx_text(text)
    assert len(result.rows) == 2
    assert result.rows[0] == RawTdxRow(row_number=1, values={"时间": "2020-01-02", "收盘": "1.05"})
    assert result.rows[1] == RawTdxRow(row_number=2, values={"时间": "2020-01-03", "收盘": "1.10"})


def test_missing_trailing_values_become_empty_strings() -> None:
    text = "时间\t开盘\t收盘\n2020-01-02\t1.0\n"
    result = parse_tdx_text(text)
    assert result.rows[0].values == {"时间": "2020-01-02", "开盘": "1.0", "收盘": ""}


def test_extra_trailing_values_are_ignored() -> None:
    text = "时间\t收盘\n2020-01-02\t1.05\t9999\textra\n"
    result = parse_tdx_text(text)
    assert result.rows[0].values == {"时间": "2020-01-02", "收盘": "1.05"}


def test_blank_lines_do_not_create_rows() -> None:
    text = "时间\t收盘\n2020-01-02\t1.05\n\n\n2020-01-03\t1.10\n"
    result = parse_tdx_text(text)
    assert len(result.rows) == 2
    assert result.rows[0].row_number == 1
    assert result.rows[1].row_number == 2


def test_row_numbering_is_stable_and_one_based() -> None:
    text = "时间\t收盘\n2020-01-02\t1.05\n2020-01-03\t1.10\n2020-01-04\t1.15\n"
    result = parse_tdx_text(text)
    assert [row.row_number for row in result.rows] == [1, 2, 3]


def test_recognized_chinese_footer_stops_parsing() -> None:
    text = "时间\t收盘\n2020-01-02\t1.05\n数据来源：通达信\n2020-01-03\t1.10\n"
    result = parse_tdx_text(text)
    assert len(result.rows) == 1
    assert result.rows[0].values["时间"] == "2020-01-02"


def test_recognized_english_footer_is_case_insensitive() -> None:
    text = "Date\tClose\n2020-01-02\t1.05\nDISCLAIMER: for reference only\n2020-01-03\t1.10\n"
    result = parse_tdx_text(text)
    assert len(result.rows) == 1


def test_short_malformed_row_is_not_treated_as_footer() -> None:
    text = (
        "时间\t开盘\t最高\t最低\t收盘\n"
        "2020-01-02\t1.0\t1.1\t0.9\t1.05\n"
        "badrow\n"
        "2020-01-04\t1.0\t1.1\t0.9\t1.05\n"
    )
    result = parse_tdx_text(text)
    assert len(result.rows) == 3
    assert result.rows[1].values == {
        "时间": "badrow",
        "开盘": "",
        "最高": "",
        "最低": "",
        "收盘": "",
    }


def test_valid_rows_after_malformed_short_row_are_preserved() -> None:
    text = "时间\t收盘\n2020-01-02\t1.05\nx\n2020-01-04\t1.10\n"
    result = parse_tdx_text(text)
    assert len(result.rows) == 3
    assert result.rows[2].values["时间"] == "2020-01-04"


def test_unrecognized_footer_like_text_does_not_stop_parsing() -> None:
    text = "时间\t收盘\n2020-01-02\t1.05\n备注：仅供参考\n2020-01-04\t1.10\n"
    result = parse_tdx_text(text)
    assert len(result.rows) == 3


def test_no_header_input_raises_header_not_found_error() -> None:
    with pytest.raises(HeaderNotFoundError):
        parse_tdx_text("just some random text\nwith no real headers at all\n")


def test_is_footer_line_matches_recognized_markers() -> None:
    assert is_footer_line(["数据来源：通达信"]) is True
    assert is_footer_line(["Disclaimer:", "for reference only"]) is True
    assert is_footer_line(["2020-01-02", "1.05"]) is False


def test_public_imports_work_from_app_importing() -> None:
    import app.importing as importing_pkg

    assert importing_pkg.parse_tdx_text is parse_tdx_text
    assert importing_pkg.RawTdxRow is RawTdxRow
    assert importing_pkg.TdxParseResult is TdxParseResult
    assert importing_pkg.HeaderNotFoundError is HeaderNotFoundError
    assert importing_pkg.is_footer_line is is_footer_line
    assert importing_pkg.DecodedText is not None
    assert importing_pkg.EncodingDetectionError is not None
    assert callable(importing_pkg.auto_map_columns)
    assert callable(importing_pkg.count_recognized_headers)
    assert callable(importing_pkg.decode_tdx_bytes)
    assert callable(importing_pkg.normalize_header)
    assert callable(importing_pkg.recognize_header)
