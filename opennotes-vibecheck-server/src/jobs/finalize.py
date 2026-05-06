"""Job finalization: assemble SidebarPayload once every slot is terminal.

`maybe_finalize_job` is safe to call after any slot write. It takes a
row-level `SELECT FOR UPDATE` lock on the `vibecheck_jobs` row so that
concurrent finalizers serialize and slot writers block until finalize
commits — the previous `pg_advisory_xact_lock` was not held by slot
writers and therefore could not prevent half-merged snapshots (codex W1
P1.4). If every slot is `done` or `failed`, finalize assembles a
`SidebarPayload` from successful slot fragments, fills failed sections with
neutral defaults, and UPSERTs into `vibecheck_analyses` (the legacy 72h
cache).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from src.analyses.schemas import (
    ErrorCode,
    JobStatus,
    PageKind,
    SectionSlot,
    SectionSlug,
    SectionState,
    UtteranceAnchor,
    UtteranceStreamType,
)
from src.jobs.preview_description import (
    DerivationContext,
    derive_preview_description,
)
from src.jobs.sidebar_payload import (
    assemble_sidebar_payload as _assemble_payload,
)
from src.jobs.sidebar_payload import (
    payload_for_url_cache as _payload_for_url_cache,
)

_CACHE_TTL = timedelta(hours=72)

# SELECT FOR UPDATE serializes concurrent finalizers on the job row and
# blocks slot writers that grab the same row-level lock for their UPDATE.
# We fetch `attempt_id` and `status` so the caller can verify neither has
# drifted from the worker's expected envelope before assembling + UPSERTing.
#
# `page_title_meta` and `first_utterance_text` feed DerivationContext for
# preview_description fallback branches (TASK-1485.02). The LATERAL joins
# stay non-locking; both subqueries return NULL for fresh jobs without
# extracted utterances and the derivation function tolerates that.
_LOAD_SQL = """
SELECT
    j.url,
    j.normalized_url,
    j.source_type,
    j.sections,
    j.attempt_id,
    j.status,
    j.safety_recommendation,
    j.headline_summary,
    j.sidebar_payload IS NOT NULL AS already_finalized,
    meta.page_title AS page_title_meta,
    meta.page_kind AS page_kind_meta,
    meta.utterance_stream_type AS utterance_stream_type_meta,
    first_utt.text AS first_utterance_text
FROM vibecheck_jobs j
LEFT JOIN LATERAL (
    SELECT u.page_title, u.page_kind, u.utterance_stream_type
    FROM vibecheck_job_utterances u
    WHERE u.job_id = j.job_id
    ORDER BY u.position
    LIMIT 1
) AS meta ON TRUE
LEFT JOIN LATERAL (
    SELECT u.text
    FROM vibecheck_job_utterances u
    WHERE u.job_id = j.job_id
    ORDER BY u.position
    LIMIT 1
) AS first_utt ON TRUE
WHERE j.job_id = $1
FOR UPDATE OF j
"""

_UPSERT_CACHE_SQL = """
INSERT INTO vibecheck_analyses (url, sidebar_payload, expires_at)
VALUES ($1, $2::jsonb, $3)
ON CONFLICT (url) DO UPDATE
SET sidebar_payload = EXCLUDED.sidebar_payload,
    expires_at = EXCLUDED.expires_at
"""

# After UPSERT into the legacy 72h cache, flip the job row itself to a
# terminal status. Without this transition the poll endpoint would surface the
# job as `analyzing` indefinitely even though every slot completed and
# `vibecheck_analyses` already carries the assembled SidebarPayload
# (TASK-1473.34). Guarded on attempt_id and the same non-terminal status
# set the rest of finalize trusts so a concurrent retry rotation cannot
# clobber a job we no longer own.
_MARK_JOB_TERMINAL_SQL = """
UPDATE vibecheck_jobs
SET status = $2::text,
    sidebar_payload = $3::jsonb,
    error_code = $4,
    error_message = $5,
    error_host = NULL,
    preview_description = $7::text,
    finished_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $6
  AND status IN ('pending', 'extracting', 'analyzing')
