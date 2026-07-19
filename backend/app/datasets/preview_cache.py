"""Thread-safe in-process preview cache with a frozen 30-minute TTL.

Temporary infrastructure for the local single-process application; a
Redis-backed shared cache is deferred until the background-job stage.
Exactly one instance lives per FastAPI application (on ``app.state``) —
never a module-level dictionary shared independently of the app. The
cache never opens a database connection.
"""

import secrets
import threading
from datetime import UTC, datetime, timedelta

from app.datasets.preview_models import PreviewCacheEntry

__all__ = ["PREVIEW_TOKEN_TTL", "PreviewCache"]

PREVIEW_TOKEN_TTL = timedelta(minutes=30)


class PreviewCache:
    """Token-keyed store of preview entries, owner-bound and single-use."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, PreviewCacheEntry] = {}

    @staticmethod
    def _current(now: datetime | None) -> datetime:
        return now if now is not None else datetime.now(UTC)

    def put(self, entry: PreviewCacheEntry) -> str:
        """Store the entry under a fresh cryptographically random token."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._entries[token] = entry
        return token

    def get_for_owner(
        self, token: str, owner_user_id: int, now: datetime | None = None
    ) -> PreviewCacheEntry | None:
        """Read without consuming. Unknown, expired, and wrong-owner tokens
        all return None — wrong-owner access never reveals the token exists."""
        current = self._current(now)
        with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            if entry.expires_at <= current:
                del self._entries[token]
                return None
            if entry.owner_user_id != owner_user_id:
                return None
            return entry

    def pop_for_owner(
        self, token: str, owner_user_id: int, now: datetime | None = None
    ) -> PreviewCacheEntry | None:
        """Atomically validate owner/expiry and consume the token."""
        current = self._current(now)
        with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            if entry.expires_at <= current:
                del self._entries[token]
                return None
            if entry.owner_user_id != owner_user_id:
                return None
            del self._entries[token]
            return entry

    def restore(self, token: str, entry: PreviewCacheEntry, now: datetime | None = None) -> None:
        """Re-store a popped entry after a failed database transaction.

        An already-expired entry is not restored.
        """
        if entry.expires_at <= self._current(now):
            return
        with self._lock:
            self._entries[token] = entry

    def clear_expired(self, now: datetime | None = None) -> int:
        current = self._current(now)
        with self._lock:
            expired = [
                token for token, entry in self._entries.items() if entry.expires_at <= current
            ]
            for token in expired:
                del self._entries[token]
            return len(expired)
