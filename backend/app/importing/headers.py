"""Column-header recognition for uploaded market-data files."""

__all__ = [
    "auto_map_columns",
    "count_recognized_headers",
    "normalize_header",
    "recognize_header",
]

_BOM = "﻿"

_RECOGNIZED_HEADERS: dict[str, tuple[str, ...]] = {
    "date": ("Date", "date", "日期", "时间"),
    "open": ("Open", "open", "开盘", "开盘价"),
    "high": ("High", "high", "最高", "最高价"),
    "low": ("Low", "low", "最低", "最低价"),
    "close": ("Close", "close", "收盘", "收盘价"),
    "volume": ("Volume", "volume", "成交量"),
}


def normalize_header(value: str) -> str:
    value = value.strip()
    value = value.strip(_BOM)
    value = value.strip()
    return value.casefold()


_NORMALIZED_TO_FIELD: dict[str, str] = {
    normalize_header(header): field
    for field, headers in _RECOGNIZED_HEADERS.items()
    for header in headers
}


def recognize_header(value: str) -> str | None:
    return _NORMALIZED_TO_FIELD.get(normalize_header(value))


def auto_map_columns(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        field = recognize_header(header)
        if field is None or field in mapping:
            continue
        mapping[field] = header
    return mapping


def count_recognized_headers(headers: list[str]) -> int:
    return sum(1 for header in headers if recognize_header(header) is not None)
