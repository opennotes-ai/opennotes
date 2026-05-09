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
from tests.conftest import VIBECHECK_IMAGE_UPLOAD_BATCHES_DDL, VIBECHECK_JOBS_DDL

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
            "DROP TABLE IF EXISTS vibecheck_image_upload_batches CASCADE;"
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


def _harmful_match(utterance_id: str, text: str) -> dict[str, Any]:
    return {
        "utterance_id": utterance_id,
        "utterance_text": text,
        "max_score": 0.91,
        "categories": {"harassment": True},
        "scores": {"harassment": 0.91},
        "flagged_categories": ["harassment"],
        "source": "openai",
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
    last_stage: str | None = None,
    heartbeat_at: datetime | None = None,
    safety_recommendation: dict[str, Any] | None = None,
    headline_summary: dict[str, Any] | None = None,
) -> UUID:
    attempt_id = uuid4()
    sections_json = json.dumps(sections or {})
    payload_json = json.dumps(sidebar_payload) if sidebar_payload is not None else None
    safety_json = json.dumps(safety_recommendation) if safety_recommendation is not None else None
    headline_json = json.dumps(headline_summary) if headline_summary is not None else None
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id,
                sections, sidebar_payload,
                error_code, error_message, finished_at,
                last_stage, heartbeat_at,
                safety_recommendation, headline_summary
            )
            VALUES (
                $1, $1, 'example.com', $2, $3,
                $4::jsonb, $5::jsonb,
                $6, $7, $8,
                $9, $10,
                $11::jsonb, $12::jsonb
            )
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
            last_stage,
            heartbeat_at,
            safety_json,
            headline_json,
        )
    assert isinstance(job_id, UUID)
    return job_id


# --- AC #1 + #4: shape + next_poll_ms ladder -------------------------------


async def test_pending_job_returns_500ms_poll_hint(client: httpx.AsyncClient, db_pool: Any) -> None:
    job_id = await _insert_job(db_pool, status="pending")
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == str(job_id)
    assert body["status"] == "pending"
    assert body["next_poll_ms"] == 500
    assert body["sidebar_payload"] is None
    assert body["sections"] == {}


async def test_extracting_returns_500ms_poll_hint(client: httpx.AsyncClient, db_pool: Any) -> None:
    job_id = await _insert_job(db_pool, status="extracting")
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["next_poll_ms"] == 500
    assert body["activity_label"] == "Extracting page content"


async def test_analyzing_returns_1500ms_poll_hint(client: httpx.AsyncClient, db_pool: Any) -> None:
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


