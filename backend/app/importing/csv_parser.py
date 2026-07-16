"""Structural parsing of decoded CSV market-data text."""

import csv
import io
from dataclasses import dataclass

from app.importing.headers import auto_map_columns

__all__ = [
    "CsvHeaderNotFoundError",
    "CsvParseResult",
    "RawCsvRow",
    "parse_csv_text",
]

_SUPPORTED_DELIMITERS = ",;\t"
_FALLBACK_DELIMITER = ","


class CsvHeaderNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RawCsvRow:
    row_number: int
    values: dict[str, str]


@dataclass(frozen=True, slots=True)
class CsvParseResult:
    header: tuple[str, ...]
    rows: tuple[RawCsvRow, ...]
    auto_column_mapping: dict[str, str]
    delimiter: str


def _detect_delimiter(text: str) -> str:
    first_nonblank_line = next((line for line in text.splitlines() if line.strip() != ""), None)
    if first_nonblank_line is None:
        raise CsvHeaderNotFoundError("CSV text contains no nonblank record.")
    try:
        dialect = csv.Sniffer().sniff(first_nonblank_line, delimiters=_SUPPORTED_DELIMITERS)
    except csv.Error:
        return _FALLBACK_DELIMITER
    return dialect.delimiter


def _is_blank_record(record: list[str]) -> bool:
    return all(cell.strip() == "" for cell in record)


def _align_to_header(record: list[str], header: tuple[str, ...]) -> dict[str, str]:
    return {
        column: (record[index] if index < len(record) else "")
        for index, column in enumerate(header)
    }


def parse_csv_text(text: str) -> CsvParseResult:
    delimiter = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    records = [record for record in reader if not _is_blank_record(record)]
    if not records:
        raise CsvHeaderNotFoundError("CSV text contains no nonblank record.")

    header = tuple(records[0])
    rows = tuple(
        RawCsvRow(row_number=row_number, values=_align_to_header(record, header))
        for row_number, record in enumerate(records[1:], start=1)
    )
    return CsvParseResult(
        header=header,
        rows=rows,
        auto_column_mapping=auto_map_columns(list(header)),
        delimiter=delimiter,
    )
