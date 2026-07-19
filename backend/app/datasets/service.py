"""Dataset preview and save service (SPEC Sections 2-5, 25.2).

Connects the pure importing pipeline (decoding, parsing, mapping, cleaning)
to the preview cache and the persistence models. Parsing and cleaning run
only at preview time; saving persists exactly the cached cleaned Bars and
never re-parses, re-cleans, or reinterprets cached content.
"""

import hashlib
import json
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.datasets.preview_cache import PREVIEW_TOKEN_TTL, PreviewCache
from app.datasets.preview_models import PreviewCacheEntry
from app.db.models import Dataset, PriceBar
from app.importing import (
    CleaningSummary,
    CsvHeaderNotFoundError,
    CsvParseResult,
    EncodingDetectionError,
    HeaderNotFoundError,
    IncompleteOhlcMappingError,
    MissingRequiredColumnError,
    TdxParseResult,
    clean_rows,
    count_recognized_headers,
    decode_tdx_bytes,
    determine_data_mode,
    parse_csv_text,
    parse_tdx_text,
)

__all__ = [
    "build_preview_entry",
    "cleaning_summary_to_json",
    "sanitize_filename",
    "save_dataset",
]

TDX_FORMAT = "TDX_XLS"
CSV_FORMAT = "CSV"

_CANONICAL_FIELDS = ("date", "open", "high", "low", "close", "volume")
_REQUIRED_FIELDS = ("date", "close")
_OHLC_FIELDS = ("open", "high", "low")

# Real binary spreadsheet containers renamed to .xls are rejected: only the
# TongdaXin tab-separated *text* export is supported (SPEC 2.1).
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

_MIN_HEADER_MATCHES = 2
_TITLE_PATTERN = re.compile(r"^(?P<name>.+?)\s*[（(](?P<code>\d{6})[）)]$")
_CODE_PATTERN = re.compile(r"^\d{6}$")


def _validation_error(message: str, details: dict[str, object] | None = None) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, details)


def sanitize_filename(filename: str) -> str:
    """Return only the basename, supporting both slash styles."""
    basename = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    return basename or "upload"


def _detect_format(basename: str, raw: bytes) -> str:
    extension = basename.rsplit(".", maxsplit=1)[-1].lower() if "." in basename else ""
    if extension == "csv":
        return CSV_FORMAT
    if extension == "xls":
        if raw.startswith(_OLE2_MAGIC) or raw.startswith(_ZIP_MAGICS):
            raise ApiError(
                400,
                "UNSUPPORTED_FILE_TYPE",
                "Only TongdaXin text-export .xls files are supported, "
                "not binary spreadsheet files.",
            )
        return TDX_FORMAT
    raise ApiError(
        400,
        "UNSUPPORTED_FILE_TYPE",
        "Unsupported file type; upload a TongdaXin text-export .xls or a .csv file.",
    )


def _extract_security_metadata(text: str) -> tuple[str | None, str | None]:
    """Best-effort SPEC 3.4 title-line extraction, reusing the importing
    package's public header recognition (no importing module is modified)."""
    for line in text.splitlines():
        if line.strip() == "":
            continue
        tokens = line.split("\t")
        if count_recognized_headers(tokens) >= _MIN_HEADER_MATCHES:
            return None, None  # reached the header row without a title line
        nonblank = [token.strip() for token in tokens if token.strip() != ""]
        if len(nonblank) == 2 and _CODE_PATTERN.match(nonblank[1]):
            return nonblank[0], nonblank[1]
        matched = _TITLE_PATTERN.match(" ".join(nonblank).strip())
        if matched:
            return matched.group("name").strip(), matched.group("code")
    return None, None


def _parse_manual_mapping(manual_mapping_json: str) -> dict[str, str | None]:
    try:
        parsed = json.loads(manual_mapping_json)
    except json.JSONDecodeError as error:
        raise _validation_error("manual_mapping is not valid JSON.") from error
    if not isinstance(parsed, dict):
        raise _validation_error("manual_mapping must be a JSON object.")
    unknown_fields = sorted(key for key in parsed if key not in _CANONICAL_FIELDS)
    if unknown_fields:
        raise _validation_error(
            "manual_mapping keys must be canonical fields.",
            {"unknown_fields": unknown_fields},
        )
    for key, value in parsed.items():
        if value is not None and not isinstance(value, str):
            raise _validation_error(
                "manual_mapping values must be source-header strings or null.",
                {"field": key},
            )
    return {key: value for key, value in parsed.items()}


def _merge_mapping(
    auto_mapping: dict[str, str],
    manual_mapping_json: str | None,
    header: tuple[str, ...],
) -> dict[str, str]:
    merged = dict(auto_mapping)
    if manual_mapping_json is not None:
        for field, source_header in _parse_manual_mapping(manual_mapping_json).items():
            if source_header is None:
                merged.pop(field, None)
            else:
                merged[field] = source_header

    unknown_headers = sorted({value for value in merged.values() if value not in header})
    if unknown_headers:
        raise _validation_error(
            "Mapped source header(s) are not present in the file header.",
            {"unknown_headers": unknown_headers},
        )
    seen: dict[str, str] = {}
    for field in _CANONICAL_FIELDS:
        source_header = merged.get(field)
        if source_header is None:
            continue
        if source_header in seen:
            raise _validation_error(
                "One source column must not map to more than one field.",
                {"source_header": source_header, "fields": [seen[source_header], field]},
            )
        seen[source_header] = field

    try:
        determine_data_mode(merged)
    except MissingRequiredColumnError as error:
        raise ApiError(
            400,
            "MISSING_REQUIRED_COLUMN",
            "Date and Close must both be mapped.",
            {"missing_fields": [field for field in _REQUIRED_FIELDS if field not in merged]},
        ) from error
    except IncompleteOhlcMappingError as error:
        raise ApiError(
            400,
            "MISSING_REQUIRED_COLUMN",
            "Open/High/Low must be mapped together or not at all.",
            {"partial_ohlc_fields": [field for field in _OHLC_FIELDS if field in merged]},
        ) from error
    return merged


