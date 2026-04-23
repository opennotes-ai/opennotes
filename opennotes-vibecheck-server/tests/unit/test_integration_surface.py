"""Cross-cutting contract tests for the async-pipeline integration surface.

Each test exercises a contract that spans multiple components — claim CAS,
advisory-lock single-flight dedup, redelivery idempotency, retry-after-
terminal recovery, and SSRF allowlist. Per-feature happy paths live in
their dedicated suites (`test_slot_writes`, `test_worker`, `test_retry`,
`test_url_security`); this file fills the cross-cutting gaps the brief
calls out.

Coverage matrix (TASK-1473.21 AC#2):

  * claim CAS — `_claim_job` accepts only the matching expected_attempt_id
    and rejects every other UUID (paired with the worker-level test for
    end-to-end 200 no-op semantics).
  * advisory-lock fallback — second POST for the same URL within 2s blocks
    on the lock, observes the in-flight row, and returns the original
    job_id without inserting a second row.
  * redelivery idempotency — `run_job` called twice with the same envelope
    leaves the DB unchanged on the second call (200 no-op).
  * retry race — slot flips through failed → running → done → all-done
    triggers `maybe_finalize_job` to UPSERT vibecheck_analyses exactly once.
  * SSRF allowlist — `validate_public_http_url` rejects every PII / private
    class and accepts the public path.
  * sanitizer regex — uncovered PII classes that `test_observability.py`
    doesn't already exercise (user-home paths, GCP project IDs, bearer
    tokens, auth URLs).
"""
from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from src.analyses.schemas import SectionSlug
from src.jobs.orchestrator import (
    RunResult,
    _claim_job,
    run_job,
)
from src.main import app
from src.routes import analyze as analyze_route
from src.utils.error_sanitizer import _sanitize
from src.utils.url_security import InvalidURL, validate_public_http_url

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
"""


@pytest.fixture(autouse=True)
def _restore_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _REAL_GETADDRINFO)


@pytest.fixture(scope="module")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def db_pool(
    _postgres_container: PostgresContainer,
) -> AsyncIterator[Any]:
    raw = _postgres_container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=8)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS vibecheck_analyses CASCADE; "
            "DROP TABLE IF EXISTS vibecheck_jobs CASCADE;"
        )
        await conn.execute(_MINIMAL_DDL)
    try:
        yield pool
    finally:
        await pool.close()


# ===========================================================================
# Claim CAS — direct unit-level coverage of _claim_job.
# ===========================================================================


async def _insert_pending(
    pool: Any, attempt_id: UUID, *, url: str = "https://example.com/work"
) -> UUID:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (url, normalized_url, host, status, attempt_id)
            VALUES ($1, $1, 'example.com', 'pending', $2)
            RETURNING job_id
            """,
            url,
            attempt_id,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def test_claim_job_rejects_stale_expected_attempt(db_pool: Any) -> None:
    """`_claim_job` returns None when the expected_attempt_id has rotated."""
    current = uuid4()
    job_id = await _insert_pending(db_pool, current)

    stale = uuid4()
    result = await _claim_job(db_pool, job_id, stale)
    assert result is None
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, attempt_id FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row["status"] == "pending"
    assert row["attempt_id"] == current


async def test_claim_job_rotates_attempt_id_and_flips_status(
    db_pool: Any,
) -> None:
    """Successful claim mints a fresh attempt_id and flips status to extracting."""
    initial = uuid4()
    job_id = await _insert_pending(db_pool, initial)

    result = await _claim_job(db_pool, job_id, initial)
    assert result is not None
    new_attempt, url = result
    assert new_attempt != initial
    assert url == "https://example.com/work"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, attempt_id FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row["status"] == "extracting"
    assert row["attempt_id"] == new_attempt


async def test_claim_job_rejects_when_status_already_moved(
    db_pool: Any,
) -> None:
    """A job already in `extracting`/`analyzing`/`done`/`failed` cannot be re-claimed
    even if expected_attempt_id matches — the predicate `status = 'pending'`
    in the UPDATE rejects the second delivery."""
    current = uuid4()
    job_id = await _insert_pending(db_pool, current)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET status = 'extracting' WHERE job_id = $1",
            job_id,
        )

    result = await _claim_job(db_pool, job_id, current)
    assert result is None


# ===========================================================================
# Cloud Tasks redelivery idempotency at the run_job seam.
# ===========================================================================


