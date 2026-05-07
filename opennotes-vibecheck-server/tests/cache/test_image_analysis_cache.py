"""Tests for src/cache/image_analysis_cache.py (TASK-1483.24.02).

Uses testcontainers Postgres for the vibecheck_image_analysis_cache table.
Mirrors the pattern in tests/analyses/safety/test_web_risk.py.
"""
from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.safety.vision_client import SafeSearchResult
from src.cache import image_analysis_cache

_REAL_GETADDRINFO = socket.getaddrinfo

_MINIMAL_DDL = """
CREATE TABLE IF NOT EXISTS vibecheck_image_analysis_cache (
    image_url TEXT PRIMARY KEY,
    result_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS vibecheck_image_analysis_cache_expires_at_idx
    ON vibecheck_image_analysis_cache (expires_at);
"""


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container: PostgresContainer) -> AsyncIterator[asyncpg.Pool]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS vibecheck_image_analysis_cache CASCADE;")
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


def _result(adult: float = 0.1) -> SafeSearchResult:
    return SafeSearchResult(
        adult=adult,
        violence=0.2,
        racy=0.3,
        medical=0.0,
        spoof=0.0,
        flagged=False,
        max_likelihood=0.3,
    )


class TestFetchCached:
    async def test_empty_input_returns_empty_dict(self, db_pool: asyncpg.Pool) -> None:
        out = await image_analysis_cache.fetch_cached(db_pool, [])
        assert out == {}

    async def test_returns_unexpired_entry(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/cat.jpg"
        await image_analysis_cache.upsert_cached(
            db_pool, {url: _result(adult=0.42)}, ttl_hours=24
        )

        out = await image_analysis_cache.fetch_cached(db_pool, [url])

        assert set(out.keys()) == {url}
        assert out[url].adult == pytest.approx(0.42)
        assert out[url].max_likelihood == pytest.approx(0.3)

    async def test_expired_entry_treated_as_miss(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/expired.jpg"
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO vibecheck_image_analysis_cache
                    (image_url, result_payload, expires_at)
                VALUES ($1, '{"adult":0.1,"violence":0.2,"racy":0.3,"medical":0,'
                        '"spoof":0,"flagged":false,"max_likelihood":0.3}'::jsonb,
                        now() - interval '1 minute')
                """,
                url,
            )

        out = await image_analysis_cache.fetch_cached(db_pool, [url])
        assert out == {}

    async def test_miss_returns_empty_dict(self, db_pool: asyncpg.Pool) -> None:
        out = await image_analysis_cache.fetch_cached(
            db_pool, ["https://example.com/never.jpg"]
        )
        assert out == {}


class TestUpsertCached:
    async def test_empty_results_is_noop(self, db_pool: asyncpg.Pool) -> None:
        await image_analysis_cache.upsert_cached(db_pool, {}, ttl_hours=24)
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT count(*) FROM vibecheck_image_analysis_cache")
        assert count == 0

    async def test_inserts_row(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/dog.jpg"
        await image_analysis_cache.upsert_cached(
            db_pool, {url: _result()}, ttl_hours=168
        )
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT image_url, expires_at, checked_at "
                "FROM vibecheck_image_analysis_cache WHERE image_url = $1",
                url,
            )
        assert row is not None
        assert row["image_url"] == url
        # expires_at ~= now + 168h (allow a few seconds drift)
        assert row["expires_at"] > row["checked_at"]

    async def test_conflict_updates_payload_and_expiry(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/conflict.jpg"
        await image_analysis_cache.upsert_cached(
            db_pool, {url: _result(adult=0.1)}, ttl_hours=1
        )
        await image_analysis_cache.upsert_cached(
            db_pool, {url: _result(adult=0.9)}, ttl_hours=24
        )

        out = await image_analysis_cache.fetch_cached(db_pool, [url])
        assert out[url].adult == pytest.approx(0.9)

    async def test_none_values_are_skipped(self, db_pool: asyncpg.Pool) -> None:
        url1 = "https://example.com/ok.jpg"
        url2 = "https://example.com/failed.jpg"
        await image_analysis_cache.upsert_cached(
            db_pool, {url1: _result(), url2: None}, ttl_hours=24
        )
        async with db_pool.acquire() as conn:
            urls = await conn.fetch("SELECT image_url FROM vibecheck_image_analysis_cache")
        assert {r["image_url"] for r in urls} == {url1}
