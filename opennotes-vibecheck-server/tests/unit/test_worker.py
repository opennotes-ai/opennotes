"""Integration tests for POST /_internal/jobs/{job_id}/run (TASK-1473.12).

The internal worker endpoint is the Cloud Tasks push-queue handler. It
verifies the OIDC token, CAS-claims the job, spawns a heartbeat, runs the
scrape+extract+per-section pipeline, and returns the HTTP status Cloud
Tasks interprets as retry (503) or no-retry (200).

Tests run against real Postgres (testcontainers) because the CAS guard
semantics and `sections` JSONB merge are the heart of what we're testing;
mocking asyncpg at that depth would verify the mock rather than the
handler. OIDC verification is mocked at the `id_token.verify_oauth2_token`
call site — every other dependency is real.

The orchestrator itself (`src.jobs.orchestrator.run_job`) is tested via
the HTTP surface since that's the integration contract Cloud Tasks
exercises. A small set of orchestrator-only tests cover the heartbeat loop
separately (those don't need HTTP plumbing).
"""
from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.firecrawl_client import ScrapeMetadata
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
    test_fail_slug TEXT,
    safety_recommendation JSONB,
    last_stage TEXT
);

CREATE INDEX vibecheck_jobs_normalized_url_idx
    ON vibecheck_jobs(normalized_url);
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
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE;"
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
def verify_oidc_mock(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Default: OIDC verification passes for the configured SA + audience.

    Individual tests override by setting `verify_oidc_mock.return_value` or
    `.side_effect` to simulate invalid token payloads.
    """
    from src.auth import cloud_tasks_oidc

    # Point settings at a known audience + SA so the default payload matches.
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
    db_pool: Any, verify_oidc_mock: MagicMock
) -> AsyncIterator[httpx.AsyncClient]:
    app.state.cache = None
    app.state.db_pool = db_pool
    analyze_route.limiter.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c
    app.state.db_pool = None
    analyze_route.limiter.reset()


# --- Helpers to stub the orchestrator pipeline ----------------------------


async def _insert_pending_job(
    pool: Any,
    *,
    url: str = "https://example.com/work",
    attempt_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    attempt = attempt_id or uuid4()
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, status, attempt_id)
            VALUES ($1, $1, 'example.com', 'pending', $2)
            RETURNING job_id
            """,
            url,
            attempt,
        )
    assert isinstance(job_id, UUID)
    return job_id, attempt


# =========================================================================
# AC #1 — OIDC verification
# =========================================================================


async def test_oidc_missing_bearer_returns_401(
    client: httpx.AsyncClient, db_pool: Any
) -> None:
    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
    )
    assert resp.status_code == 401


async def test_oidc_wrong_audience_returns_401(
    client: httpx.AsyncClient,
    db_pool: Any,
    verify_oidc_mock: MagicMock,
) -> None:
    verify_oidc_mock.return_value = {
        "iss": "https://accounts.google.com",
        "aud": "https://evil.test",
        "email": "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com",
        "email_verified": True,
    }
    # Make verify_oauth2_token itself raise for wrong audience — the real
    # google.oauth2 id_token API raises ValueError when audience doesn't
    # match the expected arg. We simulate that: the handler should still
    # 401 either way.
    verify_oidc_mock.side_effect = ValueError("audience mismatch")

    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 401


async def test_oidc_wrong_email_returns_401(
    client: httpx.AsyncClient,
    db_pool: Any,
    verify_oidc_mock: MagicMock,
) -> None:
    verify_oidc_mock.return_value = {
        "iss": "https://accounts.google.com",
        "aud": "https://vibecheck.test",
        "email": "attacker@evil.test",
        "email_verified": True,
    }
    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 401


async def test_oidc_wrong_issuer_returns_401(
    client: httpx.AsyncClient,
    db_pool: Any,
    verify_oidc_mock: MagicMock,
) -> None:
    verify_oidc_mock.return_value = {
        "iss": "https://evil.issuer",
        "aud": "https://vibecheck.test",
        "email": "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com",
        "email_verified": True,
    }
    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 401


async def test_oidc_email_unverified_returns_401(
    client: httpx.AsyncClient,
    db_pool: Any,
    verify_oidc_mock: MagicMock,
) -> None:
    verify_oidc_mock.return_value = {
        "iss": "https://accounts.google.com",
        "aud": "https://vibecheck.test",
        "email": "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com",
        "email_verified": False,
    }
    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 401