def build_preview_entry(
    *,
    raw: bytes,
    filename: str,
    manual_mapping_json: str | None,
    owner_user_id: int,
    now: datetime | None = None,
) -> PreviewCacheEntry:
    """Decode, parse, map, and clean one upload into a cache-ready entry."""
    basename = sanitize_filename(filename)
    detected_format = _detect_format(basename, raw)

    try:
        decoded = decode_tdx_bytes(raw)
    except EncodingDetectionError as error:
        raise ApiError(
            400,
            "ENCODING_DETECTION_FAILED",
            "The file could not be decoded as UTF-8 or GB18030 text.",
        ) from error

    security_name: str | None = None
    security_code: str | None = None
    parsed: TdxParseResult | CsvParseResult
    try:
        if detected_format == TDX_FORMAT:
            parsed = parse_tdx_text(decoded.text)
            security_name, security_code = _extract_security_metadata(decoded.text)
        else:
            parsed = parse_csv_text(decoded.text)
    except (HeaderNotFoundError, CsvHeaderNotFoundError) as error:
        raise ApiError(
            400,
            "HEADER_NOT_FOUND",
            "No recognizable column-header row was found in the file.",
        ) from error

    auto_mapping = dict(parsed.auto_column_mapping)
    mapping_used = _merge_mapping(auto_mapping, manual_mapping_json, parsed.header)
    cleaning = clean_rows(parsed.rows, mapping_used)
    if not cleaning.bars:
        raise _validation_error("No valid rows remain after cleaning.")

    created_at = now if now is not None else datetime.now(UTC)
    return PreviewCacheEntry(
        owner_user_id=owner_user_id,
        source_content_hash=hashlib.sha256(decoded.text.encode("utf-8")).hexdigest(),
        original_filename=basename,
        detected_format=detected_format,
        detected_encoding=decoded.encoding,
        security_name=security_name,
        security_code=security_code,
        auto_column_mapping=auto_mapping,
        column_mapping_used=mapping_used,
        data_mode=cleaning.data_mode,
        bars=cleaning.bars,
        bad_rows=cleaning.bad_rows,
        duplicate_rows=cleaning.duplicate_rows,
        cleaning_summary=cleaning.summary,
        created_at=created_at,
        expires_at=created_at + PREVIEW_TOKEN_TTL,
    )


def cleaning_summary_to_json(summary: CleaningSummary) -> dict[str, object]:
    """SPEC 5.4 JSON shape, including every reason key even at zero."""
    date_range: dict[str, str] | None = None
    if summary.date_range is not None:
        date_range = {
            "start": summary.date_range.start.isoformat(),
            "end": summary.date_range.end.isoformat(),
        }
    return {
        "total_rows_parsed": summary.total_rows_parsed,
        "valid_rows": summary.valid_rows,
        "bad_rows": summary.bad_rows,
        "duplicate_dates": summary.duplicate_dates,
        "final_row_count": summary.final_row_count,
        "date_range": date_range,
        "data_mode": summary.data_mode.value,
        "bad_row_reasons": {
            reason.value: count for reason, count in summary.bad_row_reasons.items()
        },
    }


def _token_not_found() -> ApiError:
    # Identical response for unknown, expired, consumed, and wrong-owner
    # tokens — never reveal token state or ownership.
    return ApiError(404, "PREVIEW_TOKEN_NOT_FOUND", "Preview token not found or expired.")


def save_dataset(
    session: Session,
    cache: PreviewCache,
    *,
    token: str,
    name: str,
    owner_user_id: int,
) -> Dataset:
    """Persist one Dataset plus all its PriceBars from a cached preview.

    The token is consumed atomically up front; on any persistence failure
    the transaction rolls back and the unexpired token is restored, so a
    temporary database outage never burns a valid preview. The cache lock
    is never held while the database transaction runs.
    """
    entry = cache.pop_for_owner(token, owner_user_id)
    if entry is None:
        raise _token_not_found()

    try:
        dataset = Dataset(
            user_id=owner_user_id,
            name=name.strip(),
            source_type=entry.detected_format,
            original_filename=entry.original_filename,
            security_name=entry.security_name,
            security_code=entry.security_code,
            data_mode=entry.data_mode.value,
            start_date=entry.bars[0].date,
            end_date=entry.bars[-1].date,
            row_count=len(entry.bars),
            column_mapping=dict(entry.column_mapping_used),
            cleaning_summary=cleaning_summary_to_json(entry.cleaning_summary),
        )
        session.add(dataset)
        session.flush()
        for bar in entry.bars:
            session.add(
                PriceBar(
                    dataset_id=dataset.id,
                    date=bar.date,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        cache.restore(token, entry)
        raise
    session.refresh(dataset)
    return dataset
