"""Soft-delete purge integration tests (TASK-1541.01).

The production schema schedules `vibecheck_purge_terminal_jobs()` via
`pg_cron` once per hour. This test invokes the function directly to
assert that terminal jobs older than 7 days are soft-deleted via the
`expired_at` marker (with sensitive payload columns nulled and child
utterances hard-deleted), while fresh terminal jobs are untouched, and
that the operation is idempotent across repeated calls.

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
) -> UUID:
    finished_at = datetime.now(UTC) - finished_delta
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id,
                finished_at, sidebar_payload, sections, error_message,
                headline_summary, safety_recommendation, last_stage
            )
            VALUES (
                $1, $1, 'example.com', $2, $3,
                $4, $5::jsonb, $6::jsonb, $7, $8::jsonb, $9::jsonb, $10
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
        )
    assert isinstance(job_id, UUID)
    return job_id


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
                   last_stage
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
