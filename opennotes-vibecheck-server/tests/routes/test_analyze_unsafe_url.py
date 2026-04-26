"""Integration tests for the Web Risk page-URL gate in POST /api/analyze.

Six ACs from TASK-1474.15:
1. clean URL (empty findings dict) → proceeds to enqueue path
2. clean URL (threat_types=[]) → proceeds to enqueue path
3. flagged URL → inserts failed job with error_code=unsafe_url
4. flagged URL → sidebar_payload.web_risk.findings populated
5. flagged URL → enqueue_job never called
6. WebRiskTransientError → HTTP 503 + Retry-After: 5
"""
from __future__ import annotations

import json
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
from src.analyses.safety.web_risk import WebRiskTransientError
from src.main import app
from src.routes import analyze as analyze_route
from tests.conftest import VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo


_MINIMAL_DDL = (
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

CREATE TABLE vibecheck_scrapes (
    scrape_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    normalized_url TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '72 hours')
);

CREATE TABLE vibecheck_job_utterances (
    utterance_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES vibecheck_jobs(job_id),
    kind TEXT NOT NULL DEFAULT 'post',
    text TEXT NOT NULL DEFAULT '',
    position INT NOT NULL DEFAULT 0,
    page_title TEXT,
    page_kind TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
)

_ANALYZE_URL = "https://example.com/article"


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
            "DROP TABLE IF EXISTS vibecheck_job_utterances CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_scrapes CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE;"
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
    monkeypatch.setattr(analyze_route, "enqueue_job", mock)
    return mock


@pytest.fixture
async def client(
    db_pool: Any, enqueue_mock: AsyncMock
) -> AsyncIterator[httpx.AsyncClient]:
    app.state.cache = None
    app.state.db_pool = db_pool
    app.state.limiter = analyze_route.limiter
    analyze_route.limiter.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c
    app.state.db_pool = None
    analyze_route.limiter.reset()


async def _count_jobs(pool: Any, normalized_url: str | None = None) -> int:
    async with pool.acquire() as conn:
        if normalized_url is None:
            return await conn.fetchval("SELECT COUNT(*) FROM vibecheck_jobs")
        return await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_jobs WHERE normalized_url = $1",
            normalized_url,
        )


async def _fetch_job_row(pool: Any, normalized_url: str) -> Any:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM vibecheck_jobs WHERE normalized_url = $1 LIMIT 1",
            normalized_url,
        )


async def test_clean_url_proceeds_to_enqueue(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    clean_finding = WebRiskFinding(url=_ANALYZE_URL, threat_types=[])
    with patch.object(
        analyze_route, "check_urls", new=AsyncMock(return_value={_ANALYZE_URL: clean_finding})
    ):
        resp = await client.post("/api/analyze", json={"url": _ANALYZE_URL})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["cached"] is False
    assert enqueue_mock.await_count == 1


async def test_unflagged_url_from_empty_findings_dict_proceeds_to_enqueue(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/not-in-findings"
    with patch.object(
        analyze_route, "check_urls", new=AsyncMock(return_value={})
    ):
        resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["cached"] is False
    assert enqueue_mock.await_count == 1


async def test_flagged_url_inserts_failed_job_with_unsafe_url_error_code(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/malware-page"
    malware_finding = WebRiskFinding(url=url, threat_types=["MALWARE"])
    with patch.object(
        analyze_route, "check_urls", new=AsyncMock(return_value={url: malware_finding})
    ):
        resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "failed"
    assert body["cached"] is False
    assert UUID(body["job_id"])

    row = await _fetch_job_row(db_pool, url)
    assert row is not None
    assert row["status"] == "failed"
    assert row["error_code"] == "unsafe_url"
    assert "MALWARE" in row["error_message"]
    assert row["finished_at"] is not None


async def test_flagged_url_populates_web_risk_section_in_sidebar_payload(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/malware-sidebar"
    malware_finding = WebRiskFinding(url=url, threat_types=["MALWARE"])
    with patch.object(
        analyze_route, "check_urls", new=AsyncMock(return_value={url: malware_finding})
    ):
        resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 202
    job_id = UUID(resp.json()["job_id"])

    row = await _fetch_job_row(db_pool, url)
    assert row is not None
    raw_payload = row["sidebar_payload"]
    payload = json.loads(raw_payload) if isinstance(raw_payload, str) else dict(raw_payload)

    web_risk = payload["web_risk"]
    assert len(web_risk["findings"]) == 1
    assert web_risk["findings"][0]["threat_types"] == ["MALWARE"]
    assert web_risk["findings"][0]["url"] == url

    poll_resp = await client.get(f"/api/analyze/{job_id}")
    assert poll_resp.status_code == 200
    poll_body = poll_resp.json()
    assert poll_body["status"] == "failed"
    assert poll_body["error_code"] == "unsafe_url"
    assert poll_body["sidebar_payload"]["web_risk"]["findings"][0]["threat_types"] == ["MALWARE"]


async def test_flagged_url_does_not_enqueue_cloud_task(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/no-enqueue-when-flagged"
    malware_finding = WebRiskFinding(url=url, threat_types=["SOCIAL_ENGINEERING"])
    with patch.object(
        analyze_route, "check_urls", new=AsyncMock(return_value={url: malware_finding})
    ):
        resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 202
    assert enqueue_mock.await_count == 0


async def test_repeated_flagged_url_returns_existing_unsafe_job(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/repeated-malware-page"
    malware_finding = WebRiskFinding(url=url, threat_types=["MALWARE"])
    with patch.object(
        analyze_route, "check_urls", new=AsyncMock(return_value={url: malware_finding})
    ):
        first = await client.post("/api/analyze", json={"url": url})
        second = await client.post("/api/analyze", json={"url": url})

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert await _count_jobs(db_pool, normalized_url=url) == 1
    assert enqueue_mock.await_count == 0


async def test_web_risk_transient_error_returns_503_with_retry_after(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/transient-error"

    async def _raise(*args: Any, **kwargs: Any) -> Any:
        raise WebRiskTransientError("service unavailable")

    with patch.object(analyze_route, "check_urls", new=_raise):
        resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 503
    body = resp.json()
    assert body["error_code"] == "rate_limited"
    assert "web risk" in body["message"].lower()
    assert resp.headers.get("retry-after") == "5"

    assert await _count_jobs(db_pool, normalized_url=url) == 0
    assert enqueue_mock.await_count == 0
