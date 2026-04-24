"""Orphan-sweeper SQL function integration test (TASK-1473.22 AC#3).

The production schema schedules `vibecheck_sweep_orphan_jobs()` via
`pg_cron` once per minute. This test invokes the function directly,
asserting:

  * Pending tier — a `pending` job older than 240s flips to
    `status='failed'` with `error_code='timeout'`.
  * Heartbeat tier — an `extracting`/`analyzing` job whose `heartbeat_at`
    is older than 30s flips to failed/timeout.
  * Fresh in-flight jobs are NOT swept.
  * Already-terminal jobs (done/failed) are NOT touched.

Times are simulated by directly UPDATEing `created_at`/`heartbeat_at`
backwards rather than literally sleeping, so the test stays fast.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4


async def _insert_job(
    pool: Any,
    *,
    url: str,
    status: str,
    created_at: datetime | None = None,
    heartbeat_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> UUID:
    async with pool.acquire() as conn:
        job_id = await conn.fetchval(
            """
            INSERT INTO vibecheck_jobs (
                url, normalized_url, host, status, attempt_id,
                created_at, updated_at, heartbeat_at, finished_at
            )
            VALUES (
                $1, $1, 'example.com', $2, $3,
                COALESCE($4, now()), COALESCE($4, now()), $5, $6
            )
            RETURNING job_id
            """,
            url,
            status,
            uuid4(),
            created_at,
            heartbeat_at,
            finished_at,
        )
    assert isinstance(job_id, UUID)
    return job_id


async def _read_status(pool: Any, job_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, error_code, error_message, finished_at "
            "FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
        )
    assert row is not None
    return dict(row)


async def _run_sweeper(pool: Any) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT vibecheck_sweep_orphan_jobs()")


async def test_sweeper_flips_old_pending_job_to_failed(
    db_pool: Any,
) -> None:
    """A pending job older than 240s must be flipped to failed/timeout."""
    stale = datetime.now(UTC) - timedelta(seconds=300)
    job_id = await _insert_job(
        db_pool,
        url="https://example.com/stale-pending",
        status="pending",
        created_at=stale,
    )

    swept = await _run_sweeper(db_pool)
    assert swept >= 1

    final = await _read_status(db_pool, job_id)
    assert final["status"] == "failed"
    assert final["error_code"] == "timeout"
    assert "pending" in (final["error_message"] or "")
    assert final["finished_at"] is not None


async def test_sweeper_flips_stale_heartbeat_job_to_failed(
    db_pool: Any,
) -> None:
    """An analyzing job with stale heartbeat must be flipped to failed/timeout."""
    now = datetime.now(UTC)
    stale_heartbeat = now - timedelta(seconds=120)
    fresh_creation = now - timedelta(seconds=180)
    job_id = await _insert_job(
        db_pool,
        url="https://example.com/stale-heartbeat",
        status="analyzing",
        created_at=fresh_creation,
        heartbeat_at=stale_heartbeat,
    )

    swept = await _run_sweeper(db_pool)
    assert swept >= 1

    final = await _read_status(db_pool, job_id)
    assert final["status"] == "failed"
    assert final["error_code"] == "timeout"
    assert "heartbeat" in (final["error_message"] or "")


async def test_sweeper_does_not_touch_fresh_pending_job(
    db_pool: Any,
) -> None:
    """A pending job younger than 240s must survive the sweep."""
    fresh = datetime.now(UTC) - timedelta(seconds=10)
    job_id = await _insert_job(
        db_pool,
        url="https://example.com/fresh-pending",
        status="pending",
        created_at=fresh,
    )

    await _run_sweeper(db_pool)

    final = await _read_status(db_pool, job_id)
    assert final["status"] == "pending"
    assert final["error_code"] is None


async def test_sweeper_does_not_touch_terminal_jobs(db_pool: Any) -> None:
    """Already-terminal jobs are never re-touched, regardless of age."""
    old = datetime.now(UTC) - timedelta(hours=2)
    done_id = await _insert_job(
        db_pool,
        url="https://example.com/done",
        status="done",
        created_at=old,
        finished_at=old,
    )
    failed_id = await _insert_job(
        db_pool,
        url="https://example.com/already-failed",
        status="failed",
        created_at=old,
        finished_at=old,
    )
    partial_id = await _insert_job(
        db_pool,
        url="https://example.com/partial",
        status="partial",
        created_at=old,
        finished_at=old,
    )

    await _run_sweeper(db_pool)

    done_final = await _read_status(db_pool, done_id)
    failed_final = await _read_status(db_pool, failed_id)
    partial_final = await _read_status(db_pool, partial_id)
    assert done_final["status"] == "done"
    assert failed_final["status"] == "failed"
    assert partial_final["status"] == "partial"


async def test_sweeper_with_no_orphans_returns_zero(db_pool: Any) -> None:
    """The sweeper must be idempotent on a clean table."""
    swept = await _run_sweeper(db_pool)
    assert swept == 0
