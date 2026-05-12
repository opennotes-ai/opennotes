"""Endpoint tests for GET /api/internal/analyses/recent-unfiltered."""
from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.config import get_settings
from src.main import app
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
async def client(
    db_pool: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("VIBECHECK_PRIVATE_PATH_PREFIX", "internal-prefix-for-tests")
    get_settings.cache_clear()
    app.state.cache = None
    app.state.db_pool = db_pool
    app.state.recent_signer = _StubSigner()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c
    app.state.db_pool = None
    app.state.recent_signer = None
    get_settings.cache_clear()


def _sections(done: int = 7, total: int = 7) -> dict[str, dict[str, str]]:
    return {
        f"slug{i}": {"state": "done" if i < done else "failed"}
        for i in range(total)
    }


async def _seed_job_and_scrape(
    pool: Any,
    *,
    url: str,
    status: str = "done",
    sections: dict[str, dict[str, str]] | None = None,
    finished_at: datetime | None = None,
) -> None:
    finished = finished_at or datetime.now(UTC)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_jobs
                (url, normalized_url, host, status, sections, finished_at,
                 preview_description, page_title)
            VALUES ($1, $1, 'example.com', $2, $3::jsonb, $4, $5, $6)
            """,
            url,
            status,
            json.dumps(sections or _sections()),
            finished,
            "Sample preview blurb",
            "Sample Page",
        )
        await conn.execute(
            """
            INSERT INTO vibecheck_scrapes
                (normalized_url, url, host, page_title, screenshot_storage_key,
                 expires_at)
            VALUES ($1, $1, 'example.com', 'Sample Page', $2, now() + INTERVAL '72 hours')
            """,
            url,
            f"{url.removeprefix('https://').removeprefix('http://')}.png",
        )


class TestInternalRecentUnfilteredAuth:
    async def test_matching_prefix_returns_unfiltered_rows(
        self, client: httpx.AsyncClient, db_pool: Any
    ) -> None:
        await _seed_job_and_scrape(db_pool, url="http://localhost/private")

        resp = await client.get(
            "/api/internal/analyses/recent-unfiltered",
            headers={"X-Internal-Prefix": "internal-prefix-for-tests"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["source_url"] == "http://localhost/private"

    async def test_mismatched_prefix_returns_404(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.get(
            "/api/internal/analyses/recent-unfiltered",
            headers={"X-Internal-Prefix": "wrong"},
        )
        assert resp.status_code == 404

    async def test_missing_prefix_returns_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/internal/analyses/recent-unfiltered")
        assert resp.status_code == 404

    async def test_unset_env_returns_404(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("VIBECHECK_PRIVATE_PATH_PREFIX", raising=False)
        get_settings.cache_clear()

        resp = await client.get(
            "/api/internal/analyses/recent-unfiltered",
            headers={"X-Internal-Prefix": "internal-prefix-for-tests"},
        )

        assert resp.status_code == 404


class TestInternalRecentUnfilteredLimit:
    async def test_limit_clamps_to_one(
        self, client: httpx.AsyncClient, db_pool: Any
    ) -> None:
        for i in range(3):
            await _seed_job_and_scrape(
                db_pool,
                url=f"https://example.com/limit-low-{i}",
                finished_at=datetime.now(UTC) - timedelta(seconds=i),
            )

        resp = await client.get(
            "/api/internal/analyses/recent-unfiltered?limit=0",
            headers={"X-Internal-Prefix": "internal-prefix-for-tests"},
        )

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_limit_clamps_to_maximum(
        self, client: httpx.AsyncClient, db_pool: Any
    ) -> None:
        for i in range(205):
            await _seed_job_and_scrape(
                db_pool,
                url=f"https://example.com/limit-high-{i}",
                finished_at=datetime.now(UTC) - timedelta(seconds=i),
            )

        resp = await client.get(
            "/api/internal/analyses/recent-unfiltered?limit=500",
            headers={"X-Internal-Prefix": "internal-prefix-for-tests"},
        )

        assert resp.status_code == 200
        assert len(resp.json()) == 200