async def test_run_job_redelivery_returns_no_op_after_first_run(
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two `run_job` calls with the same envelope must not double-process.

    First call claims, runs the (stubbed) pipeline, leaves the job in the
    state the pipeline ended in (we leave it `extracting` here).
    Second call: the original `expected_attempt_id` no longer matches —
    the row has rotated. `_claim_job` returns None, `run_job` returns
    200 no-op without touching the row.
    """
    from src.jobs import orchestrator

    pipeline_runs: list[UUID] = []

    async def _stub_pipeline(
        pool: Any,
        job_id: UUID,
        task_attempt: UUID,
        url: str,
        settings: Any,
    ) -> None:
        pipeline_runs.append(task_attempt)

    monkeypatch.setattr(orchestrator, "_run_pipeline", _stub_pipeline)
    monkeypatch.setattr(orchestrator, "HEARTBEAT_INTERVAL_SEC", 60.0)

    initial = uuid4()
    job_id = await _insert_pending(db_pool, initial)

    settings = object()
    first = await run_job(db_pool, job_id, initial, settings)  # pyright: ignore[reportArgumentType]
    second = await run_job(db_pool, job_id, initial, settings)  # pyright: ignore[reportArgumentType]

    assert isinstance(first, RunResult)
    assert isinstance(second, RunResult)
    assert first.status_code == 200
    assert second.status_code == 200
    # Pipeline executed exactly once — second call hit the stale-claim path.
    assert len(pipeline_runs) == 1


# ===========================================================================
# Retry-after-terminal: slot flips drive maybe_finalize_job.
# ===========================================================================


async def test_retry_after_failed_drives_finalize(db_pool: Any) -> None:
    """Slot lifecycle failed → running → done → all-done UPSERTs the cache.

    Walks one slot through the full retry-recovery sequence and asserts
    `maybe_finalize_job` is invoked once enough slots reach `done` to
    populate the `vibecheck_analyses` cache row.
    """
    from src.jobs.finalize import maybe_finalize_job
    from src.jobs.slots import (
        claim_slot,
        mark_slot_done,
        mark_slot_failed,
        retry_claim_slot,
        write_slot,
    )
    from tests.unit.test_slot_writes import _done_slot, _minimal_slot_payloads

    task_attempt = uuid4()
    url = "https://example.com/retry-then-finalize"
    job_id = await _insert_pending(db_pool, task_attempt, url=url)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET status = 'analyzing' WHERE job_id = $1",
            job_id,
        )

    # Seed all but one slug as already-done.
    payloads = _minimal_slot_payloads()
    target = SectionSlug.SAFETY_MODERATION
    for slug in SectionSlug:
        if slug is target:
            continue
        rows = await write_slot(
            db_pool,
            job_id,
            task_attempt,
            slug,
            _done_slot(payloads[slug]),
        )
        assert rows == 1

    # Target slot fails first.
    first_attempt = await claim_slot(db_pool, job_id, task_attempt, target)
    assert first_attempt is not None
    rows = await mark_slot_failed(
        db_pool,
        job_id,
        target,
        first_attempt,
        "synthetic failure",
        expected_task_attempt=task_attempt,
    )
    assert rows == 1

    # Mark the job as failed terminal so retry_claim_slot's gate is satisfied.
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET status = 'failed', "
            "error_code = 'extraction_failed', error_message = 'fail', "
            "finished_at = now() WHERE job_id = $1",
            job_id,
        )

    # Retry-claim the failed slot — flips status back to analyzing + new slot attempt.
    new_slot_attempt = await retry_claim_slot(db_pool, job_id, target, first_attempt)
    assert new_slot_attempt is not None

    # Worker completes the section successfully.
    rows = await mark_slot_done(
        db_pool,
        job_id,
        target,
        new_slot_attempt,
        payloads[target],
        expected_task_attempt=task_attempt,
    )
    assert rows == 1

    # Finalize the job — every slot is now `done`, so the cache UPSERTs.
    finalized = await maybe_finalize_job(
        db_pool, job_id, expected_task_attempt=task_attempt
    )
    assert finalized is True
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_analyses WHERE url = $1", url
        )
    assert rowcount == 1


# ===========================================================================
# Advisory-lock fallback: second POST blocks → returns first job_id.
# ===========================================================================


@pytest.fixture
def enqueue_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(analyze_route, "enqueue_job", mock)
    return mock


@pytest.fixture
async def http_client(
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


async def test_two_concurrent_posts_for_same_url_dedupe_to_one_job(
    http_client: httpx.AsyncClient,
    db_pool: Any,
) -> None:
    """Two simultaneous POSTs for the same URL must return the same job_id.

    The advisory lock serializes the two transactions; the second observer
    sees the in-flight row inserted by the first and returns its job_id
    instead of inserting a second row. Verifies the spec's single-flight
    dedup contract end-to-end via the public API.
    """
    payload = {"url": "https://example.com/dedup-target"}

    responses = await asyncio.gather(
        http_client.post("/api/analyze", json=payload),
        http_client.post("/api/analyze", json=payload),
    )

    job_ids = sorted({json.loads(r.text)["job_id"] for r in responses})
    statuses = {r.status_code for r in responses}
    assert statuses == {202}
    # Exactly one row in the DB; both clients got the same job_id back.
    async with db_pool.acquire() as conn:
        rowcount = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_jobs WHERE normalized_url = $1",
            "https://example.com/dedup-target",
        )
    assert rowcount == 1
    assert len(job_ids) == 1


# ===========================================================================
# SSRF allowlist — full coverage of rejection categories.
# ===========================================================================


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "gopher://example.com",
        "data:text/html,<script>",
    ],
)
def test_ssrf_rejects_disallowed_schemes(url: str) -> None:
    with pytest.raises(InvalidURL) as info:
        validate_public_http_url(url)
    assert info.value.reason == "scheme_not_allowed"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "https://localhost.",
        "http://metadata/x",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://something.internal/x",
        "http://service.local/x",
    ],
)
def test_ssrf_rejects_blocklist_hosts(url: str) -> None:
    with pytest.raises(InvalidURL) as info:
        validate_public_http_url(url)
    assert info.value.reason == "host_blocked"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://10.0.0.1/x",
        "http://192.168.1.1/x",
        "http://169.254.169.254/x",
        "http://[::1]/x",
        "http://[fd00::1]/x",
    ],
)
def test_ssrf_rejects_private_ip_literals(url: str) -> None:
    with pytest.raises(InvalidURL) as info:
        validate_public_http_url(url)
    assert info.value.reason == "private_ip"


def test_ssrf_rejects_resolved_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hostname that resolves into a private range is rejected."""

    def _private_resolver(*args: Any, **kwargs: Any) -> Any:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _private_resolver)
    with pytest.raises(InvalidURL) as info:
        validate_public_http_url("https://attacker.example.com/x")
    assert info.value.reason == "resolved_private_ip"


