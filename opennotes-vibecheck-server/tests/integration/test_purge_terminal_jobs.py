"""Soft-delete purge integration tests (TASK-1541.01, TASK-1540.01).

The production schema schedules `vibecheck_purge_terminal_jobs()` via
`pg_cron` once per hour. This test invokes the function directly to
assert that terminal jobs older than 7 days are soft-deleted via the
`expired_at` marker (with sensitive payload columns nulled and child
utterances hard-deleted), while fresh terminal jobs are untouched, and
that the operation is idempotent across repeated calls.

TASK-1540.01 adds an operator-controlled `protected` flag that exempts
a job and its matching `vibecheck_analyses` cache row from the purge.

Times are simulated by directly UPDATEing `finished_at` backwards rather
than literally sleeping, so the test stays fast.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest


async def _insert_terminal_job(
    pool: Any,
    *,
    url: str,
    status: str,
    finished_delta: timedelta,
    sidebar_payload: str = '{"verdict": "ok"}',
    sections: str = '{"summary": {"text": "done"}}',
    error_message: str | None = "prior failure note",
    headline_summary: str = '{"text": "headline"}',
    safety_recommendation: str = '{"level": "low"}',
    last_stage: str = "analyze",
    protected: bool = False,
) -> UUID:
    finished_at = datetime.now(UTC) - finished_delta
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id,
                finished_at, sidebar_payload, sections, error_message,
                headline_summary, safety_recommendation, last_stage,
                protected
            )
            VALUES (
                $1, $1, 'example.com', $2, $3,
                $4, $5::jsonb, $6::jsonb, $7, $8::jsonb, $9::jsonb, $10,
                $11
            )
            RETURNING job_id
            """,
            url,
            status,
            uuid4(),
            finished_at,
            sidebar_payload,
            sections,
            error_message,
            headline_summary,
            safety_recommendation,
            last_stage,
            protected,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def _insert_analyses_row(
    pool: Any,
    *,
    url: str,
    expires_delta: timedelta,
    sidebar_payload: str = '{"verdict": "ok"}',
) -> None:
    expires_at = datetime.now(UTC) - expires_delta
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_analyses (url, sidebar_payload, expires_at)
            VALUES ($1, $2::jsonb, $3)
            """,
            url,
            sidebar_payload,
            expires_at,
        )


async def _analyses_exists(pool: Any, *, url: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM vibecheck_analyses WHERE url = $1",
            url,
        )
    return row is not None


async def _insert_pdf_archive(
    pool: Any,
    *,
    job_id: UUID,
    expires_delta: timedelta,
    html: str = "<html>archived</html>",
) -> None:
    expires_at = datetime.now(UTC) - expires_delta
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_pdf_archives (job_id, html, expires_at)
            VALUES ($1, $2, $3)
            """,
            job_id,
            html,
            expires_at,
        )


async def _pdf_archive_exists(pool: Any, *, job_id: UUID) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM vibecheck_pdf_archives WHERE job_id = $1",
            job_id,
        )
    return row is not None


async def _insert_utterance(pool: Any, job_id: UUID, *, text: str = "hello") -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vibecheck_job_utterances (job_id, kind, text)
            VALUES ($1, 'post', $2)
            """,
            job_id,
            text,
        )


async def _read_job(pool: Any, job_id: UUID) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT job_id, status, expired_at, sidebar_payload, sections,
                   error_message, headline_summary, safety_recommendation,
                   last_stage, protected
            FROM vibecheck_jobs
            WHERE job_id = $1
            """,
            job_id,
        )
    return dict(row) if row is not None else None


async def _count_utterances(pool: Any, job_id: UUID) -> int:
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM vibecheck_job_utterances WHERE job_id = $1",
            job_id,
        )
    return int(count)


async def _purge(pool: Any) -> int:
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT vibecheck_purge_terminal_jobs()")
    return int(result)


@pytest.mark.asyncio
async def test_old_done_job_soft_deleted_with_payload_nulled(db_pool: Any) -> None:
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/old-done",
        status="done",
        finished_delta=timedelta(days=8),
    )
    await _insert_utterance(db_pool, job_id, text="post body")
    await _insert_utterance(db_pool, job_id, text="reply body")

    purged = await _purge(db_pool)

    assert purged == 1
    row = await _read_job(db_pool, job_id)
    assert row is not None, "row must still exist (soft-delete keeps the row)"
    assert row["expired_at"] is not None
    assert row["sidebar_payload"] is None
    assert row["error_message"] is None
    assert row["headline_summary"] is None
    assert row["safety_recommendation"] is None
    assert row["last_stage"] is None
    assert await _count_utterances(db_pool, job_id) == 0


@pytest.mark.asyncio
async def test_fresh_done_job_untouched(db_pool: Any) -> None:
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/fresh-done",
        status="done",
        finished_delta=timedelta(days=1),
    )
    await _insert_utterance(db_pool, job_id, text="post body")

    purged = await _purge(db_pool)

    assert purged == 0
    row = await _read_job(db_pool, job_id)
    assert row is not None
    assert row["expired_at"] is None
    assert row["sidebar_payload"] is not None
    assert await _count_utterances(db_pool, job_id) == 1


@pytest.mark.asyncio
async def test_purge_is_idempotent(db_pool: Any) -> None:
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/idempotent",
        status="done",
        finished_delta=timedelta(days=10),
    )

    first = await _purge(db_pool)
    row_after_first = await _read_job(db_pool, job_id)
    assert row_after_first is not None
    expired_at_first = row_after_first["expired_at"]

    second = await _purge(db_pool)
    row_after_second = await _read_job(db_pool, job_id)
    assert row_after_second is not None

    assert first == 1
    assert second == 0
    assert row_after_second["expired_at"] == expired_at_first


