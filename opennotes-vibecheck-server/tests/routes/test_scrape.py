from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.safety._schemas import WebRiskFinding
from src.main import app
from src.routes import scrape as scrape_route
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
    tier TEXT NOT NULL DEFAULT 'scrape',
    url TEXT NOT NULL,
    final_url TEXT,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '72 hours'),
    evicted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX vibecheck_scrapes_normalized_url_tier_idx
    ON vibecheck_scrapes (normalized_url, tier);
ALTER TABLE vibecheck_scrapes
    ADD CONSTRAINT vibecheck_scrapes_tier_check
    CHECK (tier IN ('scrape', 'interact', 'browser_html'));
"""
)


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
            "DROP TABLE IF EXISTS vibecheck_scrapes CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
def enqueue_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(scrape_route, "enqueue_job", mock)
    return mock


@pytest.fixture
async def client(
    db_pool: Any, enqueue_mock: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    app.state.cache = None
    app.state.db_pool = db_pool
    app.state.limiter = scrape_route.limiter
    scrape_route.limiter.reset()
    monkeypatch.setenv("VIBECHECK_SCRAPE_API_TOKEN", "secret")
    monkeypatch.setenv("VIBECHECK_WEB_URL", "https://vibecheck.example")
    scrape_route.get_settings.cache_clear()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.state.db_pool = None
    scrape_route.limiter.reset()
    scrape_route.get_settings.cache_clear()


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer secret"}


async def _fetch_job(pool: Any, job_id: UUID) -> Any:
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM vibecheck_jobs WHERE job_id = $1", job_id)


async def _fetch_scrape(pool: Any, normalized_url: str) -> Any:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM vibecheck_scrapes WHERE normalized_url = $1 AND tier = 'browser_html'",
            normalized_url,
        )


async def test_missing_token_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/scrape",
        json={"url": "https://example.com/post", "html": "<article>Hello</article>"},
    )

    assert resp.status_code == 401


async def test_missing_url_or_html_returns_client_error(client: httpx.AsyncClient) -> None:
    missing_url = await client.post("/api/scrape", headers=_headers(), json={"html": "<p>x</p>"})
    missing_html = await client.post("/api/scrape", headers=_headers(), json={"url": "https://example.com/post"})

    assert missing_url.status_code in {400, 422}
    assert missing_html.status_code in {400, 422}


async def test_valid_payload_inserts_browser_scrape_job_and_enqueues(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/post"
    with patch.object(
        scrape_route,
        "check_urls",
        new=AsyncMock(return_value={url: WebRiskFinding(url=url, threat_types=[])}),
    ):
        resp = await client.post(
            "/api/scrape",
            headers=_headers(),
            json={
                "url": url,
                "html": "<html><body><h1>Title</h1><p>Browser body</p></body></html>",
                "title": "Title",
                "description": "A browser supplied page",
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    job_id = UUID(body["job_id"])
    assert body["analyze_url"] == f"https://vibecheck.example/analyze?job={job_id}"
    assert body["created_at"]
    assert enqueue_mock.await_count == 1

    job = await _fetch_job(db_pool, job_id)
    assert job["status"] == "pending"
    assert job["source_type"] == "browser_html"

    scrape = await _fetch_scrape(db_pool, url)
    assert scrape is not None
    assert scrape["url"] == url
    assert scrape["final_url"] == url
    assert scrape["page_title"] == "Title"
    assert "<h1>Title</h1>" in scrape["html"]
    assert "Browser body" in scrape["markdown"]


async def test_oversized_html_returns_413(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/scrape",
        headers=_headers(),
        json={"url": "https://example.com/large", "html": "x" * (10 * 1024 * 1024 + 1)},
    )

    assert resp.status_code == 413


async def test_unsafe_url_inserts_failed_job_without_enqueue(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/malware"
    finding = WebRiskFinding(url=url, threat_types=["MALWARE"])
    with patch.object(
        scrape_route,
        "check_urls",
        new=AsyncMock(return_value={url: finding}),
    ):
        resp = await client.post(
            "/api/scrape",
            headers=_headers(),
            json={"url": url, "html": "<article>unsafe</article>"},
        )

    assert resp.status_code == 400
    assert resp.json()["error_code"] == "unsafe_url"
    assert enqueue_mock.await_count == 0
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM vibecheck_jobs WHERE normalized_url = $1", url)
    assert row["status"] == "failed"
    assert row["error_code"] == "unsafe_url"
    assert row["source_type"] == "browser_html"
