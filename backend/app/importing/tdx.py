"""Structural parsing of raw TongdaXin tab-delimited text exports."""

from dataclasses import dataclass

from app.importing.headers import auto_map_columns, count_recognized_headers

__all__ = [
    "HeaderNotFoundError",
    "RawTdxRow",
    "TdxParseResult",
    "is_footer_line",
    "parse_tdx_text",
]

_FOOTER_MARKERS: tuple[str, ...] = (
    "数据来源",
    "来源：",
    "来源:",
    "免责声明",
    "以上数据",
    "disclaimer",
    "source:",
)

_MIN_HEADER_MATCHES = 2


class HeaderNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RawTdxRow:
    row_number: int
    values: dict[str, str]


@dataclass(frozen=True, slots=True)
class TdxParseResult:
    header: tuple[str, ...]
    rows: tuple[RawTdxRow, ...]
    auto_column_mapping: dict[str, str]


def is_footer_line(tokens: list[str]) -> bool:
    joined = "".join(tokens).strip().lower()
    return any(marker.lower() in joined for marker in _FOOTER_MARKERS)


def _align_to_header(tokens: list[str], header: tuple[str, ...]) -> dict[str, str]:
    return {
        column: (tokens[index] if index < len(tokens) else "")
        for index, column in enumerate(header)
    }


def parse_tdx_text(text: str) -> TdxParseResult:
    lines = [line.split("\t") for line in text.splitlines() if line.strip() != ""]

    header_index: int | None = None
    for index, tokens in enumerate(lines):
        if count_recognized_headers(tokens) >= _MIN_HEADER_MATCHES:
            header_index = index
            break
    if header_index is None:
        raise HeaderNotFoundError("No line with at least two recognized column headers was found.")

    header = tuple(lines[header_index])
    rows: list[RawTdxRow] = []
    for row_number, tokens in enumerate(lines[header_index + 1 :], start=1):
        if is_footer_line(tokens):
            break
        rows.append(RawTdxRow(row_number=row_number, values=_align_to_header(tokens, header)))

    return TdxParseResult(
        header=header,
        rows=tuple(rows),
        auto_column_mapping=auto_map_columns(list(header)),
    )