# =========================================================================
# AC #2 — CAS claim: stale attempt_id is a 200 idempotent no-op.
# =========================================================================


async def test_claim_fails_when_expected_attempt_id_stale(
    client: httpx.AsyncClient,
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloud Tasks redelivery carrying a superseded attempt_id: return 200
    no-op without invoking the orchestrator pipeline."""
    from src.jobs import orchestrator

    # Orchestrator must NOT be called — we spy with a sentinel raise.
    ran = asyncio.Event()

    async def _should_not_run(*_args: Any, **_kwargs: Any) -> Any:
        ran.set()
        raise AssertionError("orchestrator must not run on stale claim")

    monkeypatch.setattr(orchestrator, "_run_pipeline", _should_not_run)

    job_id, current_attempt = await _insert_pending_job(db_pool)
    stale_attempt = uuid4()
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={
            "job_id": str(job_id),
            "expected_attempt_id": str(stale_attempt),
        },
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 200
    assert not ran.is_set()
    # Job row is untouched.
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, attempt_id FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row["status"] == "pending"
    assert row["attempt_id"] == current_attempt


async def test_claim_succeeds_and_handler_runs_pipeline(
    client: httpx.AsyncClient,
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh claim: status flips from pending→extracting with a new
    `attempt_id`, and `_run_pipeline` is invoked with that new attempt."""
    from src.jobs import orchestrator

    invoked_with: dict[str, Any] = {}

    async def _fake_pipeline(
        pool: Any,
        job_id: UUID,
        task_attempt: UUID,
        url: str,
        settings: Any,
        *,
        test_fail_slug: str | None = None,
    ) -> None:
        invoked_with["job_id"] = job_id
        invoked_with["task_attempt"] = task_attempt
        invoked_with["url"] = url

    monkeypatch.setattr(orchestrator, "_run_pipeline", _fake_pipeline)

    job_id, attempt = await _insert_pending_job(
        db_pool, url="https://example.com/fresh-work"
    )
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 200, resp.text
    assert invoked_with["job_id"] == job_id
    # Claim rotates attempt_id: the pipeline receives the *new* one, not the
    # expected_attempt_id from the request body.
    assert invoked_with["task_attempt"] != attempt

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, attempt_id FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    # Status is whatever the pipeline left it at. Since we stubbed the
    # pipeline, status should be `extracting` from the claim transition.
    assert row["status"] == "extracting"
    assert row["attempt_id"] == invoked_with["task_attempt"]


# =========================================================================
# AC #3 — Heartbeat task bumps `heartbeat_at` during long-running work.
# =========================================================================


async def test_heartbeat_bumps_during_long_pipeline(
    client: httpx.AsyncClient,
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a 0.25s heartbeat interval and a pipeline that awaits 0.8s, the
    heartbeat task must bump `heartbeat_at` at least twice before the
    pipeline returns."""
    from src.jobs import orchestrator

    ticks_seen: list[datetime] = []

    async def _slow_pipeline(
        pool: Any,
        job_id: UUID,
        task_attempt: UUID,
        url: str,
        settings: Any,
        *,
        test_fail_slug: str | None = None,
    ) -> None:
        # Sleep long enough for multiple heartbeat intervals.
        await asyncio.sleep(0.8)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT heartbeat_at FROM vibecheck_jobs WHERE job_id = $1",
                job_id,
            )
        if rows and rows[0]["heartbeat_at"] is not None:
            ticks_seen.append(rows[0]["heartbeat_at"])

    monkeypatch.setattr(orchestrator, "_run_pipeline", _slow_pipeline)
    monkeypatch.setattr(orchestrator, "HEARTBEAT_INTERVAL_SEC", 0.25)

    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 200
    # The pipeline saw at least one heartbeat that was bumped from NULL.
    assert ticks_seen, "heartbeat loop never wrote heartbeat_at"


# =========================================================================
# AC #4 — TransientError resets the job and returns 503 for Cloud Tasks retry.
# =========================================================================


async def test_transient_error_resets_and_returns_503(
    client: httpx.AsyncClient,
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.jobs import orchestrator

    async def _raise_transient(
        pool: Any,
        job_id: UUID,
        task_attempt: UUID,
        url: str,
        settings: Any,
        *,
        test_fail_slug: str | None = None,
    ) -> None:
        raise orchestrator.TransientError("firecrawl 503")

    monkeypatch.setattr(orchestrator, "_run_pipeline", _raise_transient)

    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 503
    # Job row: status reverted to `pending` so the retry can re-claim.
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, attempt_id FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row["status"] == "pending"
    # The attempt_id on the row is the body's expected_attempt_id — reset to
    # the caller's envelope so the retry can re-claim.
    assert row["attempt_id"] == attempt


# =========================================================================
# AC #5 — TerminalError: job flipped to failed with classified error_code; 200.
# =========================================================================


async def test_terminal_error_marks_failed_and_returns_200(
    client: httpx.AsyncClient,
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.analyses.schemas import ErrorCode
    from src.jobs import orchestrator

    async def _raise_terminal(
        pool: Any,
        job_id: UUID,
        task_attempt: UUID,
        url: str,
        settings: Any,
        *,
        test_fail_slug: str | None = None,
    ) -> None:
        raise orchestrator.TerminalError(
            ErrorCode.EXTRACTION_FAILED, "extraction lost contact with gemini"
        )

    monkeypatch.setattr(orchestrator, "_run_pipeline", _raise_terminal)

    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 200
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, error_code, error_message FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row["status"] == "failed"
    assert row["error_code"] == "extraction_failed"
    assert row["error_message"] == "extraction lost contact with gemini"


# =========================================================================
# AC #6 — Unclassified exception: treated as transient (reset + 503).
# =========================================================================


async def test_unclassified_exception_treated_as_transient(
    client: httpx.AsyncClient,
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.jobs import orchestrator

    async def _blow_up(
        pool: Any,
        job_id: UUID,
        task_attempt: UUID,
        url: str,
        settings: Any,
        *,
        test_fail_slug: str | None = None,
    ) -> None:
        raise RuntimeError("something unexpected")

    monkeypatch.setattr(orchestrator, "_run_pipeline", _blow_up)

    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 503
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, attempt_id FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    # Reverted to pending for Cloud Tasks retry.
    assert row["status"] == "pending"
    assert row["attempt_id"] == attempt


# =========================================================================
# AC #7 — Post-scrape revalidation: redirect to private host → invalid_url.
# =========================================================================


async def test_post_scrape_private_redirect_marks_invalid_url(
    client: httpx.AsyncClient,
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestrator's scrape step: final `metadata.source_url` points at the
    GCE metadata service. Revalidate, flip the job to invalid_url, discard
    the cached scrape. Return 200 (no retry)."""
    from src.cache import scrape_cache as scrape_cache_module
    from src.jobs import orchestrator

    # Capture orchestrator's scrape cache so we can assert discard happened.
    evict_calls: list[str] = []

    class _FakeCache:
        async def get(self, url: str) -> Any:
            return None

        async def put(self, url: str, scrape: Any) -> Any:
            return scrape_cache_module.CachedScrape(
                markdown="hi",
                html=None,
                metadata=ScrapeMetadata(source_url="http://169.254.169.254/"),
                storage_key="mock-storage-key",
            )

        async def evict(self, url: str) -> None:
            evict_calls.append(url)

    fake_client = MagicMock()

    async def _scrape(*args: Any, **kwargs: Any) -> Any:
        return MagicMock(
            markdown="hi",
            html=None,
            raw_html=None,
            screenshot=None,
            links=None,
            metadata=ScrapeMetadata(source_url="http://169.254.169.254/"),
            warning=None,
        )

    fake_client.scrape = _scrape

    monkeypatch.setattr(
        orchestrator, "_build_scrape_cache", lambda _settings: _FakeCache()
    )
    monkeypatch.setattr(
        orchestrator, "_build_firecrawl_client", lambda _settings: fake_client
    )

    # Stub section fanout so the test focuses on the post-scrape check —
    # the pipeline should raise TerminalError *before* any section runs.
    async def _fail(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("sections must not run after invalid redirect")

    monkeypatch.setattr(orchestrator, "_run_all_sections", _fail)

    job_id, attempt = await _insert_pending_job(db_pool)
    resp = await client.post(
        f"/_internal/jobs/{job_id}/run",
        json={"job_id": str(job_id), "expected_attempt_id": str(attempt)},
        headers={"Authorization": "Bearer fake.jwt.token"},
    )
    assert resp.status_code == 200
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, error_code, error_message FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row["status"] == "failed"
    assert row["error_code"] == "invalid_url"
    assert "private" in (row["error_message"] or "").lower()
    # Cache was told to discard the bad scrape.
    assert evict_calls, "scrape cache was not told to evict the invalid redirect"


# =========================================================================
# Codex P0-1 — enqueue_job actually publishes a Cloud Task.
# =========================================================================


async def test_enqueue_job_publishes_cloud_task_with_oidc() -> None:
    """`enqueue_job` must invoke CloudTasksAsyncClient.create_task with an
    OIDC-signed target pointing at VIBECHECK_SERVER_URL/_internal/jobs/{job_id}/run."""
    from src.config import Settings
    from src.jobs import enqueue as enqueue_module

    settings = Settings(
        VIBECHECK_TASKS_PROJECT="open-notes-core",
        VIBECHECK_TASKS_LOCATION="us-central1",
        VIBECHECK_TASKS_QUEUE="vibecheck-jobs",
        VIBECHECK_TASKS_ENQUEUER_SA="vibecheck-tasks@open-notes-core.iam.gserviceaccount.com",
        VIBECHECK_SERVER_URL="https://vibecheck.opennotes.ai",
    )
    job_id = UUID("11111111-1111-1111-1111-111111111111")
    attempt_id = UUID("22222222-2222-2222-2222-222222222222")

    fake_client = MagicMock()
    fake_client.queue_path = MagicMock(
        return_value="projects/open-notes-core/locations/us-central1/queues/vibecheck-jobs"
    )
    fake_client.create_task = AsyncMock(return_value=MagicMock(name="Task"))

    with patch.object(
        enqueue_module, "_get_async_client", return_value=fake_client
    ):
        await enqueue_module.enqueue_job(job_id, attempt_id, settings)

    # queue_path computed from settings.
    fake_client.queue_path.assert_called_once_with(
        "open-notes-core", "us-central1", "vibecheck-jobs"
    )
    # create_task received a request whose task has OIDC token + URL.
    fake_client.create_task.assert_awaited_once()
    call_kwargs = fake_client.create_task.await_args.kwargs
    request = call_kwargs.get("request") or fake_client.create_task.await_args.args[0]
    # Validate the task payload.
    task = request["task"] if isinstance(request, dict) else request.task
    http_req = task["http_request"] if isinstance(task, dict) else task.http_request
    url = (
        http_req["url"]
        if isinstance(http_req, dict)
        else http_req.url
    )
    assert url == f"https://vibecheck.opennotes.ai/_internal/jobs/{job_id}/run"
    oidc_token = (
        http_req["oidc_token"]
        if isinstance(http_req, dict)
        else http_req.oidc_token
    )
    email = (
        oidc_token["service_account_email"]
        if isinstance(oidc_token, dict)
        else oidc_token.service_account_email
    )
    assert email == "vibecheck-tasks@open-notes-core.iam.gserviceaccount.com"
    # Audience must match the server URL (OIDC verify checks exact match).
    audience = (
        oidc_token["audience"]
        if isinstance(oidc_token, dict)
        else oidc_token.audience
    )
    assert audience == "https://vibecheck.opennotes.ai"
    # TASK-1474.27: dispatch_deadline must be set so Cloud Tasks does not
    # cancel the redelivered request before the Cloud Run timeout fires.
    deadline = (
        task["dispatch_deadline"]
        if isinstance(task, dict)
        else task.dispatch_deadline
    )
    seconds = (
        deadline["seconds"]
        if isinstance(deadline, dict)
        else deadline.seconds
    )
    assert seconds == 1200


async def test_enqueue_job_raises_when_settings_missing() -> None:
    """Safety: if Cloud Tasks settings are empty, fail loudly instead of
    silently publishing to the wrong queue."""
    from src.config import Settings
    from src.jobs import enqueue as enqueue_module

    settings = Settings()  # all defaults blank
    with pytest.raises(RuntimeError, match="VIBECHECK_TASKS_"):
        await enqueue_module.enqueue_job(uuid4(), uuid4(), settings)
