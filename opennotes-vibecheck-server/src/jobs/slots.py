"""Section-slot write-contract helpers.

Every slot mutation in `vibecheck_jobs.sections` flows through this module so
that the `jsonb_build_object` merge pattern, compare-and-set guard on
`attempt_id`, and Pydantic -> JSON serialization live in one place.

All helpers accept a `db` object exposing `.acquire()` as an async context
manager returning an asyncpg connection-compatible object (i.e. an
`asyncpg.Pool`). Helpers return the number of rows affected (0 or 1) so the
caller can detect stale attempts and drop the redelivery.

`slot.data` is serialized via `SectionSlot.model_dump(mode='json')` which
converts UUIDs and datetimes to strings that Postgres accepts inside
`JSONB`.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from src.analyses.schemas import SectionSlot, SectionSlug, SectionState

# The single UPDATE shape all helpers share: CAS on the job-level attempt_id
# and merge-in the new slot JSON via jsonb_build_object.
_WRITE_SQL = """
UPDATE vibecheck_jobs
SET sections = sections || jsonb_build_object($3::text, $4::jsonb),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $2
"""

# claim_slot's extra guard: only transition from pending/failed (or missing).
_CLAIM_SQL = """
UPDATE vibecheck_jobs
SET sections = sections || jsonb_build_object($3::text, $4::jsonb),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $2
  AND (
    NOT (sections ? $3::text)
    OR sections -> $3::text ->> 'state' IN ('pending', 'failed')
  )
"""

# mark_slot_done/failed enforce the full slot write contract from spec
# §"Slot write contract":
#   1. job.attempt_id still equals the expected task_attempt (stale worker
#      after a retry rotation cannot mutate the fresh attempt's cache).
#   2. job.status is non-terminal (no writes after the job flipped to
#      done/failed — the sweeper or error path owns those rows).
#   3. the slot's recorded attempt_id matches (CAS on the slot-level
#      attempt so Cloud Tasks redeliveries of an earlier superseded slot
#      silently drop).
#   4. the slot is currently `running` (don't flip done→done or failed→
#      done on a redelivered terminal write).
_FINALIZE_SLOT_SQL = """
UPDATE vibecheck_jobs
SET sections = sections || jsonb_build_object($2::text, $3::jsonb),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $5
  AND status IN ('pending', 'extracting', 'analyzing')
  AND sections ? $2::text
  AND sections -> $2::text ->> 'attempt_id' = $4::text
  AND sections -> $2::text ->> 'state' = 'running'
"""


def _dump_slot(slot: SectionSlot) -> str:
    """Serialize a SectionSlot for JSONB. model_dump(mode='json') converts
    UUIDs and datetimes to strings so they round-trip cleanly."""
    return json.dumps(slot.model_dump(mode="json"))


def _rowcount(result: Any) -> int:
    """asyncpg's `execute` returns a status string like 'UPDATE 1'."""
    if isinstance(result, str) and result.startswith("UPDATE"):
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
    return 0


async def write_slot(
    db: Any,
    job_id: UUID,
    task_attempt: UUID,
    slug: SectionSlug,
    slot: SectionSlot,
) -> int:
    """CAS-guarded merge of `slot` into `sections[slug]`.

    The WHERE clause guards on `attempt_id = task_attempt` so redeliveries
    from a superseded job attempt are rejected. Returns the number of rows
    affected (0 = stale attempt / unknown job, 1 = written).
    """
    async with db.acquire() as conn:
        result = await conn.execute(
            _WRITE_SQL,
            job_id,
            task_attempt,
            slug.value,
            _dump_slot(slot),
        )
    return _rowcount(result)


async def claim_slot(
    db: Any,
    job_id: UUID,
    task_attempt: UUID,
    slug: SectionSlug,
) -> UUID | None:
    """Atomically flip `sections[slug]` from pending/failed -> running.

    The UPDATE runs under row-level locking, so concurrent claimers serialize
    and only the first observes the pending/failed predicate as true. Later
    claimers see `state='running'` and the WHERE clause rejects their update.

    Returns the newly minted slot `attempt_id` on success, or None if the
    slot is already running/done or the job's `attempt_id` doesn't match.
    """
    slot_attempt = uuid4()
    now = datetime.now(UTC)
    slot = SectionSlot(
        state=SectionState.RUNNING,
        attempt_id=slot_attempt,
        started_at=now,
    )
    async with db.acquire() as conn:
        result = await conn.execute(
            _CLAIM_SQL,
            job_id,
            task_attempt,
            slug.value,
            _dump_slot(slot),
        )
    return slot_attempt if _rowcount(result) == 1 else None


async def mark_slot_done(
    db: Any,
    job_id: UUID,
    slug: SectionSlug,
    slot_attempt: UUID,
    data: dict[str, Any],
    *,
    expected_task_attempt: UUID,
) -> int:
    """Mark a running slot as done iff the full CAS envelope holds.

    CAS guards (spec §"Slot write contract"):
      * `job.attempt_id == expected_task_attempt` — reject stale workers
        whose job attempt was rotated by a retry.
      * `job.status` is non-terminal — reject writes after the sweeper or
        error path flipped the job to done/failed.
      * `slot.attempt_id == slot_attempt` — reject Cloud Tasks redeliveries
        from an earlier superseded slot attempt.
      * `slot.state == 'running'` — reject a second terminal write that
        would clobber an earlier done/failed payload.

    Returns 1 on success, 0 if any guard fails. The caller should treat 0
    as a silent no-op (the slot is already in a consistent state owned by
    a different worker).
    """
    now = datetime.now(UTC)
    slot = SectionSlot(
        state=SectionState.DONE,
        attempt_id=slot_attempt,
        data=data,
        finished_at=now,
    )
    async with db.acquire() as conn:
        result = await conn.execute(
            _FINALIZE_SLOT_SQL,
            job_id,
            slug.value,
            _dump_slot(slot),
            str(slot_attempt),
            expected_task_attempt,
        )
    return _rowcount(result)


async def mark_slot_failed(
    db: Any,
    job_id: UUID,
    slug: SectionSlug,
    slot_attempt: UUID,
    error: str,
    *,
    expected_task_attempt: UUID,
) -> int:
    """Mark a running slot as failed iff the full CAS envelope holds.

    See `mark_slot_done` for the guard list — this function enforces the
    same envelope. A failed slot (written here) is eligible for reclaim
    via `claim_slot` because claim's predicate accepts pending|failed.
    """
    now = datetime.now(UTC)
    slot = SectionSlot(
        state=SectionState.FAILED,
        attempt_id=slot_attempt,
        error=error,
        finished_at=now,
    )
    async with db.acquire() as conn:
        result = await conn.execute(
            _FINALIZE_SLOT_SQL,
            job_id,
            slug.value,
            _dump_slot(slot),
            str(slot_attempt),
            expected_task_attempt,
        )
    return _rowcount(result)


__all__ = [
    "claim_slot",
    "mark_slot_done",
    "mark_slot_failed",
    "write_slot",
]
