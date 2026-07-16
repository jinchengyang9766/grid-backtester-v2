"""Header recognition, encoding detection, and raw TongdaXin/CSV text parsing."""

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
    "CsvHeaderNotFoundError",
    "CsvParseResult",
    "DecodedText",
    "EncodingDetectionError",
    "HeaderNotFoundError",
    "RawCsvRow",
    "RawTdxRow",
    "TdxParseResult",
    "auto_map_columns",
    "count_recognized_headers",
    "decode_tdx_bytes",
    "is_footer_line",
    "normalize_header",
    "parse_csv_text",
    "parse_tdx_text",
    "recognize_header",
]
