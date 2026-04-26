"""In-process TTL cache for the recent-analyses endpoint (TASK-1485.03).

Single-key cache (one limit value per process). Per-instance staleness is
bounded by TTL — Cloud Run's per-instance fan-out is acceptable for a 5-row
public gallery. Hit/miss visibility comes from logfire spans in the route
handler; this module stays a tiny in-memory dict.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")

_LIMIT_DISABLED = 0


class _AsyncTTLCache(Generic[T]):
    """Single-value TTL cache keyed by a string.

    Contention is acceptable: a brief dogpile on TTL boundary triggers at
    most a few duplicate loader calls. Locks would add complexity for a
    5-row public payload that's already shaped like a CDN-cacheable response.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = max(0.0, float(ttl_seconds))
        self._store: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T) -> None:
        if self._ttl <= 0:
            return
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()

    async def get_or_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[T]],
    ) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = await loader()
        self.set(key, value)
        return value


def cache_key(limit: int) -> str:
    return f"recent:{limit}"


def is_cache_disabled(limit: int) -> bool:
    """Test/dev hook: limit=0 means no cache (also no work).

    The endpoint always uses settings.VIBECHECK_RECENT_ANALYSES_LIMIT > 0 in
    production. Tests may pass 0 to make the loader deterministic.
    """
    return limit == _LIMIT_DISABLED


__all__ = ["_AsyncTTLCache", "cache_key", "is_cache_disabled"]
