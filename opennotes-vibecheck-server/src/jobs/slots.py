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

# mark_slot_done/failed guard against stale slot attempt_ids (Cloud Tasks
# redelivery of a retried slot). The predicate also forces the slot to exist.
_FINALIZE_SLOT_SQL = """
UPDATE vibecheck_jobs
SET sections = sections || jsonb_build_object($2::text, $3::jsonb),
    updated_at = now()
WHERE job_id = $1
  AND sections ? $2::text
  AND sections -> $2::text ->> 'attempt_id' = $4::text
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
) -> int:
    """Mark a running slot as done iff its `attempt_id` matches `slot_attempt`.

    Returns 1 on success, 0 if the slot was re-claimed (stale attempt) or is
    missing entirely. Cloud Tasks redeliveries from an earlier, already-
    superseded slot attempt are silently dropped by the CAS.
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
        )
    return _rowcount(result)


async def mark_slot_failed(
    db: Any,
    job_id: UUID,
    slug: SectionSlug,
    slot_attempt: UUID,
    error: str,
) -> int:
    """Mark a running slot as failed iff its `attempt_id` matches `slot_attempt`.

    Returns 1 on success, 0 on stale attempt. A failed slot is eligible for
    reclaim via `claim_slot` (which permits pending|failed -> running).
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
        )
    return _rowcount(result)


__all__ = [
    "claim_slot",
    "mark_slot_done",
    "mark_slot_failed",
    "write_slot",
]
