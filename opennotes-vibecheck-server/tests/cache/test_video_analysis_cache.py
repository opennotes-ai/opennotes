"""Tests for src/cache/video_analysis_cache.py (TASK-1483.24.03).

Uses testcontainers Postgres for the vibecheck_video_analysis_cache table.
"""
from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.safety._schemas import FrameFinding
from src.cache import video_analysis_cache

_REAL_GETADDRINFO = socket.getaddrinfo

_MINIMAL_DDL = """
CREATE TABLE IF NOT EXISTS vibecheck_video_analysis_cache (
    video_url TEXT PRIMARY KEY,
    frame_findings_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS vibecheck_video_analysis_cache_expires_at_idx
    ON vibecheck_video_analysis_cache (expires_at);
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
        await conn.execute("DROP TABLE IF EXISTS vibecheck_video_analysis_cache CASCADE;")
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


def _frame(offset_ms: int, *, adult: float = 0.1, flagged: bool = False) -> FrameFinding:
    return FrameFinding(
        frame_offset_ms=offset_ms,
        adult=adult,
        violence=0.2,
        racy=0.3,
        medical=0.0,
        spoof=0.0,
        flagged=flagged,
        max_likelihood=0.3,
    )


class TestFetchCached:
    async def test_empty_input_returns_empty_dict(self, db_pool: asyncpg.Pool) -> None:
        out = await video_analysis_cache.fetch_cached(db_pool, [])
        assert out == {}

    async def test_round_trip_preserves_frame_list(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/clip.mp4"
        findings = [_frame(0, adult=0.1), _frame(1000, adult=0.5), _frame(2000, adult=0.9)]
        await video_analysis_cache.upsert_cached(db_pool, {url: findings}, ttl_hours=24)

        out = await video_analysis_cache.fetch_cached(db_pool, [url])

        assert list(out.keys()) == [url]
        assert [f.frame_offset_ms for f in out[url]] == [0, 1000, 2000]
        assert [f.adult for f in out[url]] == [pytest.approx(0.1), pytest.approx(0.5), pytest.approx(0.9)]

    async def test_expired_entry_treated_as_miss(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/expired.mp4"
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO vibecheck_video_analysis_cache
                    (video_url, frame_findings_payload, expires_at)
                VALUES ($1, '[]'::jsonb, now() - interval '1 minute')
                """,
                url,
            )

        out = await video_analysis_cache.fetch_cached(db_pool, [url])
        assert out == {}

    async def test_miss_returns_empty_dict(self, db_pool: asyncpg.Pool) -> None:
        out = await video_analysis_cache.fetch_cached(
            db_pool, ["https://example.com/never.mp4"]
        )
        assert out == {}


class TestUpsertCached:
    async def test_empty_results_is_noop(self, db_pool: asyncpg.Pool) -> None:
        await video_analysis_cache.upsert_cached(db_pool, {}, ttl_hours=24)
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT count(*) FROM vibecheck_video_analysis_cache")
        assert count == 0

    async def test_empty_list_value_is_skipped(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/empty.mp4"
        await video_analysis_cache.upsert_cached(db_pool, {url: []}, ttl_hours=24)
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT count(*) FROM vibecheck_video_analysis_cache")
        assert count == 0

    async def test_conflict_updates_payload_and_expiry(self, db_pool: asyncpg.Pool) -> None:
        url = "https://example.com/conflict.mp4"
        await video_analysis_cache.upsert_cached(
            db_pool, {url: [_frame(0, adult=0.1)]}, ttl_hours=1
        )
        await video_analysis_cache.upsert_cached(
            db_pool, {url: [_frame(0, adult=0.9), _frame(500, adult=0.95)]},
            ttl_hours=24,
        )

        out = await video_analysis_cache.fetch_cached(db_pool, [url])
        assert [f.adult for f in out[url]] == [pytest.approx(0.9), pytest.approx(0.95)]

    async def test_partial_skip_writes_only_nonempty(self, db_pool: asyncpg.Pool) -> None:
        url1 = "https://example.com/ok.mp4"
        url2 = "https://example.com/failed.mp4"
        await video_analysis_cache.upsert_cached(
            db_pool, {url1: [_frame(0)], url2: []}, ttl_hours=24
        )
        async with db_pool.acquire() as conn:
            urls = await conn.fetch("SELECT video_url FROM vibecheck_video_analysis_cache")
        assert {r["video_url"] for r in urls} == {url1}