@pytest.mark.asyncio
async def test_old_partial_job_soft_deleted(db_pool: Any) -> None:
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/partial",
        status="partial",
        finished_delta=timedelta(days=8),
    )

    purged = await _purge(db_pool)

    assert purged == 1
    row = await _read_job(db_pool, job_id)
    assert row is not None
    assert row["expired_at"] is not None
    assert row["sidebar_payload"] is None


@pytest.mark.asyncio
async def test_old_failed_job_soft_deleted(db_pool: Any) -> None:
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/failed",
        status="failed",
        finished_delta=timedelta(days=8),
    )

    purged = await _purge(db_pool)

    assert purged == 1
    row = await _read_job(db_pool, job_id)
    assert row is not None
    assert row["expired_at"] is not None
    assert row["error_message"] is None


# ---------------------------------------------------------------------------
# TASK-1540.01: protected flag exempts jobs (and matching analyses cache rows)
# from TTL reaping.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protected_job_survives_thirty_day_ttl(db_pool: Any) -> None:
    """A protected=true job aged 30 days must NOT be soft-deleted."""
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/protected-old",
        status="done",
        finished_delta=timedelta(days=30),
        protected=True,
    )

    purged = await _purge(db_pool)

    assert purged == 0
    row = await _read_job(db_pool, job_id)
    assert row is not None
    assert row["protected"] is True
    assert row["expired_at"] is None
    assert row["sidebar_payload"] is not None
    assert row["headline_summary"] is not None
    assert row["safety_recommendation"] is not None
    assert row["last_stage"] is not None


@pytest.mark.asyncio
async def test_analyses_row_survives_when_matching_job_is_protected(
    db_pool: Any,
) -> None:
    """An expired analyses row must survive when its url matches a protected job."""
    url = "https://example.com/protected-cache"
    await _insert_terminal_job(
        db_pool,
        url=url,
        status="done",
        finished_delta=timedelta(days=8),
        protected=True,
    )
    await _insert_analyses_row(
        db_pool,
        url=url,
        expires_delta=timedelta(days=1),
    )

    purged = await _purge(db_pool)

    assert purged == 0
    assert await _analyses_exists(db_pool, url=url) is True


@pytest.mark.asyncio
async def test_unprotected_analyses_row_still_purged(db_pool: Any) -> None:
    """Regression: an expired analyses row with no protected job is deleted."""
    url = "https://example.com/no-protector"
    await _insert_analyses_row(
        db_pool,
        url=url,
        expires_delta=timedelta(days=1),
    )

    await _purge(db_pool)

    assert await _analyses_exists(db_pool, url=url) is False


@pytest.mark.asyncio
async def test_unprotected_job_still_soft_deleted(db_pool: Any) -> None:
    """Regression: protected=false (default) still gets soft-deleted normally."""
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/unprotected",
        status="done",
        finished_delta=timedelta(days=8),
        protected=False,
    )

    purged = await _purge(db_pool)

    assert purged == 1
    row = await _read_job(db_pool, job_id)
    assert row is not None
    assert row["protected"] is False
    assert row["expired_at"] is not None
    assert row["sidebar_payload"] is None


@pytest.mark.asyncio
async def test_unprotecting_job_lets_next_purge_soft_delete(db_pool: Any) -> None:
    """Flip protected=true -> false; the next purge run soft-deletes the job."""
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/unprotect-flip",
        status="done",
        finished_delta=timedelta(days=8),
        protected=True,
    )

    first = await _purge(db_pool)
    assert first == 0
    row_one = await _read_job(db_pool, job_id)
    assert row_one is not None
    assert row_one["expired_at"] is None

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE vibecheck_jobs SET protected = false WHERE job_id = $1",
            job_id,
        )

    second = await _purge(db_pool)
    assert second == 1
    row_two = await _read_job(db_pool, job_id)
    assert row_two is not None
    assert row_two["protected"] is False
    assert row_two["expired_at"] is not None
    assert row_two["sidebar_payload"] is None


# ---------------------------------------------------------------------------
# TASK-1540.03: protected flag also exempts the vibecheck_pdf_archives row.
# Unlike URL-keyed regeneration caches, pdf_archives stores user-uploaded
# PDF HTML that cannot be re-fetched from the original URL.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_archive_survives_when_job_is_protected(db_pool: Any) -> None:
    """An expired pdf_archives row must survive when its job is protected."""
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/protected-pdf",
        status="done",
        finished_delta=timedelta(days=30),
        protected=True,
    )
    await _insert_pdf_archive(
        db_pool,
        job_id=job_id,
        expires_delta=timedelta(days=1),
    )

    purged = await _purge(db_pool)

    assert purged == 0
    assert await _pdf_archive_exists(db_pool, job_id=job_id) is True


@pytest.mark.asyncio
async def test_unprotected_pdf_archive_still_purged(db_pool: Any) -> None:
    """Regression: an expired pdf_archives row whose job is not protected is deleted."""
    job_id = await _insert_terminal_job(
        db_pool,
        url="https://example.com/unprotected-pdf",
        status="done",
        finished_delta=timedelta(days=1),
        protected=False,
    )
    await _insert_pdf_archive(
        db_pool,
        job_id=job_id,
        expires_delta=timedelta(days=1),
    )

    await _purge(db_pool)

    assert await _pdf_archive_exists(db_pool, job_id=job_id) is False
