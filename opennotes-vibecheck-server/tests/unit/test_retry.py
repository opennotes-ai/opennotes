"""Integration tests for section retry endpoint + worker (TASK-1473.13).

The retry path is a two-stage flow:

    1. Public `POST /api/analyze/{job_id}/retry/{slug}` — rate-limited per
       (ip, job_id), validates the retry gate (job terminal + slot failed +
       utterances extracted), CAS-flips the slot's `attempt_id` with state
       pending/failed → running, enqueues a Cloud Task. 202 on success,
       409 with a stable `error_code` on gate failure, 404 when the job is
       unknown.

    2. Internal `POST /_internal/jobs/{job_id}/sections/{slug}/run` —
       OIDC-verified, CAS-claims the slot on `expected_slot_attempt_id`,
       runs the one analysis, marks the slot
       done/failed, then calls `maybe_finalize_job` so a successful retry
       can rescue the cache once every slot is `done`.

Tests run against real Postgres (testcontainers) because the CAS guard
semantics and JSONB merge are the heart of the contract; mocking asyncpg
at that depth would verify the mock. OIDC verification and the Cloud
Tasks enqueue client are the only stubbed surfaces.
"""
from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.schemas import SectionSlug
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
    finished_at TIMESTAMPTZ,
    test_fail_slug TEXT
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
    page_title TEXT,
    page_kind TEXT NOT NULL DEFAULT 'other',
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
def enqueue_section_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace `enqueue_section_retry` at the analyze route import with an
    AsyncMock so retry tests observe call count + args without a real Cloud
    Tasks client.
    """
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(analyze_route, "enqueue_section_retry", mock)
    return mock


@pytest.fixture
def verify_oidc_mock(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """OIDC verification passes by default (for the worker endpoint)."""
    from src.auth import cloud_tasks_oidc
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VIBECHECK_SERVER_URL", "https://vibecheck.test")
    monkeypatch.setenv(
        "VIBECHECK_TASKS_ENQUEUER_SA",
        "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com",
    )
    get_settings.cache_clear()

    mock = MagicMock(
        return_value={
            "iss": "https://accounts.google.com",
            "aud": "https://vibecheck.test",
            "email": "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com",
            "email_verified": True,
        }
    )
    monkeypatch.setattr(cloud_tasks_oidc, "_verify_oauth2_token", mock)
    yield mock
    get_settings.cache_clear()


@pytest.fixture
async def client(
    db_pool: Any, enqueue_section_mock: AsyncMock, verify_oidc_mock: MagicMock
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


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


async def _insert_job_with_slot(
    pool: Any,
    *,
    job_status: str,
    slug: SectionSlug,
    slot_state: str,
    slot_attempt_id: UUID | None = None,
    with_utterance: bool = True,
    url: str = "https://example.com/retry-test",
) -> tuple[UUID, UUID]:
    """Insert a job + one seeded slot in the given state. Returns
    (job_id, slot_attempt_id). The slot's attempt_id is rotated fresh
    unless the caller passes one.
    """
    attempt_id = uuid4()
    slot_id = slot_attempt_id or uuid4()
    sections = {
        slug.value: {
            "state": slot_state,
            "attempt_id": str(slot_id),
            "data": None,
            "error": None,
            "started_at": None,
            "finished_at": (
                datetime.now(UTC).isoformat() if slot_state in ("done", "failed") else None
            ),
        }
    }
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id, sections
            )
            VALUES ($1, $1, 'example.com', $2, $3, $4::jsonb)
            RETURNING job_id
            """,
            url,
            job_status,
            attempt_id,
            json.dumps(sections),
        )
        if with_utterance:
            await conn.execute(
                """
                INSERT INTO vibecheck_job_utterances
                    (job_id, kind, text, position)
                VALUES ($1, 'post', 'hello world', 0)
                """,
                job_id,
            )
    assert isinstance(job_id, UUID)
    return job_id, slot_id


async def _read_slot(pool: Any, job_id: UUID, slug: SectionSlug) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT sections FROM vibecheck_jobs WHERE job_id = $1", job_id
        )
    if row is None:
        return None
    sections = json.loads(row) if isinstance(row, str) else dict(row)
    entry = sections.get(slug.value)
    return entry if isinstance(entry, dict) else None


# =========================================================================
# Retry endpoint — success path
# =========================================================================


