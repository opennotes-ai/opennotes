"""Regression test for `_find_unsafe_url_job` skipping soft-deleted rows (TASK-1541.05).

When the purge worker (TASK-1541) clears job data and stamps `expired_at`,
the surviving stub row must NOT be returned by `_find_unsafe_url_job` —
otherwise re-submitting the same URL surfaces the dead job_id and the
client is routed to an expired analysis instead of getting a fresh job.
"""
from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from src.jobs.submit import _find_unsafe_url_job
from tests.conftest import VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


_DDL = (
    """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
"""
    + VIBECHECK_JOBS_DDL
    + """
CREATE INDEX vibecheck_jobs_normalized_url_idx
    ON vibecheck_jobs(normalized_url);
"""
)


@pytest.fixture(scope="module")
def _pg() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def pool(_pg: PostgresContainer) -> AsyncIterator[Any]:
    raw = _pg.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    p = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    assert p is not None
    async with p.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS vibecheck_jobs CASCADE;")
        await conn.execute(_DDL)
    try:
        yield p
    finally:
        await p.close()


async def _insert_unsafe_url_row(
    conn: Any,
    *,
    normalized_url: str,
    expired: bool,
) -> UUID:
    job_id = uuid4()
    raw_url = normalized_url + "?ref=test"
    await conn.execute(
        """
        INSERT INTO vibecheck_jobs (
            job_id, url, normalized_url, host, status, attempt_id,
            error_code, error_message, finished_at, expired_at
        )
        VALUES (
            $1, $2, $3, 'example.com', 'failed', $4,
            'unsafe_url', 'flagged: MALWARE', now(),
            CASE WHEN $5 THEN now() ELSE NULL END
        )
        """,
        job_id,
        raw_url,
        normalized_url,
        uuid4(),
        expired,
    )
    return job_id


async def test_find_unsafe_url_job_skips_expired_row(pool: Any) -> None:
    url = "https://example.com/expired-malware"
    async with pool.acquire() as conn:
        await _insert_unsafe_url_row(conn, normalized_url=url, expired=True)
        result = await _find_unsafe_url_job(conn, url)
    assert result is None


async def test_find_unsafe_url_job_returns_live_row(pool: Any) -> None:
    url = "https://example.com/live-malware"
    async with pool.acquire() as conn:
        live_id = await _insert_unsafe_url_row(conn, normalized_url=url, expired=False)
        result = await _find_unsafe_url_job(conn, url)
    assert result == live_id


async def test_find_unsafe_url_job_prefers_live_over_expired(pool: Any) -> None:
    url = "https://example.com/mixed-malware"
    async with pool.acquire() as conn:
        await _insert_unsafe_url_row(conn, normalized_url=url, expired=True)
        live_id = await _insert_unsafe_url_row(conn, normalized_url=url, expired=False)
        result = await _find_unsafe_url_job(conn, url)
    assert result == live_id