"""

_LOAD_UTTERANCE_ANCHORS_SQL = """
SELECT position + 1 AS position, utterance_id
FROM vibecheck_job_utterances
WHERE job_id = $1 AND utterance_id IS NOT NULL
ORDER BY position
"""

_NON_TERMINAL_STATUSES = frozenset({"pending", "extracting", "analyzing"})
_TERMINAL_SLOT_STATES = frozenset({SectionState.DONE, SectionState.FAILED})
_FINALIZED_STATUSES = frozenset({JobStatus.DONE.value, JobStatus.PARTIAL.value})


def _load_sections(raw: Any) -> dict[SectionSlug, SectionSlot]:
    """Parse the `sections` JSONB column into typed SectionSlot values.

    asyncpg may hand us either a JSON string or a pre-decoded dict depending
    on how jsonb codec is configured, so we handle both shapes.
    """
    if raw is None:
        return {}
    as_dict: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else dict(raw)
    out: dict[SectionSlug, SectionSlot] = {}
    for slug in SectionSlug:
        entry = as_dict.get(slug.value)
        if entry is None:
            continue
        out[slug] = SectionSlot.model_validate(entry)
    return out


async def maybe_finalize_job(  # noqa: PLR0911
    db: Any,
    job_id: UUID,
    *,
    expected_task_attempt: UUID,
) -> bool:
    """Finalize the job if every slot is terminal, serialized with slot writers.

    Returns True iff a SidebarPayload was assembled and upserted into
    `vibecheck_analyses` (also True on an idempotent re-finalize where the
    cache row already existed). Returns False when any slot is still
    pending/running, when the job's `attempt_id` no longer matches the
    caller's expected envelope, or when the job has already flipped to an
    unhandled terminal status.

    **Locking strategy (spec §"Finalize lock consistency", codex P1.4).**
    The load is `SELECT ... FOR UPDATE`, which takes a row-level lock on
    the `vibecheck_jobs` row for the duration of the transaction. Concurrent
    finalizers serialize on that lock; slot writers that UPDATE the same
    row are blocked until finalize commits, so finalize never observes a
    half-merged slot snapshot. This supersedes the previous
    `pg_advisory_xact_lock(hashtext(job_id))` which was not held by
    `slots.py` writers and therefore could not serialize them.

    Strategy B was chosen over forcing each slot writer to grab the lock
    too (Strategy A) because Strategy B scales better: per-section retries
    on *unrelated* slots do not contend, and the finalize read-then-UPSERT
    is the only long-held critical section.

    `expected_task_attempt` is **required** (codex W3 P1-5) — the previous
    optional-with-None default silently skipped the CAS guard when callers
    forgot to pass it, defeating the slot-write contract. If a retry
    rotated the job's `attempt_id` after this worker launched the
    finalizer, the stale finalize aborts without touching the cache.
    A job whose status moved to `failed` returns False — the error path or
    sweeper owns those rows. A job that is already `done` or `partial`
    (because finalize already ran successfully) is treated as an idempotent
    re-finalize and returns True without re-touching either the cache or the
    job row (TASK-1473.34).
    """
    async with db.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(_LOAD_SQL, job_id)
        if row is None:
            return False

        if row["attempt_id"] != expected_task_attempt:
            return False
        if row["status"] in _FINALIZED_STATUSES and row["already_finalized"]:
            return True
        if row["status"] not in _NON_TERMINAL_STATUSES:
            return False

        sections = _load_sections(row["sections"])
        if len(sections) < len(SectionSlug):
            return False
        if any(s.state not in _TERMINAL_SLOT_STATES for s in sections.values()):
            return False

        failed_slugs = [
            slug for slug in SectionSlug if sections[slug].state == SectionState.FAILED
        ]
        next_status = JobStatus.PARTIAL if failed_slugs else JobStatus.DONE
        error_code = ErrorCode.SECTION_FAILURE.value if failed_slugs else None
        error_message = (
            "Sections failed: " + ", ".join(slug.value for slug in failed_slugs)
            if failed_slugs
            else None
        )

        utterance_anchors = [
            UtteranceAnchor(position=row["position"], utterance_id=row["utterance_id"])
            for row in await conn.fetch(_LOAD_UTTERANCE_ANCHORS_SQL, job_id)
        ]

        payload = _assemble_payload(
            row["url"],
            sections,
            row["safety_recommendation"],
            row["headline_summary"],
            utterance_anchors,
            page_title=row["page_title_meta"],
            page_kind=PageKind(row["page_kind_meta"]) if row["page_kind_meta"] else PageKind.OTHER,
            utterance_stream_type=(
                UtteranceStreamType(row["utterance_stream_type_meta"])
                if row["utterance_stream_type_meta"]
                else UtteranceStreamType.UNKNOWN
            ),
        )
        ctx = DerivationContext(
            page_title=row["page_title_meta"],
            first_utterance_text=row["first_utterance_text"],
        )
        preview_description = derive_preview_description(payload, ctx)
        payload_json = json.dumps(payload.model_dump(mode="json"))
        cache_payload_json = _payload_for_url_cache(payload)
        expires_at = datetime.now(UTC) + _CACHE_TTL
        if row["source_type"] != "browser_html":
            await conn.execute(
                _UPSERT_CACHE_SQL,
                row["normalized_url"],
                cache_payload_json,
                expires_at,
            )
        await conn.execute(
            _MARK_JOB_TERMINAL_SQL,
            job_id,
            next_status.value,
            payload_json,
            error_code,
            error_message,
            expected_task_attempt,
            preview_description,
        )
        return True


__all__ = ["maybe_finalize_job"]
