"""Tests for structural CSV text parsing."""

import pytest
from app.importing.csv_parser import (
    CsvHeaderNotFoundError,
    CsvParseResult,
    RawCsvRow,
    parse_csv_text,
)


def test_normal_comma_separated_csv() -> None:
    text = "Date,Open,High,Low,Close,Volume\n2020-01-02,1.0,1.1,0.9,1.05,1000\n"
    result = parse_csv_text(text)
    assert result.delimiter == ","
    assert result.header == ("Date", "Open", "High", "Low", "Close", "Volume")
    assert len(result.rows) == 1
    assert result.rows[0].values == {
        "Date": "2020-01-02",
        "Open": "1.0",
        "High": "1.1",
        "Low": "0.9",
        "Close": "1.05",
        "Volume": "1000",
    }


def test_semicolon_delimiter_detection() -> None:
    text = "Date;Close\n2020-01-02;1.05\n"
    result = parse_csv_text(text)
    assert result.delimiter == ";"
    assert result.rows[0].values == {"Date": "2020-01-02", "Close": "1.05"}


def test_tab_delimiter_detection() -> None:
    text = "Date\tClose\n2020-01-02\t1.05\n"
    result = parse_csv_text(text)
    assert result.delimiter == "\t"
    assert result.rows[0].values == {"Date": "2020-01-02", "Close": "1.05"}


def test_comma_fallback_when_sniffer_fails() -> None:
    text = "Date\n2020-01-02\n2020-01-03\n"
    result = parse_csv_text(text)
    assert result.delimiter == ","
    assert result.header == ("Date",)
    assert [row.values["Date"] for row in result.rows] == ["2020-01-02", "2020-01-03"]


def test_leading_blank_lines_before_header() -> None:
    text = "\n   \nDate,Close\n2020-01-02,1.05\n"
    result = parse_csv_text(text)
    assert result.header == ("Date", "Close")
    assert len(result.rows) == 1


def test_first_nonblank_record_is_always_the_header() -> None:
    text = "Some Title\nDate,Close\n2020-01-02,1.05\n"
    result = parse_csv_text(text)
    assert result.header == ("Some Title",)
    assert result.rows[0].values == {"Some Title": "Date"}


def test_english_header_automatic_mapping() -> None:
    text = "DATE,open,High,LOW,Close,Volume\n2020-01-02,1.0,1.1,0.9,1.05,1000\n"
    result = parse_csv_text(text)
    assert result.auto_column_mapping == {
        "date": "DATE",
        "open": "open",
        "high": "High",
        "low": "LOW",
        "close": "Close",
        "volume": "Volume",
    }


def test_chinese_header_automatic_mapping() -> None:
    text = "日期,开盘,最高,最低,收盘,成交量\n2020-01-02,1.0,1.1,0.9,1.05,1000\n"
    result = parse_csv_text(text)
    assert result.delimiter == ","
    assert result.auto_column_mapping == {
        "date": "日期",
        "open": "开盘",
        "high": "最高",
        "low": "最低",
        "close": "收盘",
        "volume": "成交量",
    }


def test_original_header_text_is_preserved() -> None:
    text = "DATE,Close Price,收盘\n2020-01-02,x,1.05\n"
    result = parse_csv_text(text)
    assert result.header == ("DATE", "Close Price", "收盘")
    assert "DATE" in result.rows[0].values
    assert "Close Price" in result.rows[0].values


def test_quoted_comma_inside_field_is_preserved() -> None:
    text = 'Date,Close,Note\n2020-01-02,1.05,"hello, world"\n'
    result = parse_csv_text(text)
    assert result.rows[0].values["Note"] == "hello, world"


def test_quoted_semicolon_inside_semicolon_delimited_file() -> None:
    text = 'Date;Close;Note\n2020-01-02;1.05;"a;b"\n'
    result = parse_csv_text(text)
    assert result.delimiter == ";"
    assert result.rows[0].values["Note"] == "a;b"


def test_missing_trailing_values_become_empty_strings() -> None:
    text = "Date,Open,Close\n2020-01-02,1.0\n"
    result = parse_csv_text(text)
    assert result.rows[0].values == {"Date": "2020-01-02", "Open": "1.0", "Close": ""}


def test_extra_trailing_values_are_ignored() -> None:
    text = "Date,Close\n2020-01-02,1.05,9999,extra\n"
    result = parse_csv_text(text)
    assert result.rows[0].values == {"Date": "2020-01-02", "Close": "1.05"}


def test_completely_blank_records_are_ignored() -> None:
    text = "Date,Close\n2020-01-02,1.05\n\n , \n2020-01-03,1.10\n"
    result = parse_csv_text(text)
    assert len(result.rows) == 2
    assert result.rows[0].row_number == 1
    assert result.rows[1].row_number == 2


def test_partially_populated_records_are_retained() -> None:
    text = "Date,Open,Close\n2020-01-02,,1.05\n"
    result = parse_csv_text(text)
    assert len(result.rows) == 1
    assert result.rows[0].values == {"Date": "2020-01-02", "Open": "", "Close": "1.05"}


def test_stable_one_based_row_numbering() -> None:
    text = "Date,Close\n2020-01-02,1.05\n2020-01-03,1.10\n2020-01-06,1.15\n"
    result = parse_csv_text(text)
    assert [row.row_number for row in result.rows] == [1, 2, 3]


def test_footer_like_text_is_retained_as_ordinary_row() -> None:
    text = "Date,Close\n2020-01-02,1.05\n数据来源：通达信\n2020-01-03,1.10\n"
    result = parse_csv_text(text)
    assert len(result.rows) == 3
    assert result.rows[1].values == {"Date": "数据来源：通达信", "Close": ""}
    assert result.rows[2].values["Date"] == "2020-01-03"


def test_no_recognized_headers_required_at_structural_parse_time() -> None:
    text = "colA,colB\nfoo,bar\n"
    result = parse_csv_text(text)
    assert result.header == ("colA", "colB")
    assert result.auto_column_mapping == {}
    assert len(result.rows) == 1


def test_empty_input_raises_header_not_found() -> None:
    with pytest.raises(CsvHeaderNotFoundError):
        parse_csv_text("")


def test_blank_only_input_raises_header_not_found() -> None:
    with pytest.raises(CsvHeaderNotFoundError):
        parse_csv_text("\n   \n\t\n")


def test_delimiter_only_records_raise_header_not_found() -> None:
    with pytest.raises(CsvHeaderNotFoundError):
        parse_csv_text(" , \n,,\n")


def test_no_date_or_decimal_conversion_occurs() -> None:
    text = "Date,Close\n2020/01/02, 1.0500\n"
    result = parse_csv_text(text)
    values = result.rows[0].values
    assert values["Date"] == "2020/01/02"
    assert values["Close"] == " 1.0500"
    assert isinstance(values["Date"], str)
    assert isinstance(values["Close"], str)


def test_public_imports_work_from_app_importing() -> None:
    import app.importing as importing_pkg

    assert importing_pkg.parse_csv_text is parse_csv_text
    assert importing_pkg.RawCsvRow is RawCsvRow
    assert importing_pkg.CsvParseResult is CsvParseResult
    assert importing_pkg.CsvHeaderNotFoundError is CsvHeaderNotFoundError
