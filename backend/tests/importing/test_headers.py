"""Tests for column-header recognition."""

from app.importing.headers import (
    auto_map_columns,
    count_recognized_headers,
    normalize_header,
    recognize_header,
)


def test_english_headers_match_regardless_of_case() -> None:
    assert recognize_header("Date") == "date"
    assert recognize_header("DATE") == "date"
    assert recognize_header("date") == "date"
    assert recognize_header("Close") == "close"
    assert recognize_header("CLOSE") == "close"


def test_chinese_headers_match_exactly() -> None:
    assert recognize_header("日期") == "date"
    assert recognize_header("时间") == "date"
    assert recognize_header("开盘") == "open"
    assert recognize_header("开盘价") == "open"
    assert recognize_header("最高") == "high"
    assert recognize_header("最高价") == "high"
    assert recognize_header("最低") == "low"
    assert recognize_header("最低价") == "low"
    assert recognize_header("收盘") == "close"
    assert recognize_header("收盘价") == "close"
    assert recognize_header("成交量") == "volume"


def test_whitespace_is_ignored() -> None:
    assert recognize_header("  Date  ") == "date"
    assert recognize_header("\tClose\n") == "close"


def test_bom_is_ignored() -> None:
    assert recognize_header("﻿Date") == "date"
    assert recognize_header("Date﻿") == "date"
    assert normalize_header("﻿日期") == "日期"


def test_unknown_and_indicator_headers_are_not_recognized() -> None:
    assert recognize_header("VOL") is None
    assert recognize_header("MA5") is None
    assert recognize_header("MACD") is None
    assert recognize_header("成交额") is None
    assert recognize_header("涨跌幅") is None
    assert recognize_header("") is None


def test_count_recognized_headers() -> None:
    assert count_recognized_headers(["时间", "开盘", "MA5", "VOL"]) == 2
    assert count_recognized_headers(["MA5", "VOL"]) == 0


def test_auto_map_columns_preserves_original_header_text() -> None:
    mapping = auto_map_columns(["时间", "开盘", "最高", "最低", "收盘", "成交量"])
    assert mapping == {
        "date": "时间",
        "open": "开盘",
        "high": "最高",
        "low": "最低",
        "close": "收盘",
        "volume": "成交量",
    }


def test_auto_map_columns_ignores_unrecognized_headers() -> None:
    mapping = auto_map_columns(["Date", "Close", "MA5", "VOL"])
    assert mapping == {"date": "Date", "close": "Close"}


def test_auto_map_columns_keeps_first_duplicate_source_column() -> None:
    mapping = auto_map_columns(["Date", "date", "Close"])
    assert mapping == {"date": "Date", "close": "Close"}
