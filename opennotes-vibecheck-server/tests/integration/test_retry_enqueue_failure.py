"""Revert-on-enqueue-failure guard regression test (TASK-1473.61).

_revert_slot_after_enqueue_failure must NOT clobber a slot whose job has
already been flipped to 'done' or 'failed' by a concurrent finalizer.

Two scenarios:

  1. Negative (guard fires): job status='done' when revert runs -> UPDATE
     matches zero rows -> slot stays as the new (post-retry-claim) attempt.

  2. Positive (revert fires): job status='analyzing' when revert runs ->
     UPDATE matches -> slot rolls back to prior_slot snapshot.

Both cases use a real Postgres via testcontainers to validate the SQL
predicate `AND status NOT IN ('done', 'failed')` in context.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from src.analyses.schemas import SectionSlug
from src.routes.analyze import _revert_slot_after_enqueue_failure

from .conftest import insert_pending_job, read_sections

_SLUG = SectionSlug.TONE_DYNAMICS_SCD


async def _seed_job_with_slot(
    pool: Any,
    *,
    status: str,
    slot_attempt_id: UUID,
    slot_state: str = "failed",
) -> UUID:
    """Insert a job with a seeded section slot, then set its status."""
    job_id, _ = await insert_pending_job(
        pool, url=f"https://example.com/revert-guard-{uuid4().hex[:8]}"
    )
    slot = {
        "state": slot_state,
        "attempt_id": str(slot_attempt_id),
        "data": None,
        "error": "upstream_error",
        "started_at": None,
        "finished_at": None,
    }
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE vibecheck_jobs
            SET sections = jsonb_build_object($2::text, $3::jsonb),
                status = $4
            WHERE job_id = $1
            """,
            job_id,
            _SLUG.value,
            json.dumps(slot),
            status,
        )
    return job_id


async def _read_slot(pool: Any, job_id: UUID) -> dict[str, Any]:
    sections = await read_sections(pool, job_id)
    return sections[_SLUG.value]


async def test_revert_blocked_when_job_is_done(db_pool: Any) -> None:
    """When job.status='done', the revert UPDATE matches zero rows.

    The slot must remain as the NEW (post-retry-claim) attempt, not roll
    back to the prior failed snapshot — a concurrent finalizer already
    committed the result.
    """
    prior_attempt = uuid4()
    new_attempt = uuid4()

    prior_slot: dict[str, Any] = {
        "state": "failed",
        "attempt_id": str(prior_attempt),
        "data": None,
        "error": "upstream_error",
        "started_at": None,
        "finished_at": None,
    }
    job_id = await _seed_job_with_slot(
        db_pool, status="done", slot_attempt_id=new_attempt, slot_state="running"
    )

    await _revert_slot_after_enqueue_failure(
        db_pool, job_id, _SLUG, new_attempt, prior_slot
    )

    slot_after = await _read_slot(db_pool, job_id)
    assert slot_after["attempt_id"] == str(new_attempt), (
        "Revert must NOT fire when job.status='done'; slot should keep new attempt"
    )
    assert slot_after["state"] == "running"


async def test_revert_fires_when_job_is_analyzing(db_pool: Any) -> None:
    """When job.status='analyzing', the revert UPDATE matches and reverts the slot.

    The happy-but-networking-hiccup case: Cloud Tasks creation was called but
    the client raised before the 200 was confirmed. The job is still in flight
    so reverting the slot is the correct action.
    """
    prior_attempt = uuid4()
    new_attempt = uuid4()

    prior_slot: dict[str, Any] = {
        "state": "failed",
        "attempt_id": str(prior_attempt),
        "data": None,
        "error": "upstream_error",
        "started_at": None,
        "finished_at": None,
    }

    job_id = await _seed_job_with_slot(
        db_pool, status="analyzing", slot_attempt_id=new_attempt, slot_state="running"
    )

    await _revert_slot_after_enqueue_failure(
        db_pool, job_id, _SLUG, new_attempt, prior_slot
    )

    slot_after = await _read_slot(db_pool, job_id)
    assert slot_after["attempt_id"] == str(prior_attempt), (
        "Revert must fire when job.status='analyzing'; slot should roll back to prior"
    )
    assert slot_after["state"] == "failed"
    assert slot_after["error"] == "upstream_error"
