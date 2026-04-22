"""Integration tests for POST /api/analyze (TASK-1473.11).

These tests run against a real Postgres via testcontainers because the
handler's correctness depends on transactional semantics (advisory lock,
single-flight dedup, cache-hit short-circuit with atomic job row insert,
and the post-commit enqueue-then-rollback-on-failure sequence). Mocking
the DB at that depth would test the mock, not the handler.

The Cloud Tasks enqueue call is the one out-of-process dependency we do
stub: by default the suite patches `src.routes.analyze.enqueue_job` with
an AsyncMock so tests observe call count + arguments without a real
Cloud Tasks client.
"""
from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

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
"""


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest.py's autouse `_stub_dns` pins every lookup to 8.8.8.8, which
    # testcontainers can't use to reach the Postgres it just booted.
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
    """Replace `enqueue_job` with an AsyncMock by default.

    Tests that want to assert the exception-path behavior override
    `side_effect` to raise.
    """
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(analyze_route, "enqueue_job", mock)
    return mock


@pytest.fixture
async def client(
    db_pool: Any, enqueue_mock: AsyncMock
) -> AsyncIterator[httpx.AsyncClient]:
    """httpx.AsyncClient over the ASGI transport so the test, the app, and
    the asyncpg pool all share a single event loop.

    TestClient's BaseHTTPMiddleware bridge runs middleware on its own loop
    and causes 'Future attached to a different loop' errors when mixed with
    an asyncpg pool created by a test fixture.
    """
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


async def _insert_cache_entry(pool: Any, url: str, payload: dict[str, Any]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_analyses (url, sidebar_payload, expires_at)
            VALUES ($1, $2::jsonb, $3)
            """,
            url,
            json.dumps(payload),
            datetime.now(UTC) + timedelta(hours=1),
        )


