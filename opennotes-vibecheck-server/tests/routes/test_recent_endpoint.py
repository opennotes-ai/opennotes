"""Endpoint tests for GET /api/analyses/recent (TASK-1485.03).

Mounted at /api/analyses/recent (router has prefix /api). Tests cover
empty, populated, truncation/ordering, and TTL-cache stability inside
the same TTL window.
"""
from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.config import get_settings
from src.main import app
from src.routes import analyze as analyze_route
from tests.conftest import VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo

_MINIMAL_DDL = (
    """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
"""
    + VIBECHECK_JOBS_DDL
    + """
CREATE TABLE vibecheck_scrapes (
    scrape_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    normalized_url TEXT NOT NULL,
    url TEXT NOT NULL,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    utterance_stream_type TEXT NOT NULL DEFAULT 'unknown',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    tier TEXT NOT NULL DEFAULT 'scrape',
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '72 hours')
);
CREATE UNIQUE INDEX vibecheck_scrapes_normalized_url_tier_idx
    ON vibecheck_scrapes (normalized_url, tier);
"""
)


class _StubSigner:
    def sign_screenshot_key(self, storage_key: str | None) -> str | None:
        if not storage_key:
            return None
        return f"https://signed.example/{storage_key}"


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container: PostgresContainer) -> AsyncIterator[Any]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_scrapes CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def client(db_pool: Any) -> AsyncIterator[httpx.AsyncClient]:
    app.state.cache = None
    app.state.db_pool = db_pool
    app.state.recent_signer = _StubSigner()
    analyze_route._reset_recent_cache_for_testing()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c
    app.state.db_pool = None
    app.state.recent_signer = None
    analyze_route._reset_recent_cache_for_testing()


def _full_done_sections() -> dict[str, dict[str, str]]:
    return {f"slug{i}": {"state": "done"} for i in range(7)}


async def _seed_done_job(
    pool: Any,
    *,
    url: str,
    finished_at: datetime | None = None,
    page_title: str = "Sample Page",
    storage_key: str = "abc/screenshot.png",
    preview: str = "Sample preview blurb",
) -> UUID:
    finished = finished_at or datetime.now(UTC)
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs
                (url, normalized_url, host, status, sections, finished_at,
                 preview_description, page_title)
            VALUES ($1, $1, 'example.com', 'done', $2::jsonb, $3, $4, $5)
            RETURNING job_id
            """,
            url,
            json.dumps(_full_done_sections()),
            finished,
            preview,
            page_title,
        )
        await conn.execute(
            """
            INSERT INTO vibecheck_scrapes
                (normalized_url, url, host, page_title, screenshot_storage_key,
                 expires_at)
            VALUES ($1, $1, 'example.com', $2, $3, now() + INTERVAL '72 hours')
            """,
            url,
            page_title,
            storage_key,
        )
    assert isinstance(job_id, UUID)
    return job_id


class TestEndpointEmpty:
    async def test_empty_db_returns_empty_list(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.get("/api/analyses/recent")
        assert resp.status_code == 200
        assert resp.json() == []


class TestEndpointPopulated:
    async def test_returns_card_with_signed_url_and_job_id(
        self, client: httpx.AsyncClient, db_pool: Any
    ) -> None:
        url = "https://example.com/post"
        job_id = await _seed_done_job(db_pool, url=url)
        resp = await client.get("/api/analyses/recent")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        card = body[0]
        assert UUID(card["job_id"]) == job_id
        assert card["source_url"] == url
        assert card["page_title"] == "Sample Page"
        assert card["screenshot_url"].startswith("https://signed.example/")
        assert card["preview_description"] == "Sample preview blurb"

    async def test_truncates_to_configured_limit(
        self, client: httpx.AsyncClient, db_pool: Any
    ) -> None:
        for i in range(7):
            await _seed_done_job(
                db_pool,
                url=f"https://example.com/post-{i}",
                finished_at=datetime.now(UTC) - timedelta(seconds=i),
            )
        resp = await client.get("/api/analyses/recent")
        body = resp.json()
        # Default limit is 6.
        assert len(body) == get_settings().VIBECHECK_RECENT_ANALYSES_LIMIT


class TestEndpointCache:
    async def test_consecutive_calls_return_stable_payload_within_ttl(
        self, client: httpx.AsyncClient, db_pool: Any
    ) -> None:
        await _seed_done_job(db_pool, url="https://example.com/cached")
        first = (await client.get("/api/analyses/recent")).json()
        # Insert a new job that *would* show up if cache was bypassed.
        await _seed_done_job(
            db_pool,
            url="https://example.com/inserted-later",
            finished_at=datetime.now(UTC) + timedelta(seconds=1),
        )
        second = (await client.get("/api/analyses/recent")).json()
        # Cache returns the original payload — new row not visible until TTL.
        assert first == second
        assert len(first) == 1
        assert first[0]["source_url"] == "https://example.com/cached"

    async def test_cache_reset_returns_fresh_payload(
        self, client: httpx.AsyncClient, db_pool: Any
    ) -> None:
        await _seed_done_job(db_pool, url="https://example.com/first")
        first = (await client.get("/api/analyses/recent")).json()
        await _seed_done_job(
            db_pool,
            url="https://example.com/second",
            finished_at=datetime.now(UTC) + timedelta(seconds=1),
        )
        analyze_route._reset_recent_cache_for_testing()
        second = (await client.get("/api/analyses/recent")).json()
        assert len(second) == 2
        assert {r["source_url"] for r in second} == {
            "https://example.com/first",
            "https://example.com/second",
        }
        assert first != second
