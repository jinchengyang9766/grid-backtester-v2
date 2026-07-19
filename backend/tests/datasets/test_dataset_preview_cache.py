"""Tests for the thread-safe in-process preview cache."""

import threading
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.datasets.preview_cache import PREVIEW_TOKEN_TTL, PreviewCache
from app.datasets.preview_models import PreviewCacheEntry
from app.domain.enums import DataMode
from app.domain.models import Bar
from app.importing import BadRowReason, CleaningSummary, DateRange

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
OWNER = 1
OTHER_OWNER = 2


def make_entry(owner_user_id: int = OWNER, created_at: datetime = NOW) -> PreviewCacheEntry:
    day = created_at.date()
    summary = CleaningSummary(
        total_rows_parsed=1,
        valid_rows=1,
        bad_rows=0,
        duplicate_dates=0,
        final_row_count=1,
        date_range=DateRange(start=day, end=day),
        data_mode=DataMode.CLOSE_ONLY,
        bad_row_reasons=dict.fromkeys(BadRowReason, 0),
    )
    return PreviewCacheEntry(
        owner_user_id=owner_user_id,
        source_content_hash="a" * 64,
        original_filename="sample.csv",
        detected_format="CSV",
        detected_encoding="utf-8-sig",
        security_name=None,
        security_code=None,
        auto_column_mapping={"date": "Date", "close": "Close"},
        column_mapping_used={"date": "Date", "close": "Close"},
        data_mode=DataMode.CLOSE_ONLY,
        bars=(Bar(date=day, close=Decimal("10.5")),),
        bad_rows=(),
        duplicate_rows=(),
        cleaning_summary=summary,
        created_at=created_at,
        expires_at=created_at + PREVIEW_TOKEN_TTL,
    )


def test_ttl_is_exactly_thirty_minutes() -> None:
    entry = make_entry()
    assert entry.expires_at - entry.created_at == timedelta(minutes=30)


def test_tokens_are_opaque_and_random() -> None:
    cache = PreviewCache()
    token = cache.put(make_entry())
    assert len(token) >= 32
    assert token != str(OWNER)
    assert "sample" not in token.lower()


def test_different_puts_create_different_tokens() -> None:
    cache = PreviewCache()
    assert cache.put(make_entry()) != cache.put(make_entry())


def test_correct_owner_can_read() -> None:
    cache = PreviewCache()
    entry = make_entry()
    token = cache.put(entry)
    assert cache.get_for_owner(token, OWNER, now=NOW) is entry


def test_wrong_owner_receives_none_and_cannot_consume() -> None:
    cache = PreviewCache()
    entry = make_entry()
    token = cache.put(entry)
    assert cache.get_for_owner(token, OTHER_OWNER, now=NOW) is None
    assert cache.pop_for_owner(token, OTHER_OWNER, now=NOW) is None
    # The wrong-owner attempts must not have consumed or revealed the entry.
    assert cache.get_for_owner(token, OWNER, now=NOW) is entry


def test_missing_token_returns_none() -> None:
    cache = PreviewCache()
    assert cache.get_for_owner("no-such-token", OWNER, now=NOW) is None
    assert cache.pop_for_owner("no-such-token", OWNER, now=NOW) is None


def test_expired_token_returns_none_and_is_removed() -> None:
    cache = PreviewCache()
    token = cache.put(make_entry())
    after_expiry = NOW + timedelta(minutes=31)
    assert cache.get_for_owner(token, OWNER, now=after_expiry) is None
    # Removed: even a query dated before expiry no longer finds it.
    assert cache.get_for_owner(token, OWNER, now=NOW) is None


def test_ttl_boundary_behavior() -> None:
    cache = PreviewCache()
    entry = make_entry()
    token = cache.put(entry)
    just_before = entry.expires_at - timedelta(seconds=1)
    assert cache.get_for_owner(token, OWNER, now=just_before) is entry
    assert cache.get_for_owner(token, OWNER, now=entry.expires_at) is None


def test_get_does_not_consume() -> None:
    cache = PreviewCache()
    entry = make_entry()
    token = cache.put(entry)
    assert cache.get_for_owner(token, OWNER, now=NOW) is entry
    assert cache.get_for_owner(token, OWNER, now=NOW) is entry


def test_pop_consumes_and_consumed_token_cannot_be_reused() -> None:
    cache = PreviewCache()
    entry = make_entry()
    token = cache.put(entry)
    assert cache.pop_for_owner(token, OWNER, now=NOW) is entry
    assert cache.pop_for_owner(token, OWNER, now=NOW) is None
    assert cache.get_for_owner(token, OWNER, now=NOW) is None


def test_restore_makes_entry_usable_again() -> None:
    cache = PreviewCache()
    entry = make_entry()
    token = cache.put(entry)
    popped = cache.pop_for_owner(token, OWNER, now=NOW)
    assert popped is entry
    cache.restore(token, entry, now=NOW)
    assert cache.pop_for_owner(token, OWNER, now=NOW) is entry


def test_expired_entry_is_not_restored() -> None:
    cache = PreviewCache()
    entry = make_entry()
    token = cache.put(entry)
    assert cache.pop_for_owner(token, OWNER, now=NOW) is entry
    cache.restore(token, entry, now=entry.expires_at)
    assert cache.get_for_owner(token, OWNER, now=NOW) is None


def test_clear_expired_count() -> None:
    cache = PreviewCache()
    cache.put(make_entry(created_at=NOW - timedelta(hours=2)))
    cache.put(make_entry(created_at=NOW - timedelta(hours=1)))
    fresh_token = cache.put(make_entry(created_at=NOW))
    assert cache.clear_expired(now=NOW) == 2
    assert cache.clear_expired(now=NOW) == 0
    assert cache.get_for_owner(fresh_token, OWNER, now=NOW) is not None


def test_concurrent_consumers_get_exactly_one_success() -> None:
    cache = PreviewCache()
    token = cache.put(make_entry())
    results: list[PreviewCacheEntry | None] = []
    barrier = threading.Barrier(8)

    def consume() -> None:
        barrier.wait()
        results.append(cache.pop_for_owner(token, OWNER, now=NOW))

    threads = [threading.Thread(target=consume) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    successes = [result for result in results if result is not None]
    assert len(successes) == 1


def test_cache_entry_is_immutable_with_tuple_collections() -> None:
    entry = make_entry()
    assert isinstance(entry.bars, tuple)
    assert isinstance(entry.bad_rows, tuple)
    assert isinstance(entry.duplicate_rows, tuple)
    with pytest.raises(FrozenInstanceError):
        entry.owner_user_id = 99  # type: ignore[misc]