async def _insert_inflight_job(pool: Any, url: str) -> UUID:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, status)
            VALUES ($1, $1, 'example.com', 'pending')
            RETURNING job_id
            """,
            url,
        )
    assert isinstance(job_id, UUID)
    return job_id


def _minimal_sidebar_payload(url: str) -> dict[str, Any]:
    """Dict-shaped SidebarPayload good enough for cache-hit tests.

    The handler stores this in `vibecheck_jobs.sidebar_payload` without
    re-validating it, so it needs only to round-trip as JSONB.
    """
    now = datetime.now(UTC).isoformat()
    return {
        "source_url": url,
        "page_title": None,
        "page_kind": "other",
        "scraped_at": now,
        "cached": True,
        "cached_at": now,
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


# --- AC #1: invalid URL ----------------------------------------------------


async def test_invalid_url_returns_400_no_job_row(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    before = await _count_jobs(db_pool)
    resp = await client.post("/api/analyze", json={"url": "javascript:alert(1)"})

    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "invalid_url"
    after = await _count_jobs(db_pool)
    assert after == before
    assert enqueue_mock.await_count == 0


async def test_empty_url_returns_400(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/analyze", json={"url": ""})
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_url"


async def test_missing_url_returns_422(client: httpx.AsyncClient) -> None:
    """Pydantic field-validation: absent `url` → 422 before handler runs."""
    resp = await client.post("/api/analyze", json={})
    assert resp.status_code == 422


async def test_double_submit_dedups_to_single_enqueue(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    """Two POSTs in quick succession: only the first enqueues, both see the
    same job_id."""
    url = "https://example.com/double-submit"

    first = await client.post("/api/analyze", json={"url": url})
    second = await client.post("/api/analyze", json={"url": url})

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    # Exactly one pending row, exactly one enqueue publish.
    assert await _count_jobs(db_pool, normalized_url=url) == 1
    assert enqueue_mock.await_count == 1


# --- AC #2: cache hit ------------------------------------------------------


async def test_cache_hit_inserts_done_job_and_returns_cached_true(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/cached-article"
    cached_payload = _minimal_sidebar_payload(url)
    await _insert_cache_entry(db_pool, url, cached_payload)

    resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 202
    body = resp.json()
    assert body["cached"] is True
    assert body["status"] == "done"
    assert UUID(body["job_id"])  # valid UUID

    # Exactly one job row exists and it is status=done with sidebar_payload.
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, sidebar_payload, cached FROM vibecheck_jobs WHERE normalized_url = $1",
            url,
        )
    assert len(rows) == 1
    assert rows[0]["status"] == "done"
    assert rows[0]["cached"] is True
    stored = (
        json.loads(rows[0]["sidebar_payload"])
        if isinstance(rows[0]["sidebar_payload"], str)
        else dict(rows[0]["sidebar_payload"])
    )
    assert stored["source_url"] == url

    # Cache hit must not enqueue a worker — the job is already done.
    assert enqueue_mock.await_count == 0


# --- AC #3: in-flight dedup ------------------------------------------------


async def test_duplicate_submit_returns_existing_job_id_without_new_row(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/dedupe-me"
    existing_job_id = await _insert_inflight_job(db_pool, url)

    resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == str(existing_job_id)
    assert body["status"] == "pending"
    assert body["cached"] is False

    # No new job row; only the pre-existing one.
    assert await _count_jobs(db_pool, normalized_url=url) == 1
    # No enqueue — the original worker is already running.
    assert enqueue_mock.await_count == 0


# --- AC #4 + fresh submit: enqueue called with expected_attempt_id ---------


def test_task_name_embeds_both_job_id_and_attempt_id() -> None:
    """AC#4: task_name must carry expected_attempt_id so redelivery windows
    cannot collide with a future attempt. Two distinct attempts for the
    same job_id must produce two distinct task names."""
    from src.jobs.enqueue import build_task_name

    job_id = UUID("11111111-1111-1111-1111-111111111111")
    attempt_a = UUID("22222222-2222-2222-2222-222222222222")
    attempt_b = UUID("33333333-3333-3333-3333-333333333333")

    name_a = build_task_name(job_id, attempt_a)
    name_b = build_task_name(job_id, attempt_b)

    assert str(job_id) in name_a
    assert str(attempt_a) in name_a
    assert name_a != name_b
    assert str(attempt_b) in name_b


async def test_fresh_submit_inserts_pending_row_and_enqueues(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    url = "https://example.com/fresh"

    resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["cached"] is False
    returned_job_id = UUID(body["job_id"])

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT job_id, status, attempt_id FROM vibecheck_jobs WHERE normalized_url = $1",
            url,
        )
    assert row is not None
    assert row["job_id"] == returned_job_id
    assert row["status"] == "pending"

    # enqueue_job called exactly once with the job_id + attempt_id we inserted.
    assert enqueue_mock.await_count == 1
    call = enqueue_mock.await_args
    assert call is not None
    # Positional or keyword — accept both shapes.
    call_kwargs: dict[str, Any] = dict(call.kwargs)
    if call.args:
        for name, value in zip(
            ("job_id", "expected_attempt_id", "settings"), call.args, strict=False
        ):
            call_kwargs.setdefault(name, value)
    assert call_kwargs["job_id"] == returned_job_id
    assert call_kwargs["expected_attempt_id"] == row["attempt_id"]


# --- AC #5: enqueue failure → job flipped to failed/internal, 500 ----------


async def test_enqueue_failure_marks_job_failed_and_returns_500(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_mock: AsyncMock,
) -> None:
    enqueue_mock.side_effect = RuntimeError("cloud tasks unreachable")
    url = "https://example.com/enqueue-boom"

    resp = await client.post("/api/analyze", json={"url": url})

    assert resp.status_code == 500
    body = resp.json()
    assert body["error_code"] == "internal"

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, error_code, error_message FROM vibecheck_jobs WHERE normalized_url = $1",
            url,
        )
    assert row is not None
    assert row["status"] == "failed"
    assert row["error_code"] == "internal"
    assert row["error_message"] == "enqueue failed"


# --- AC #6: advisory-lock contention → 503 Retry-After ---------------------


async def test_contention_without_inflight_row_returns_503_retry_after(
    client: httpx.AsyncClient, db_pool: Any, enqueue_mock: AsyncMock
) -> None:
    """Hold the advisory lock in a separate transaction.

    `pg_try_advisory_xact_lock` contends on the same `hashtext` key the
    handler computes. Without an in-flight row to dedupe against, the
    handler's two try-lock attempts (1s apart) both fail and it 503s.
    """
    url = "https://example.com/contended"
    blocker_started = asyncio.Event()
    blocker_release = asyncio.Event()

    async def hold_lock() -> None:
        async with db_pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                url,
            )
            blocker_started.set()
            await blocker_release.wait()

    blocker_task = asyncio.create_task(hold_lock())
    try:
        await blocker_started.wait()
        # httpx.AsyncClient runs on our loop; the blocker keeps yielding on
        # blocker_release so the POST runs concurrently. The handler hits
        # two try-lock failures and returns 503.
        resp = await client.post("/api/analyze", json={"url": url})
    finally:
        blocker_release.set()
        await blocker_task

    assert resp.status_code == 503
    assert "retry-after" in {k.lower() for k in resp.headers}
    # No job row was created because the handler could never enter the
    # critical section.
    assert await _count_jobs(db_pool, normalized_url=url) == 0
    assert enqueue_mock.await_count == 0
