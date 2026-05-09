"""Unit tests for GET /api/analyze/{job_id} expired_at surfacing (TASK-1541.02).

The 7-day purge cron (TASK-1541.01) sets `expired_at` on terminal job rows
and NULLs out heavy payload columns (sidebar_payload, sections). The poll
endpoint must:

1. Continue returning 200 OK for expired rows (the job_id permalink stays
   addressable so clients can render an "analysis expired" card).
2. Surface the new `expired_at` column on `JobState` so the frontend can
   distinguish expired-vs-live without inferring from null payloads.
3. Keep the existing 404 path for genuinely unknown job_ids.

Uses the same testcontainers-postgres / asyncpg / httpx.AsyncClient
fixture pattern as `test_poll.py` so the asyncpg pool and the FastAPI
handler share one event loop.
"""

from __future__ import annotations

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
from tests.conftest import VIBECHECK_IMAGE_UPLOAD_BATCHES_DDL, VIBECHECK_JOBS_DDL

_REAL_GETADDRINFO = socket.getaddrinfo


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override the global DNS stub from tests/conftest.py so testcontainers
    can reach the actual ephemeral Postgres container."""
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)

_MINIMAL_DDL = (
    """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
"""
    + VIBECHECK_JOBS_DDL
    + VIBECHECK_IMAGE_UPLOAD_BATCHES_DDL
    + """
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
)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(_postgres_container: PostgresContainer) -> AsyncIterator[Any]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_image_upload_batches CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_job_utterances CASCADE;"
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
    analyze_route.limiter.reset()
    analyze_route.poll_rate_reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
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


async def _insert_done_job(
    pool: Any,
    *,
    url: str,
    sidebar_payload: dict[str, Any] | None,
    expired_at: datetime | None,
) -> UUID:
    """Seed a terminal `done` row, optionally with `expired_at` set.

    When `expired_at` is set, sidebar_payload is typically NULL (mirroring
    the purge cron's behavior) but callers can pass either shape.
    """
    attempt_id = uuid4()
    payload_json = json.dumps(sidebar_payload) if sidebar_payload is not None else None
    finished_at = datetime.now(UTC)
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id,
                sidebar_payload, finished_at, expired_at
            )
            VALUES (
                $1, $1, 'example.com', 'done', $2,
                $3::jsonb, $4, $5
            )
            RETURNING job_id
            """,
            url,
            attempt_id,
            payload_json,
            finished_at,
            expired_at,
        )
    assert isinstance(job_id, UUID)
    return job_id


# --- AC #6: non-expired done job → 200, expired_at=None --------------------


async def test_get_non_expired_done_job_returns_200_with_null_expired_at(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Live (non-purged) done job: response carries expired_at=None and
    the persisted sidebar_payload."""
    url = "https://example.com/live"
    payload = _minimal_sidebar_payload(url)
    job_id = await _insert_done_job(
        db_pool, url=url, sidebar_payload=payload, expired_at=None
    )

    resp = await client.get(f"/api/analyze/{job_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == str(job_id)
    assert body["status"] == "done"
    assert body["expired_at"] is None
    assert body["sidebar_payload"] is not None
    assert body["sidebar_payload"]["source_url"] == url


# --- AC #4 + #6: expired job → 200, expired_at set, sidebar_payload=None ---


async def test_get_expired_done_job_returns_200_with_expired_at_set(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Soft-deleted (purged) done job: response is 200 (NOT 404/410), with
    expired_at populated and sidebar_payload NULL — clients render an
    'analysis expired — re-analyze' card instead of the standard sidebar."""
    expired_at = datetime.now(UTC)
    job_id = await _insert_done_job(
        db_pool,
        url="https://example.com/expired",
        sidebar_payload=None,
        expired_at=expired_at,
    )

    resp = await client.get(f"/api/analyze/{job_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == str(job_id)
    assert body["status"] == "done"
    assert body["expired_at"] is not None
    assert body["sidebar_payload"] is None


# --- AC #4: existing 404 preserved for unknown job_ids ---------------------


async def test_get_unknown_job_id_still_returns_404(client: httpx.AsyncClient) -> None:
    """Unknown job_ids must still 404 with error_code=not_found — adding
    expired_at must not muddy the existing not-found contract."""
    unknown = uuid4()

    resp = await client.get(f"/api/analyze/{unknown}")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error_code"] == "not_found"
