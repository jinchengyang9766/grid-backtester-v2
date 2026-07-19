"""Immutable preview-cache entry: one mapping/cleaning pairing per token.

The entry carries the complete cleaned, sorted, deduplicated Bar tuple
needed for saving — never raw bytes, decoded source text, credentials,
sessions, ORM objects, or file handles. ``source_content_hash`` is
server-side binding metadata and is never returned to the client.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import DataMode
from app.domain.models import Bar
from app.importing import BadRow, CleaningSummary, DuplicateRow

__all__ = ["PreviewCacheEntry"]


@dataclass(frozen=True, slots=True)
class PreviewCacheEntry:
    owner_user_id: int
    source_content_hash: str
    original_filename: str
    detected_format: str
    detected_encoding: str
    security_name: str | None
    security_code: str | None
    auto_column_mapping: dict[str, str]
    column_mapping_used: dict[str, str]
    data_mode: DataMode
    bars: tuple[Bar, ...]
    bad_rows: tuple[BadRow, ...]
    duplicate_rows: tuple[DuplicateRow, ...]
    cleaning_summary: CleaningSummary
    created_at: datetime
    expires_at: datetime
