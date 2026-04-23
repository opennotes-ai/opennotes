from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import Client

from src.cache.normalize import normalize_url
from src.monitoring import get_logger

# Re-exported for backwards compatibility with callers that imported
# `normalize_url` from this module before the split to `src.cache.normalize`.
__all__ = ["SupabaseCache", "normalize_url"]

logger = get_logger(__name__)

_TABLE_NAME = "vibecheck_analyses"


class SupabaseCache:
    def __init__(self, client: Client, ttl_hours: int = 72) -> None:
        self._client = client
        self._ttl_hours = ttl_hours

    async def get(self, url: str) -> dict[str, Any] | None:
        norm = normalize_url(url)
        try:
            resp = (
                self._client.table(_TABLE_NAME)
                .select("sidebar_payload, expires_at")
                .eq("url", norm)
                .gte("expires_at", "now()")
                .maybe_single()
                .execute()
            )
        except Exception as exc:
            logger.warning("supabase cache get failed for %s: %s", norm, exc)
            return None
        if not resp or not resp.data:
            return None
        data = resp.data
        if not isinstance(data, dict):
            return None
        payload = data.get("sidebar_payload")
        if not isinstance(payload, dict):
            return None
        return payload

    async def put(self, url: str, payload: dict[str, Any]) -> None:
        norm = normalize_url(url)
        now = datetime.now(UTC)
        expires = now + timedelta(hours=self._ttl_hours)
        row = {
            "url": norm,
            "sidebar_payload": payload,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
        try:
            self._client.table(_TABLE_NAME).upsert(row).execute()
        except Exception as exc:
            logger.warning("supabase cache put failed for %s: %s", norm, exc)