def test_ssrf_unresolvable_host_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _gaierror(*args: Any, **kwargs: Any) -> Any:
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", _gaierror)
    with pytest.raises(InvalidURL) as info:
        validate_public_http_url("https://does.not.exist.example/")
    assert info.value.reason == "unresolvable_host"


# ===========================================================================
# Sanitizer regex coverage — PII classes test_observability.py doesn't hit.
# ===========================================================================


class TestSanitizerCoverage:
    def test_user_home_path_macos_is_redacted(self) -> None:
        sanitized = _sanitize("/Users/alice/secret/file.png reading")
        assert "/Users/alice/" not in sanitized
        assert "<redacted>" in sanitized

    def test_user_home_path_linux_is_redacted(self) -> None:
        sanitized = _sanitize("/home/bob/.config/app.toml reading")
        assert "/home/bob/" not in sanitized
        assert "<redacted>" in sanitized

    def test_bearer_token_is_redacted(self) -> None:
        sanitized = _sanitize("Authorization: Bearer abc.def.ghi-jkl")
        assert "abc.def.ghi-jkl" not in sanitized
        assert "<redacted>" in sanitized

    def test_auth_url_is_redacted(self) -> None:
        sanitized = _sanitize(
            "Failed to call https://example.com/auth/login?ticket=secret"
        )
        # The whole auth URL collapses; the surrounding prose is preserved.
        assert "ticket=secret" not in sanitized
        assert "<redacted>" in sanitized

    def test_gcp_project_id_is_redacted(self) -> None:
        sanitized = _sanitize(
            "POST to google-mpf-internal-prod.com/api"
        )
        assert "google-mpf-internal-prod.com" not in sanitized
        assert "<redacted>" in sanitized

    def test_x_goog_signature_in_query_is_redacted(self) -> None:
        sanitized = _sanitize(
            "https://storage.googleapis.com/bucket/key?X-Goog-Signature=DEAD123"
        )
        assert "DEAD123" not in sanitized
        assert "<redacted>" in sanitized

    def test_sig_alias_in_query_is_redacted(self) -> None:
        sanitized = _sanitize("https://upload.example/path?sig=ABCDEF")
        assert "ABCDEF" not in sanitized
        assert "<redacted>" in sanitized

    def test_sign_alias_in_query_is_redacted(self) -> None:
        sanitized = _sanitize("https://example.io/file?sign=zZqW")
        assert "zZqW" not in sanitized
        assert "<redacted>" in sanitized

    def test_query_redaction_preserves_path_and_other_params(self) -> None:
        sanitized = _sanitize(
            "https://api.example.com/v1/widgets?page=2&token=SECRET&limit=10"
        )
        assert "SECRET" not in sanitized
        # Non-secret query keys must survive.
        assert "page=2" in sanitized
        assert "limit=10" in sanitized

    def test_sanitize_accepts_exception_input(self) -> None:
        sanitized = _sanitize(
            ValueError("Bearer leakedToken123")
        )
        assert "leakedToken123" not in sanitized
        assert "<redacted>" in sanitized
