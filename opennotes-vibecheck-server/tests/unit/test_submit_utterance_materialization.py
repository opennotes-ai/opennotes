"""Regression tests for cache-hit utterance materialization (TASK-1500.13.07).

Covers:
- Cache-hit submit for a URL with comment-* refs copies utterances from the source job.
- Cache-hit submit backfills an existing broken cached done job (zero utterances).
- Cache-hit submit with no source utterance rows evicts the stale cache and falls
  through to the fresh pending path.
"""
from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from tests.conftest import VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)

_DDL = (
    """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
"""
    + VIBECHECK_JOBS_DDL
    + """
CREATE INDEX vibecheck_jobs_normalized_url_idx
    ON vibecheck_jobs(normalized_url);

CREATE UNIQUE INDEX vibecheck_jobs_unique_done_cached_normalized_url
    ON vibecheck_jobs(normalized_url)
    WHERE status = 'done' AND cached = true;

CREATE TABLE vibecheck_job_utterances (
    utterance_pk UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES vibecheck_jobs(job_id) ON DELETE CASCADE,
    utterance_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    author TEXT,
    timestamp_at TIMESTAMPTZ,
    parent_id TEXT,
    position INT NOT NULL DEFAULT 0,
    page_title TEXT,
    page_kind TEXT,
    utterance_stream_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
)

_SIDEBAR_WITH_COMMENT_REFS = json.dumps(
    {
        "source_url": "https://latimes.example.com/coral-article",
        "scraped_at": "2026-05-01T00:00:00+00:00",
        "utterances": [],
        "facts_claims": {
            "claims": [
                {
                    "text": "Some claim",
                    "utterance_ref": "comment-1-abc123",
                }
            ]
        },
    }
)

_SIDEBAR_WITHOUT_COMMENT_REFS = json.dumps(
    {
        "source_url": "https://latimes.example.com/no-coral",
        "scraped_at": "2026-05-01T00:00:00+00:00",
        "utterances": [],
        "facts_claims": {"claims": []},
    }
)


@pytest.fixture(scope="module")
def _pg() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def pool(_pg: PostgresContainer) -> AsyncIterator[Any]:
    raw = _pg.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    p = await asyncpg.create_pool(dsn, min_size=2, max_size=8)
    assert p is not None
    async with p.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_job_utterances CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_DDL)
    try:
        yield p
    finally:
        await p.close()


async def _insert_fresh_done_job(pool: Any, normalized_url: str) -> UUID:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, status, cached, finished_at)
            VALUES ($1, $1, 'latimes.example.com', 'done', false, now())
            RETURNING job_id
            """,
            normalized_url,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def _insert_utterances(pool: Any, job_id: UUID, *, count: int = 2) -> None:
    async with pool.acquire() as conn:
        for i in range(count):
            await conn.execute(
                """
                INSERT INTO vibecheck_job_utterances
                    (job_id, utterance_id, kind, text, position)
                VALUES ($1, $2, 'comment', $3, $4)
                """,
                job_id,
                f"comment-{i}-abc",
                f"Comment text {i}",
                i,
            )


async def _insert_non_comment_utterances(
    pool: Any, job_id: UUID, *, count: int = 2
) -> None:
    async with pool.acquire() as conn:
        for i in range(count):
            await conn.execute(
                """
                INSERT INTO vibecheck_job_utterances
                    (job_id, utterance_id, kind, text, position)
                VALUES ($1, $2, 'article', $3, $4)
                """,
                job_id,
                f"article-{i}-abc",
                f"Article text {i}",
                i,
            )


async def _seed_cache(pool: Any, normalized_url: str, payload_json: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_analyses (url, sidebar_payload, expires_at)
            VALUES ($1, $2::jsonb, now() + interval '1 hour')
            ON CONFLICT (url) DO UPDATE SET
                sidebar_payload = EXCLUDED.sidebar_payload,
                expires_at = EXCLUDED.expires_at
            """,
            normalized_url,
            payload_json,
        )


async def _utterance_count(pool: Any, job_id: UUID) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_job_utterances WHERE job_id = $1", job_id
        )


async def _cache_exists(pool: Any, normalized_url: str) -> bool:
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1 AND expires_at > now()",
            normalized_url,
        )
        return bool(result and result > 0)


async def _call_handle_locked_submit(
    pool: Any,
    *,
    url: str,
    normalized_url: str,
    host: str,
) -> Any:
    from src.jobs.submit import handle_locked_submit

    async with pool.acquire() as conn:
        result, attempt = await handle_locked_submit(
            conn,
            url=url,
            normalized_url=normalized_url,
            host=host,
            unsafe_finding=None,
        )
    return result, attempt


async def _get_cached_done_job_id(pool: Any, normalized_url: str) -> UUID | None:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            SELECT job_id FROM vibecheck_jobs
            WHERE normalized_url = $1 AND status = 'done' AND cached = true
            LIMIT 1
            """,
            normalized_url,
        )
    return job_id if isinstance(job_id, UUID) else None


class TestCacheHitUtteranceMaterialization:
    async def test_cache_hit_with_comment_refs_copies_utterances_from_source_job(
        self, pool: Any
    ) -> None:
        url = "https://latimes.example.com/coral-utterance-copy"
        source_job_id = await _insert_fresh_done_job(pool, url)
        await _insert_utterances(pool, source_job_id, count=3)
        await _seed_cache(pool, url, _SIDEBAR_WITH_COMMENT_REFS.replace(
            "latimes.example.com/coral-article", "latimes.example.com/coral-utterance-copy"
        ))

        result, attempt = await _call_handle_locked_submit(
            pool, url=url, normalized_url=url, host="latimes.example.com"
        )

        assert result.cached is True
        assert attempt is None

        cached_job_id = await _get_cached_done_job_id(pool, url)
        assert cached_job_id is not None
        count = await _utterance_count(pool, cached_job_id)
        assert count == 3

    async def test_cache_hit_backfills_existing_broken_cached_job(
        self, pool: Any
    ) -> None:
        url = "https://latimes.example.com/coral-backfill"
        source_job_id = await _insert_fresh_done_job(pool, url)
        await _insert_utterances(pool, source_job_id, count=2)

        payload = _SIDEBAR_WITH_COMMENT_REFS.replace(
            "latimes.example.com/coral-article", "latimes.example.com/coral-backfill"
        )
        await _seed_cache(pool, url, payload)

        async with pool.acquire() as conn:
            broken_job_id = await conn.fetchval(
                """
                INSERT INTO vibecheck_jobs
                    (url, normalized_url, host, status, cached, sidebar_payload, finished_at)
                VALUES ($1, $1, 'latimes.example.com', 'done', true, $2::jsonb, now())
                RETURNING job_id
                """,
                url,
                payload,
            )
        assert isinstance(broken_job_id, UUID)
        broken_count = await _utterance_count(pool, broken_job_id)
        assert broken_count == 0

        result, _ = await _call_handle_locked_submit(
            pool, url=url, normalized_url=url, host="latimes.example.com"
        )

        assert result.cached is True
        assert result.job_id == broken_job_id

        count = await _utterance_count(pool, broken_job_id)
        assert count == 2

    async def test_cache_hit_without_comment_refs_does_not_copy_utterances(
        self, pool: Any
    ) -> None:
        url = "https://latimes.example.com/no-coral-cache"
        source_job_id = await _insert_fresh_done_job(pool, url)
        await _insert_utterances(pool, source_job_id, count=1)
        await _seed_cache(pool, url, _SIDEBAR_WITHOUT_COMMENT_REFS.replace(
            "latimes.example.com/no-coral", "latimes.example.com/no-coral-cache"
        ))

        result, _ = await _call_handle_locked_submit(
            pool, url=url, normalized_url=url, host="latimes.example.com"
        )

        assert result.cached is True

        cached_job_id = await _get_cached_done_job_id(pool, url)
        assert cached_job_id is not None
        count = await _utterance_count(pool, cached_job_id)
        assert count == 0

    async def test_cache_hit_with_comment_refs_but_no_source_utterances_evicts_cache(
        self, pool: Any
    ) -> None:
        url = "https://latimes.example.com/coral-evict"
        await _seed_cache(pool, url, _SIDEBAR_WITH_COMMENT_REFS.replace(
            "latimes.example.com/coral-article", "latimes.example.com/coral-evict"
        ))
        assert await _cache_exists(pool, url)

        result, attempt = await _call_handle_locked_submit(
            pool, url=url, normalized_url=url, host="latimes.example.com"
        )

        assert result.cached is False
        assert result.status.value == "pending"
        assert attempt is not None

        assert not await _cache_exists(pool, url)

    async def test_copy_utterances_is_idempotent_second_call_does_not_double_rows(
        self, pool: Any
    ) -> None:
        from src.jobs.submit import _copy_utterances_to_job

        url = "https://latimes.example.com/coral-idempotent"
        source_job_id = await _insert_fresh_done_job(pool, url)
        await _insert_utterances(pool, source_job_id, count=3)

        async with pool.acquire() as conn:
            target_job_id = await conn.fetchval(
                """
                INSERT INTO vibecheck_jobs
                    (url, normalized_url, host, status, cached, finished_at)
                VALUES ($1, $1, 'latimes.example.com', 'done', true, now())
                RETURNING job_id
                """,
                url + "-target",
            )
        assert isinstance(target_job_id, UUID)

        async with pool.acquire() as conn:
            result1 = await _copy_utterances_to_job(conn, source_job_id, target_job_id)
        async with pool.acquire() as conn:
            result2 = await _copy_utterances_to_job(conn, source_job_id, target_job_id)

        assert result1 is True
        assert result2 is True
        count = await _utterance_count(pool, target_job_id)
        assert count == 3

    async def test_copy_utterances_returns_false_when_source_has_no_rows(
        self, pool: Any
    ) -> None:
        from src.jobs.submit import _copy_utterances_to_job

        url = "https://latimes.example.com/coral-source-empty"
        source_job_id = await _insert_fresh_done_job(pool, url)
        # No utterances inserted for source — simulates purged utterances

        async with pool.acquire() as conn:
            target_job_id = await conn.fetchval(
                """
                INSERT INTO vibecheck_jobs
                    (url, normalized_url, host, status, cached, finished_at)
                VALUES ($1, $1, 'latimes.example.com', 'done', true, now())
                RETURNING job_id
                """,
                url + "-target",
            )
        assert isinstance(target_job_id, UUID)

        async with pool.acquire() as conn:
            result = await _copy_utterances_to_job(conn, source_job_id, target_job_id)

        assert result is False
        count = await _utterance_count(pool, target_job_id)
        assert count == 0

    async def test_cache_hit_with_comment_refs_but_only_non_comment_utterances_evicts_cache(
        self, pool: Any
    ) -> None:
        url = "https://latimes.example.com/coral-non-comment-evict"
        source_job_id = await _insert_fresh_done_job(pool, url)
        await _insert_non_comment_utterances(pool, source_job_id, count=2)
        await _seed_cache(pool, url, _SIDEBAR_WITH_COMMENT_REFS.replace(
            "latimes.example.com/coral-article",
            "latimes.example.com/coral-non-comment-evict",
        ))
        assert await _cache_exists(pool, url)

        result, attempt = await _call_handle_locked_submit(
            pool, url=url, normalized_url=url, host="latimes.example.com"
        )

        assert result.cached is False
        assert result.status.value == "pending"
        assert attempt is not None

        assert not await _cache_exists(pool, url)