async def test_sections_dict_round_trips(client: httpx.AsyncClient, db_pool: Any) -> None:
    sections = {
        "safety__moderation": {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {
                "harmful_content_matches": [_harmful_match("u-live-safety", "Live safety match")]
            },
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


async def test_poll_does_not_mutate_job_row(client: httpx.AsyncClient, db_pool: Any) -> None:
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


# --- Codex W4 Fix C: JobState page fields + Retry-After bucket math --------


async def test_job_state_includes_page_title_when_utterances_exist(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """JobState exposes job-level page metadata alongside utterance_count."""
    url = "https://example.com/with-utterances"
    job_id = await _insert_job(db_pool, status="analyzing", url=url)
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE vibecheck_jobs
            SET page_title = 'Example Title',
                page_kind = 'article',
                utterance_stream_type = 'article_or_monologue'
            WHERE job_id = $1
            """,
            job_id,
        )
        for i in range(3):
            await conn.execute(
                """
                INSERT INTO vibecheck_job_utterances
                    (job_id, kind, text, position)
                VALUES ($1, 'post', $2, $3)
                """,
                job_id,
                f"utterance {i}",
                i,
            )

    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_title"] == "Example Title"
    assert body["page_kind"] == "article"
    assert body["utterance_stream_type"] == "article_or_monologue"
    assert body["utterance_count"] == 3


async def test_job_state_page_fields_null_before_extraction(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Before the extractor runs, title is null and default metadata is returned."""
    job_id = await _insert_job(db_pool, status="pending")

    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_title"] is None
    assert body["page_kind"] == "other"
    assert body["utterance_stream_type"] == "unknown"
    assert body["utterance_count"] == 0


async def test_retry_after_reflects_minute_bucket_reset_not_hardcoded(
    client: httpx.AsyncClient, db_pool: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the 300/min sustained bucket rejects, Retry-After must reflect
    the moving-window reset time (> 1s, ≤ 60s) — not a hardcoded `1`
    (codex W4 P2-3)."""
    # Tight sustained budget (3/min) + generous burst (1000/s) so the
    # sustained limit is what actually trips. The 4th poll gets 429 because
    # the per-minute window still holds the earlier 3 hits.
    monkeypatch.setenv("RATE_LIMIT_POLL_BURST", "1000")
    monkeypatch.setenv("RATE_LIMIT_POLL_SUSTAINED", "3")
    from src.config import get_settings

    get_settings.cache_clear()
    analyze_route.limiter.reset()
    analyze_route.poll_rate_reset()

    job_id = await _insert_job(db_pool, status="pending")

    for _ in range(3):
        ok = await client.get(f"/api/analyze/{job_id}")
        assert ok.status_code == 200

    rejected = await client.get(f"/api/analyze/{job_id}")
    assert rejected.status_code == 429
    header_names_lower = {k.lower(): v for k, v in rejected.headers.items()}
    retry_after_raw = header_names_lower.get("retry-after")
    assert retry_after_raw is not None
    retry_after = int(retry_after_raw)
    # Must be strictly greater than the old hardcoded `1` and bounded by
    # the window size (60s) — pin the upper bound at the per-minute
    # window so a regression that re-introduces a tuple-shaped
    # GRANULARITY would surface here too (TASK-1473.51).
    assert 1 < retry_after <= 60

    get_settings.cache_clear()


async def test_retry_after_per_second_bucket_caps_at_one_second(
    client: httpx.AsyncClient, db_pool: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-second burst cap pins Retry-After to exactly 1s (TASK-1473.51).

    With burst=1/s and sustained=1000/min, the second poll within the
    same second trips the burst bucket. The window is 1 second, so
    Retry-After must be exactly 1.
    """
    monkeypatch.setenv("RATE_LIMIT_POLL_BURST", "1")
    monkeypatch.setenv("RATE_LIMIT_POLL_SUSTAINED", "1000")
    from src.config import get_settings

    get_settings.cache_clear()
    analyze_route.limiter.reset()
    analyze_route.poll_rate_reset()

    job_id = await _insert_job(db_pool, status="pending")

    ok = await client.get(f"/api/analyze/{job_id}")
    assert ok.status_code == 200
    rejected = await client.get(f"/api/analyze/{job_id}")
    assert rejected.status_code == 429
    header_names_lower = {k.lower(): v for k, v in rejected.headers.items()}
    retry_after_raw = header_names_lower.get("retry-after")
    assert retry_after_raw is not None
    assert int(retry_after_raw) == 1

    get_settings.cache_clear()


# --- TASK-1473.65.03: partial sidebar payload + activity fields -------------


async def test_analyzing_with_one_done_slot_returns_partial_sidebar_payload(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Non-terminal job with at least one done slot yields partial payload."""
    url = "https://example.com/partial"
    sections = {
        "safety__moderation": {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {
                "harmful_content_matches": [_harmful_match("u-live-safety", "Live safety match")]
            },
            "finished_at": datetime.now(UTC).isoformat(),
        },
        "tone_dynamics__flashpoint": {
            "state": "running",
            "attempt_id": str(uuid4()),
            "started_at": datetime.now(UTC).isoformat(),
        },
    }
    job_id = await _insert_job(db_pool, status="analyzing", sections=sections, url=url)
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "analyzing"
    assert body["sidebar_payload"] is not None
    assert body["sidebar_payload_complete"] is False
    assert body["sidebar_payload"]["source_url"] == url
    # Done slot data should be present; running slots get empty defaults
    assert body["sidebar_payload"]["safety"]["harmful_content_matches"] == [
        {
            "utterance_id": "u-live-safety",
            "utterance_text": "Live safety match",
            "max_score": 0.91,
            "categories": {"harassment": True},
            "scores": {"harassment": 0.91},
            "flagged_categories": ["harassment"],
            "source": "openai",
        }
    ]
    assert body["sidebar_payload"]["tone_dynamics"]["flashpoint_matches"] == []


async def test_non_terminal_partial_payload_includes_safety_and_headline_columns(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Partial polling payload includes completed aggregate columns."""
    sections = {
        "safety__moderation": {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"harmful_content_matches": []},
            "finished_at": datetime.now(UTC).isoformat(),
        },
    }
    job_id = await _insert_job(
        db_pool,
        status="analyzing",
        sections=sections,
        safety_recommendation={
            "level": "caution",
            "rationale": "Safety coverage is incomplete.",
            "top_signals": ["web risk unavailable"],
            "unavailable_inputs": ["web_risk"],
        },
        headline_summary={
            "text": "A developing story with partial analysis.",
            "kind": "synthesized",
            "unavailable_inputs": ["opinions"],
        },
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sidebar_payload_complete"] is False
    assert body["sidebar_payload"]["safety"]["recommendation"] == {
        "level": "caution",
        "rationale": "Safety coverage is incomplete.",
        "top_signals": ["web risk unavailable"],
        "unavailable_inputs": ["web_risk"],
    }
    assert body["sidebar_payload"]["headline"] == {
        "text": "A developing story with partial analysis.",
        "kind": "synthesized",
        "unavailable_inputs": ["opinions"],
    }


async def test_analyzing_with_zero_done_slots_returns_no_sidebar_payload(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Non-terminal job with no done slots must not fabricate a payload."""
    sections = {
        "safety__moderation": {
            "state": "running",
            "attempt_id": str(uuid4()),
            "started_at": datetime.now(UTC).isoformat(),
        },
    }
    job_id = await _insert_job(db_pool, status="analyzing", sections=sections)
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sidebar_payload"] is None
    assert body["sidebar_payload_complete"] is False


async def test_done_job_returns_sidebar_payload_complete_true(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Terminal done job with persisted payload marks it complete."""
    url = "https://example.com/complete"
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
    assert body["sidebar_payload"] is not None
    assert body["sidebar_payload_complete"] is True


async def test_failed_job_with_payload_is_not_marked_complete(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Failed jobs may carry minimal payloads but are not canonical-complete."""
    url = "https://example.com/failed-payload"
    payload = _minimal_sidebar_payload(url)
    job_id = await _insert_job(
        db_pool,
        status="failed",
        sidebar_payload=payload,
        error_code="unsupported_site",
        error_message="unsupported host",
        finished_at=datetime.now(UTC),
        url=url,
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["sidebar_payload"]["source_url"] == url
    assert body["sidebar_payload_complete"] is False


async def test_non_terminal_job_populates_activity_fields(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Analyzing/extracting jobs surface heartbeat and mapped activity label."""
    heartbeat = datetime.now(UTC)
    job_id = await _insert_job(
        db_pool,
        status="analyzing",
        last_stage="run_sections",
        heartbeat_at=heartbeat,
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "analyzing"
    assert body["activity_at"] is not None
    assert body["activity_label"] == "Running section analyses"


async def test_terminal_job_has_no_activity_fields(client: httpx.AsyncClient, db_pool: Any) -> None:
    """Done/failed jobs should not expose activity metadata."""
    url = "https://example.com/terminal"
    payload = _minimal_sidebar_payload(url)
    job_id = await _insert_job(
        db_pool,
        status="done",
        sidebar_payload=payload,
        finished_at=datetime.now(UTC),
        url=url,
        last_stage="finalize",
        heartbeat_at=datetime.now(UTC),
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity_at"] is None
    assert body["activity_label"] is None


@pytest.mark.parametrize(
    ("stage_key", "expected_label"),
    [
        ("extracting", "Extracting page content"),
        ("run_sections", "Running section analyses"),
        ("headline_summary", "Writing summary"),
        ("weather_report", "Writing weather report"),
        ("persist_utterances", "Saving page content"),
        ("set_analyzing", "Preparing analysis"),
        ("safety_recommendation", "Computing safety guidance"),
        pytest.param(
            "finalize",
            "Finalizing results",
            id="finalize-defensive-terminal-transition-label",
        ),
    ],
)
async def test_activity_label_maps_known_stage_keys(
    stage_key: str, expected_label: str, client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Known last_stage values are mapped to human-readable activity labels."""
    job_id = await _insert_job(
        db_pool,
        status="analyzing",
        last_stage=stage_key,
        heartbeat_at=datetime.now(UTC),
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity_label"] == expected_label


async def test_activity_label_falls_back_for_unknown_stage(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Unknown last_stage values degrade to a neutral readable fallback."""
    job_id = await _insert_job(
        db_pool,
        status="analyzing",
        last_stage="firecrawl_extract",
        heartbeat_at=datetime.now(UTC),
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity_label"] == "Running analysis"


async def test_partial_payload_does_not_persist_to_job_row(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Poll is read-only: partial payload must not write sidebar_payload."""
    url = "https://example.com/readonly"
    sections = {
        "safety__moderation": {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"harmful_content_matches": []},
            "finished_at": datetime.now(UTC).isoformat(),
        },
    }
    job_id = await _insert_job(db_pool, status="analyzing", sections=sections, url=url)
    async with db_pool.acquire() as conn:
        before = await conn.fetchrow(
            "SELECT sidebar_payload, updated_at FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )

    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sidebar_payload"] is not None
    assert body["sidebar_payload_complete"] is False

    async with db_pool.acquire() as conn:
        after = await conn.fetchrow(
            "SELECT sidebar_payload, updated_at FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert dict(before) == dict(after)
    assert after["sidebar_payload"] is None


async def test_stale_persisted_sidebar_payload_ignored_for_non_terminal(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Analyzing job with stale sidebar_payload from prior terminal state
    must not expose stale canonical content (TASK-1473.65.08)."""
    url = "https://example.com/stale"
    stale_payload = _minimal_sidebar_payload(url)
    stale_payload["facts_claims"]["claims_report"]["deduped_claims"] = [
        {
            "claim": "stale canonical claim",
            "utterance_ids": ["stale-u"],
            "supporting_text": ["stale text"],
        }
    ]
    sections = {
        "safety__moderation": {
            "state": "done",
            "attempt_id": str(uuid4()),
            "data": {"harmful_content_matches": []},
            "finished_at": datetime.now(UTC).isoformat(),
        },
        "tone_dynamics__flashpoint": {
            "state": "running",
            "attempt_id": str(uuid4()),
            "started_at": datetime.now(UTC).isoformat(),
        },
    }
    job_id = await _insert_job(
        db_pool,
        status="analyzing",
        sections=sections,
        sidebar_payload=stale_payload,
        url=url,
    )
    resp = await client.get(f"/api/analyze/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "analyzing"
    # The stale payload must NOT be returned
    assert body["sidebar_payload_complete"] is False
    # Done slot data from current sections should be present
    assert body["sidebar_payload"]["safety"]["harmful_content_matches"] == []
    assert body["sidebar_payload"]["facts_claims"]["claims_report"]["deduped_claims"] == []
    assert body["sidebar_payload"]["source_url"] == url


async def test_done_job_with_payload_still_returns_complete_true(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    """Terminal done job with sidebar_payload must still return it."""
    url = "https://example.com/terminal-payload"
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
    assert body["sidebar_payload_complete"] is True
    assert body["sidebar_payload"]["source_url"] == url
