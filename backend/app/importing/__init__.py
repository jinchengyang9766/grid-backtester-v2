"""Header recognition, encoding detection, raw parsing, and deterministic cleaning."""

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
from app.importing.csv_parser import (
    CsvHeaderNotFoundError,
    CsvParseResult,
    RawCsvRow,
    parse_csv_text,
)
from app.importing.encoding import DecodedText, EncodingDetectionError, decode_tdx_bytes
from app.importing.headers import (
    auto_map_columns,
    count_recognized_headers,
    normalize_header,
    recognize_header,
)
from app.importing.tdx import (
    HeaderNotFoundError,
    RawTdxRow,
    TdxParseResult,
    is_footer_line,
    parse_tdx_text,
)

__all__ = [
    "BadRow",
    "BadRowReason",
    "CleaningResult",
    "CleaningSummary",
    "CsvHeaderNotFoundError",
    "CsvParseResult",
    "DUPLICATE_DATE_DISCARDED",
    "DateRange",
    "DecodedText",
    "DuplicateRow",
    "EncodingDetectionError",
    "HeaderNotFoundError",
    "IncompleteOhlcMappingError",
    "MissingRequiredColumnError",
    "RawCsvRow",
    "RawTdxRow",
    "TdxParseResult",
    "auto_map_columns",
    "clean_rows",
    "count_recognized_headers",
    "decode_tdx_bytes",
    "determine_data_mode",
    "is_footer_line",
    "normalize_header",
    "parse_csv_text",
    "parse_tdx_text",
    "recognize_header",
]
