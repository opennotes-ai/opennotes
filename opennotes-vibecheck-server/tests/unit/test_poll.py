"""Integration tests for GET /api/analyze/{job_id} (TASK-1473.14).

Polling is a pure read: single SELECT with explicit projection, no
mutation. We cover the JobState shape, the adaptive `next_poll_ms`
ladder, the 404 path, and the slowapi composite rate-limit
(ip, job_id) → 429.

Uses testcontainers-postgres (same `_MINIMAL_DDL` as `test_analyze_post.py`
and `test_slot_writes.py`) plus an httpx.AsyncClient over the FastAPI
ASGI app so the fixture's asyncpg pool and the request handler share one
event loop.
"""
from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.main import app
from src.routes import analyze as analyze_route

_REAL_GETADDRINFO = socket.getaddrinfo


_MINIMAL_DDL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE vibecheck_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    host TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    error_code TEXT,
    error_message TEXT,
    error_host TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    sidebar_payload JSONB,
    cached BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX vibecheck_jobs_normalized_url_idx
    ON vibecheck_jobs(normalized_url);

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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


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
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE;"
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
    # Reset the POST rate limiter (from Part A) and the inline poll budget.
    analyze_route.limiter.reset()
    analyze_route.poll_rate_reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c
    app.state.db_pool = None
    analyze_route.limiter.reset()
    analyze_route.poll_rate_reset()


def _minimal_sidebar_payload(url: str) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "source_url": url,
        "page_title": "Example",
        "page_kind": "other",
        "scraped_at": now,
        "cached": False,
        "cached_at": None,
        "safety": {"harmful_content_matches": []},
        "tone_dynamics": {
            "scd": {
                "summary": "",
                "tone_labels": [],
                "per_speaker_notes": {},
                "insufficient_conversation": True,
            },
            "flashpoint_matches": [],
        },
        "facts_claims": {
            "claims_report": {
                "deduped_claims": [],
                "total_claims": 0,
                "total_unique": 0,
            },
            "known_misinformation": [],
        },
        "opinions_sentiments": {
            "opinions_report": {
                "sentiment_stats": {
                    "per_utterance": [],
                    "positive_pct": 0.0,
                    "negative_pct": 0.0,
                    "neutral_pct": 0.0,
                    "mean_valence": 0.0,
                },
                "subjective_claims": [],
            }
        },
    }