async def test_retry_on_done_job_with_failed_slot_enqueues_section(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
) -> None:
    """Happy path: job=done, one slot=failed, utterances exist.

    The retry CAS-rotates the slot attempt_id, flips state to running, and
    enqueues exactly one section-retry Cloud Task with the new attempt_id.
    """
    slug = SectionSlug.SAFETY_MODERATION
    job_id, prior_slot_attempt = await _insert_job_with_slot(
        db_pool, job_status="done", slug=slug, slot_state="failed"
    )

    resp = await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == str(job_id)
    assert body["slug"] == slug.value
    new_slot_attempt = UUID(body["slot_attempt_id"])
    assert new_slot_attempt != prior_slot_attempt

    # Slot is now running with the rotated attempt_id.
    slot = await _read_slot(db_pool, job_id, slug)
    assert slot is not None
    assert slot["state"] == "running"
    assert slot["attempt_id"] == str(new_slot_attempt)

    # Exactly one enqueue with the new attempt_id.
    assert enqueue_section_mock.await_count == 1
    call = enqueue_section_mock.await_args
    assert call is not None
    call_kwargs: dict[str, Any] = dict(call.kwargs)
    if call.args:
        for name, value in zip(
            ("job_id", "slug", "expected_slot_attempt_id", "settings"),
            call.args,
            strict=False,
        ):
            call_kwargs.setdefault(name, value)
    assert call_kwargs["job_id"] == job_id
    assert call_kwargs["slug"] == slug
    assert call_kwargs["expected_slot_attempt_id"] == new_slot_attempt


async def test_retry_on_failed_job_with_failed_slot_also_allowed(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
) -> None:
    """AC #1 — gate accepts `status IN ('done', 'failed')`. A failed job with
    a failed slot (and extracted utterances) is retryable."""
    slug = SectionSlug.TONE_DYNAMICS_SCD
    job_id, _ = await _insert_job_with_slot(
        db_pool, job_status="failed", slug=slug, slot_state="failed"
    )

    resp = await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")

    assert resp.status_code == 202, resp.text
    assert enqueue_section_mock.await_count == 1


