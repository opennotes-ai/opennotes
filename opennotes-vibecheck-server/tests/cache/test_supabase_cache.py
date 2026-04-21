from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.cache.supabase_cache import SupabaseCache, normalize_url


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    """Captures chained calls so tests can inspect them, then returns configured data."""

    def __init__(self, store: dict[str, dict[str, Any]]) -> None:
        self._store = store
        self._op: str | None = None
        self._eq_url: str | None = None
        self._upsert_row: dict[str, Any] | None = None

    def select(self, *_fields: str) -> FakeQuery:
        self._op = "select"
        return self

    def eq(self, column: str, value: str) -> FakeQuery:
        assert column == "url"
        self._eq_url = value
        return self

    def gte(self, column: str, value: str) -> FakeQuery:
        assert column == "expires_at"
        assert value == "now()"
        return self

    def maybe_single(self) -> FakeQuery:
        return self

    def upsert(self, row: dict[str, Any]) -> FakeQuery:
        self._op = "upsert"
        self._upsert_row = row
        return self

    def execute(self) -> FakeResponse:
        if self._op == "select":
            assert self._eq_url is not None
            row = self._store.get(self._eq_url)
            if row is None:
                return FakeResponse(None)
            expires = datetime.fromisoformat(row["expires_at"])
            if expires <= datetime.now(UTC):
                return FakeResponse(None)
            return FakeResponse(
                {"sidebar_payload": row["sidebar_payload"], "expires_at": row["expires_at"]}
            )
        if self._op == "upsert":
            assert self._upsert_row is not None
            self._store[self._upsert_row["url"]] = self._upsert_row
            return FakeResponse(self._upsert_row)
        raise AssertionError(f"unexpected op {self._op}")


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.tables_called: list[str] = []

    def table(self, name: str) -> FakeQuery:
        self.tables_called.append(name)
        return FakeQuery(self.store)


class TestNormalizeUrl:
    def test_lowercases_scheme_and_host(self) -> None:
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    def test_strips_trailing_slash(self) -> None:
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_preserves_root_slash(self) -> None:
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_strips_utm_params(self) -> None:
        result = normalize_url("http://Example.com/path/?utm_source=x&utm_medium=y&keep=1")
        assert result == "http://example.com/path?keep=1"

    def test_strips_fbclid_and_gclid(self) -> None:
        result = normalize_url("https://example.com/p?fbclid=a&gclid=b&q=search")
        assert result == "https://example.com/p?q=search"

    def test_drops_empty_query(self) -> None:
        result = normalize_url("https://example.com/p?utm_source=x")
        assert result == "https://example.com/p"


class TestSupabaseCache:
    @pytest.mark.asyncio
    async def test_put_then_get_returns_payload(self) -> None:
        fake = FakeSupabaseClient()
        cache = SupabaseCache(fake, ttl_hours=72)  # pyright: ignore[reportArgumentType]
        payload = {"summary": "hello", "claims": [{"text": "a"}]}
        await cache.put("https://example.com/article", payload)
        got = await cache.get("https://example.com/article")
        assert got == payload

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self) -> None:
        fake = FakeSupabaseClient()
        cache = SupabaseCache(fake, ttl_hours=72)  # pyright: ignore[reportArgumentType]
        got = await cache.get("https://nowhere.example.com/")
        assert got is None

    @pytest.mark.asyncio
    async def test_get_after_expiry_returns_none(self) -> None:
        fake = FakeSupabaseClient()
        url = "https://example.com/article"
        fake.store[normalize_url(url)] = {
            "url": normalize_url(url),
            "sidebar_payload": {"x": 1},
            "created_at": (datetime.now(UTC) - timedelta(hours=100)).isoformat(),
            "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }
        cache = SupabaseCache(fake, ttl_hours=72)  # pyright: ignore[reportArgumentType]
        got = await cache.get(url)
        assert got is None

    @pytest.mark.asyncio
    async def test_put_normalizes_url(self) -> None:
        fake = FakeSupabaseClient()
        cache = SupabaseCache(fake, ttl_hours=72)  # pyright: ignore[reportArgumentType]
        await cache.put("HTTPS://Example.com/a/?utm_source=x", {"ok": True})
        assert "https://example.com/a" in fake.store

    @pytest.mark.asyncio
    async def test_put_writes_expires_at_from_ttl(self) -> None:
        fake = FakeSupabaseClient()
        cache = SupabaseCache(fake, ttl_hours=72)  # pyright: ignore[reportArgumentType]
        before = datetime.now(UTC)
        await cache.put("https://example.com/a", {"ok": True})
        after = datetime.now(UTC)
        row = fake.store["https://example.com/a"]
        expires = datetime.fromisoformat(row["expires_at"])
        assert before + timedelta(hours=72) - timedelta(seconds=5) <= expires
        assert expires <= after + timedelta(hours=72) + timedelta(seconds=5)

    @pytest.mark.asyncio
    async def test_put_then_get_with_differently_cased_url(self) -> None:
        fake = FakeSupabaseClient()
        cache = SupabaseCache(fake, ttl_hours=72)  # pyright: ignore[reportArgumentType]
        await cache.put("https://Example.COM/a", {"ok": True})
        got = await cache.get("HTTPS://example.com/a")
        assert got == {"ok": True}