async def _insert_job(
    pool: Any,
    *,
    status: str,
    sections: dict[str, Any] | None = None,
    sidebar_payload: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    finished_at: datetime | None = None,
    url: str = "https://example.com/a",
) -> UUID:
    attempt_id = uuid4()
    sections_json = json.dumps(sections or {})
    payload_json = (
        json.dumps(sidebar_payload) if sidebar_payload is not None else None
    )
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id,
                sections, sidebar_payload,
                error_code, error_message, finished_at
            )
            VALUES ($1, $1, 'example.com', $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
            RETURNING job_id
            """,
            url,
            status,
            attempt_id,
            sections_json,
            payload_json,
            error_code,
            error_message,
            finished_at,
        )
    assert isinstance(job_id, UUID)
    return job_id


# --- AC #1 + #4: shape + next_poll_ms ladder -------------------------------


async def test_pending_job_returns_500ms_poll_hint(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    job_id = await _insert_job(db_pool, status="pending")
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == str(job_id)
    assert body["status"] == "pending"
    assert body["next_poll_ms"] == 500
    assert body["sidebar_payload"] is None
    assert body["sections"] == {}


async def test_extracting_returns_500ms_poll_hint(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    job_id = await _insert_job(db_pool, status="extracting")
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["next_poll_ms"] == 500


async def test_analyzing_returns_1500ms_poll_hint(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    job_id = await _insert_job(db_pool, status="analyzing")
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "analyzing"
    assert body["next_poll_ms"] == 1500


async def test_done_returns_zero_poll_hint_and_sidebar_payload(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    url = "https://example.com/done"
    payload = _minimal_sidebar_payload(url)
    job_id = await _insert_job(
        db_pool,
        status="done",
        sidebar_payload=payload,
        finished_at=datetime.now(UTC),
        url=url,
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["next_poll_ms"] == 0
    assert body["sidebar_payload"] is not None
    assert body["sidebar_payload"]["source_url"] == url


async def test_failed_returns_zero_poll_hint_and_error(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    job_id = await _insert_job(
        db_pool,
        status="failed",
        error_code="extraction_failed",
        error_message="firecrawl 500",
        finished_at=datetime.now(UTC),
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["next_poll_ms"] == 0
    assert body["error_code"] == "extraction_failed"
    assert body["error_message"] == "firecrawl 500"


async def test_sections_dict_round_trips(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    sections = {
        "safety__moderation": {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"harmful_content_matches": []},
            "finished_at": datetime.now(UTC).isoformat(),
        }
    }
    job_id = await _insert_job(db_pool, status="analyzing", sections=sections)
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "safety__moderation" in body["sections"]
    assert body["sections"]["safety__moderation"]["state"] == "done"


# --- AC #2: GET must not mutate the row ------------------------------------


async def test_poll_does_not_mutate_job_row(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Baseline snapshot of mutable columns; poll; compare."""
    job_id = await _insert_job(db_pool, status="pending")
    async with db_pool.acquire() as conn:
        before = await conn.fetchrow(
            "SELECT status, attempt_id, updated_at, heartbeat_at FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )

    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200

    async with db_pool.acquire() as conn:
        after = await conn.fetchrow(
            "SELECT status, attempt_id, updated_at, heartbeat_at FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert dict(before) == dict(after)


# --- AC #1 extra: unknown job → 404 ----------------------------------------


async def test_unknown_job_id_returns_404(client: httpx.AsyncClient) -> None:
    unknown = uuid4()
    resp = await client.get(f"/api/analyze/{unknown}")
    assert resp.status_code == 404


async def test_malformed_job_id_returns_422(client: httpx.AsyncClient) -> None:
    """Non-UUID path param → FastAPI rejects before handler runs."""
    resp = await client.get("/api/analyze/not-a-uuid")
    assert resp.status_code == 422


# --- AC #3: rate limit -----------------------------------------------------


async def test_rate_limit_returns_429_with_retry_after(
    client: httpx.AsyncClient, db_pool: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a tight burst budget, the 11th poll in a second returns 429.

    Keep the sustained-per-minute budget high so only the burst budget
    drives the rejection — otherwise flaky scheduling could attribute the
    failure to the wrong limit.
    """
    # Tight burst (3/second) + generous sustained (300/min). The 4th rapid
    # poll from the same (ip, job_id) tuple trips the burst limit.
    monkeypatch.setenv("RATE_LIMIT_POLL_BURST", "3")
    monkeypatch.setenv("RATE_LIMIT_POLL_SUSTAINED", "300")
    # Settings is a singleton — clear the cache so the new env is picked up.
    from src.config import get_settings

    get_settings.cache_clear()
    analyze_route.limiter.reset()
    analyze_route.poll_rate_reset()

    job_id = await _insert_job(db_pool, status="pending")

    async def one_poll() -> httpx.Response:
        return await client.get(f"/api/analyze/{job_id}")

    # Three polls from the default client IP must all succeed...
    first_batch = await asyncio.gather(*(one_poll() for _ in range(3)))
    for r in first_batch:
        assert r.status_code == 200, r.text

    # ...the next one within the same second must be 429 + Retry-After.
    fourth = await one_poll()
    assert fourth.status_code == 429
    header_names = {k.lower() for k in fourth.headers}
    assert "retry-after" in header_names

    get_settings.cache_clear()


async def test_rate_limit_is_keyed_per_job_id(
    client: httpx.AsyncClient, db_pool: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hitting two distinct job_ids must not cross-pollute the burst budget."""
    monkeypatch.setenv("RATE_LIMIT_POLL_BURST", "2")
    monkeypatch.setenv("RATE_LIMIT_POLL_SUSTAINED", "300")
    from src.config import get_settings

    get_settings.cache_clear()
    analyze_route.limiter.reset()
    analyze_route.poll_rate_reset()

    job_a = await _insert_job(db_pool, status="pending")
    job_b = await _insert_job(db_pool, status="pending")

    # 2 polls for each — burst is per (ip, job_id), so both should succeed.
    for _ in range(2):
        ra = await client.get(f"/api/analyze/{job_a}")
        rb = await client.get(f"/api/analyze/{job_b}")
        assert ra.status_code == 200
        assert rb.status_code == 200

    get_settings.cache_clear()