async def test_retry_on_done_job_refreshes_heartbeat(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
) -> None:
    """TASK-1474.27: a job that was previously running (and therefore has
    a non-null `heartbeat_at`) must have that timestamp refreshed when
    retry_claim_slot flips it back to `analyzing`. Without this, the
    sweeper's `COALESCE(heartbeat_at, updated_at, created_at) > 30s`
    check immediately marks the healthy retry as stale.
    """
    slug = SectionSlug.SAFETY_MODERATION
    job_id, _ = await _insert_job_with_slot(
        db_pool, job_status="done", slug=slug, slot_state="failed"
    )
    # Simulate a stale heartbeat from the original run.
    stale_heartbeat = datetime.now(UTC) - timedelta(minutes=10)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET heartbeat_at = $1 WHERE job_id = $2",
            stale_heartbeat,
            job_id,
        )

    resp = await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")
    assert resp.status_code == 202, resp.text

    async with db_pool.acquire() as conn:
        new_heartbeat = await conn.fetchval(
            "SELECT heartbeat_at FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert new_heartbeat is not None
    age = datetime.now(UTC) - new_heartbeat
    assert age < timedelta(seconds=5), (
        f"heartbeat_at must be refreshed on retry claim, got age={age}"
    )


# =========================================================================
# Retry endpoint — gate failures (AC #1)
# =========================================================================


async def test_retry_on_unknown_job_returns_404(
    client: httpx.AsyncClient, enqueue_section_mock: AsyncMock
) -> None:
    unknown = uuid4()
    resp = await client.post(
        f"/api/analyze/{unknown}/retry/{SectionSlug.SAFETY_MODERATION.value}"
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"
    assert enqueue_section_mock.await_count == 0


async def test_retry_on_analyzing_job_returns_409_cannot_retry_while_running(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
) -> None:
    """Gate step 3: job.status must be terminal (done/failed)."""
    slug = SectionSlug.SAFETY_MODERATION
    job_id, _ = await _insert_job_with_slot(
        db_pool, job_status="analyzing", slug=slug, slot_state="failed"
    )

    resp = await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "cannot_retry_while_running"
    assert enqueue_section_mock.await_count == 0


async def test_retry_on_job_with_null_utterances_returns_409(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
) -> None:
    """Gate step 2: no utterances → retry is meaningless (extraction must
    succeed before a slot can be re-run)."""
    slug = SectionSlug.SAFETY_MODERATION
    job_id, _ = await _insert_job_with_slot(
        db_pool,
        job_status="failed",
        slug=slug,
        slot_state="failed",
        with_utterance=False,
    )

    resp = await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")

    assert resp.status_code == 409
    assert (
        resp.json()["error_code"] == "can_only_retry_after_extraction_succeeds"
    )
    assert enqueue_section_mock.await_count == 0


async def test_retry_on_slot_not_in_failed_state_returns_409(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
) -> None:
    """Gate step 4: only `failed` slots are retryable (done/running/pending
    are rejected)."""
    slug = SectionSlug.SAFETY_MODERATION
    job_id, _ = await _insert_job_with_slot(
        db_pool, job_status="done", slug=slug, slot_state="done"
    )

    resp = await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "slot_not_in_retryable_state"
    assert enqueue_section_mock.await_count == 0


async def test_retry_on_missing_slot_returns_409(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
) -> None:
    """A slug that was never populated on this job (e.g., extraction failed
    before fan-out): treat as not-retryable too — the slot has no prior
    attempt to CAS against."""
    slug = SectionSlug.SAFETY_MODERATION
    # Insert a job with a different slot; the requested slug will be missing.
    other = SectionSlug.TONE_DYNAMICS_SCD
    job_id, _ = await _insert_job_with_slot(
        db_pool, job_status="done", slug=other, slot_state="failed"
    )

    resp = await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "slot_not_in_retryable_state"
    assert enqueue_section_mock.await_count == 0


async def test_retry_rejects_unknown_slug_with_422(
    client: httpx.AsyncClient,
) -> None:
    """Enum coercion at the path-parameter level — 422 before the handler."""
    resp = await client.post(f"/api/analyze/{uuid4()}/retry/not_a_real_slug")
    assert resp.status_code == 422


# =========================================================================
# Retry endpoint — AC #4: concurrent clicks, only one lands
# =========================================================================


async def test_concurrent_retry_calls_only_one_lands(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two Retry clicks with overlapping CAS windows: only one UPDATE lands.

    Under real multi-process traffic the two handlers can reach the CAS
    simultaneously. We simulate that here by intercepting `retry_claim_slot`:
    both callers enter the instrumented wrapper, both read the same prior
    slot_attempt_id, both call through to the real helper — the second CAS
    necessarily fails because the first rotated the attempt_id.

    Exactly one 202 + exactly one 409 `concurrent_retry_already_claimed` +
    exactly one enqueue.
    """
    from src.routes import analyze as analyze_mod

    slug = SectionSlug.FACTS_CLAIMS_DEDUP
    job_id, _ = await _insert_job_with_slot(
        db_pool, job_status="done", slug=slug, slot_state="failed"
    )

    real = analyze_mod.retry_claim_slot
    ready = asyncio.Event()
    both_entered = asyncio.Event()
    entered_count = 0

    async def _racing_retry_claim_slot(*args: Any, **kwargs: Any) -> UUID | None:
        nonlocal entered_count
        entered_count += 1
        if entered_count == 1:
            # First caller: park so the second caller can reach the same CAS.
            await ready.wait()
        else:
            both_entered.set()
            ready.set()
        return await real(*args, **kwargs)

    monkeypatch.setattr(analyze_mod, "retry_claim_slot", _racing_retry_claim_slot)

    async def one_retry() -> httpx.Response:
        return await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")

    results = await asyncio.gather(one_retry(), one_retry())
    assert both_entered.is_set(), "both callers must have reached retry_claim_slot"
    statuses = sorted(r.status_code for r in results)
    assert statuses == [202, 409], [r.status_code for r in results]

    # The 409 must carry the `concurrent_retry_already_claimed` slug.
    rejected = next(r for r in results if r.status_code == 409)
    assert rejected.json()["error_code"] == "concurrent_retry_already_claimed"

    # Exactly one enqueue — the CAS-winner.
    assert enqueue_section_mock.await_count == 1


# =========================================================================
# Retry endpoint — enqueue failure rolls slot back to failed
# =========================================================================


async def test_retry_enqueue_failure_marks_slot_failed_again_and_500(
    client: httpx.AsyncClient,
    db_pool: Any,
    enqueue_section_mock: AsyncMock,
) -> None:
    """If the Cloud Task enqueue raises after the slot has been flipped to
    running, the handler reverts the slot to failed (with error_code=internal)
    and returns 500."""
    enqueue_section_mock.side_effect = RuntimeError("cloud tasks unreachable")
    slug = SectionSlug.TONE_DYNAMICS_FLASHPOINT
    job_id, _ = await _insert_job_with_slot(
        db_pool, job_status="done", slug=slug, slot_state="failed"
    )

    resp = await client.post(f"/api/analyze/{job_id}/retry/{slug.value}")

    assert resp.status_code == 500
    assert resp.json()["error_code"] == "internal"

    slot = await _read_slot(db_pool, job_id, slug)
    assert slot is not None
    assert slot["state"] == "failed"


# =========================================================================
# Section-retry worker target
# =========================================================================


async def _post_section_run(
    client: httpx.AsyncClient,
    *,
    job_id: UUID,
    slug: SectionSlug,
    expected_slot_attempt_id: UUID,
) -> httpx.Response:
    return await client.post(
        f"/_internal/jobs/{job_id}/sections/{slug.value}/run",
        json={
            "job_id": str(job_id),
            "slug": slug.value,
            "expected_slot_attempt_id": str(expected_slot_attempt_id),
        },
        headers={"Authorization": "Bearer fake.jwt.token"},
    )


async def test_section_retry_worker_requires_oidc(
    client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    """Missing bearer → 401 before the handler touches the DB."""
    slug = SectionSlug.SAFETY_MODERATION
    job_id, prior = await _insert_job_with_slot(
        db_pool, job_status="done", slug=slug, slot_state="running"
    )
    resp = await client.post(
        f"/_internal/jobs/{job_id}/sections/{slug.value}/run",
        json={
            "job_id": str(job_id),
            "slug": slug.value,
            "expected_slot_attempt_id": str(prior),
        },
    )
    assert resp.status_code == 401


async def test_section_retry_worker_runs_analysis_and_finalizes(
    client: httpx.AsyncClient,
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With every other slot already `done`, the worker runs the retried
    slot, marks it done, and `maybe_finalize_job` upserts the cache — so a
    failed-then-retried job recovers its sidebar_payload.
    """
    # Seed: every slot done except one that's `running` (we pretend the
    # retry endpoint already CAS-flipped it). The worker will fill it.
    now = datetime.now(UTC).isoformat()
    target_slug = SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT
    sections: dict[str, Any] = {}
    running_attempt = uuid4()
    for s in SectionSlug:
        if s is target_slug:
            sections[s.value] = {
                "state": "running",
                "attempt_id": str(running_attempt),
                "data": None,
                "started_at": now,
            }
        else:
            # Mark every other slot done with the matching empty payload.
            from src.jobs.orchestrator import _empty_section_data

            sections[s.value] = {
                "state": "done",
                "attempt_id": str(uuid4()),
                "data": _empty_section_data(s),
                "finished_at": now,
            }

    url = "https://example.com/retry-finalize"
    task_attempt = uuid4()
    async with db_pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id, sections
            )
            VALUES ($1, $1, 'example.com', 'analyzing', $2, $3::jsonb)
            RETURNING job_id
            """,
            url,
            task_attempt,
            json.dumps(sections),
        )
        await conn.execute(
            """
            INSERT INTO vibecheck_job_utterances (job_id, kind, text, position)
            VALUES ($1, 'post', 'body', 0)
            """,
            job_id,
        )
    assert isinstance(job_id, UUID)

    from src.jobs import orchestrator

    async def _retry_handler(
        pool: Any,
        job_id: Any,
        task_attempt: Any,
        payload: Any,
        settings: Any,
    ) -> dict[str, Any]:
        assert payload is None
        return {
            "sentiment_stats": {
                "per_utterance": [
                    {
                        "utterance_id": "retry-u",
                        "label": "neutral",
                        "valence": 0.0,
                    }
                ],
                "positive_pct": 0.0,
                "negative_pct": 0.0,
                "neutral_pct": 100.0,
                "mean_valence": 0.0,
            }
        }

    monkeypatch.setitem(orchestrator._SECTION_HANDLERS, target_slug, _retry_handler)

    async def _fail_if_loaded(*args: Any, **kwargs: Any) -> object:
        pytest.fail("section retry should not eagerly load utterances")

    monkeypatch.setattr(
        orchestrator, "load_job_utterances", _fail_if_loaded, raising=False
    )

    resp = await _post_section_run(
        client,
        job_id=job_id,
        slug=target_slug,
        expected_slot_attempt_id=running_attempt,
    )
    assert resp.status_code == 200, resp.text

    # Slot moved to done.
    slot = await _read_slot(db_pool, job_id, target_slug)
    assert slot is not None, "target slot should still exist"
    assert slot["state"] == "done"

    # maybe_finalize_job ran and the cache has a fresh row for the URL.
    async with db_pool.acquire() as conn:
        cache_row = await conn.fetchrow(
            "SELECT url, sidebar_payload FROM vibecheck_analyses WHERE url = $1",
            url,
        )
    assert cache_row is not None, "maybe_finalize_job should have UPSERTed cache"


async def test_section_retry_worker_idempotent_on_stale_slot_attempt(
    client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    """Stale redelivery (the slot has already been claimed+rotated by a
    newer worker) must return 200 without touching the slot.
    """
    slug = SectionSlug.SAFETY_MODERATION
    job_id, current_slot_attempt = await _insert_job_with_slot(
        db_pool, job_status="analyzing", slug=slug, slot_state="running"
    )
    stale = uuid4()
    assert stale != current_slot_attempt

    resp = await _post_section_run(
        client, job_id=job_id, slug=slug, expected_slot_attempt_id=stale
    )
    assert resp.status_code == 200

    # Slot is untouched.
    slot = await _read_slot(db_pool, job_id, slug)
    assert slot is not None
    assert slot["state"] == "running"
    assert slot["attempt_id"] == str(current_slot_attempt)
