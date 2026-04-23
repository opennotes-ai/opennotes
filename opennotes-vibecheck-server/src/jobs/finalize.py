"""Job finalization: assemble SidebarPayload once every slot is done.

`maybe_finalize_job` is safe to call after any slot write. It takes a
row-level `SELECT FOR UPDATE` lock on the `vibecheck_jobs` row so that
concurrent finalizers serialize and slot writers block until finalize
commits — the previous `pg_advisory_xact_lock` was not held by slot
writers and therefore could not prevent half-merged snapshots (codex W1
P1.4). If every slot is `done`, finalize assembles a `SidebarPayload`
from the slot fragments and UPSERTs into `vibecheck_analyses` (the
legacy 72h cache).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._schemas import OpinionsReport
from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.schemas import (
    FactsClaimsSection,
    ImageModerationSection,
    OpinionsSection,
    PageKind,
    SafetySection,
    SectionSlot,
    SectionSlug,
    SectionState,
    SidebarPayload,
    ToneDynamicsSection,
    VideoModerationSection,
    WebRiskSection,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport

_CACHE_TTL = timedelta(hours=72)

# SELECT FOR UPDATE serializes concurrent finalizers on the job row and
# blocks slot writers that grab the same row-level lock for their UPDATE.
# We fetch `attempt_id` and `status` so the caller can verify neither has
# drifted from the worker's expected envelope before assembling + UPSERTing.
_LOAD_SQL = """
SELECT url, normalized_url, sections, attempt_id, status,
       sidebar_payload IS NOT NULL AS already_finalized
FROM vibecheck_jobs
WHERE job_id = $1
FOR UPDATE
"""

_UPSERT_CACHE_SQL = """
INSERT INTO vibecheck_analyses (url, sidebar_payload, expires_at)
VALUES ($1, $2::jsonb, $3)
ON CONFLICT (url) DO UPDATE
SET sidebar_payload = EXCLUDED.sidebar_payload,
    expires_at = EXCLUDED.expires_at
"""

# After UPSERT into the legacy 72h cache, flip the job row itself to
# `done`. Without this transition the poll endpoint would surface the
# job as `analyzing` indefinitely even though every slot completed and
# `vibecheck_analyses` already carries the assembled SidebarPayload
# (TASK-1473.34). Guarded on attempt_id and the same non-terminal status
# set the rest of finalize trusts so a concurrent retry rotation cannot
# clobber a job we no longer own.
_MARK_JOB_DONE_SQL = """
UPDATE vibecheck_jobs
SET status = 'done',
    sidebar_payload = $2::jsonb,
    finished_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
  AND status IN ('pending', 'extracting', 'analyzing')
"""

_NON_TERMINAL_STATUSES = frozenset({"pending", "extracting", "analyzing"})


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


def _assemble_payload(
    url: str,
    sections: dict[SectionSlug, SectionSlot],
) -> SidebarPayload:
    """Compose SidebarPayload from slot fragments.

    Each slot stores the sub-fragment its destination section needs. The
    merge rules here are the only place we reconcile slot-level shapes with
    the section-level schemas that `SidebarPayload` requires.
    """
    safety_data = sections[SectionSlug.SAFETY_MODERATION].data or {}
    raw_matches = safety_data.get("harmful_content_matches", [])
    validated_matches: list[HarmfulContentMatch] = []
    for m in raw_matches:
        if isinstance(m, dict) and "source" not in m:
            m = {**m, "source": "openai"}
        validated_matches.append(HarmfulContentMatch.model_validate(m))
    safety = SafetySection(harmful_content_matches=validated_matches)

    # TASK-1474: three new safety sections carry their own shape into the
    # sidebar. Any slug not registered with a handler still returns the
    # default-empty stub (from _empty_section_data), which shapes validate.
    web_risk_data = sections.get(SectionSlug.SAFETY_WEB_RISK)
    web_risk_findings = (
        (web_risk_data.data or {}).get("findings", []) if web_risk_data else []
    )
    web_risk = WebRiskSection(
        findings=[WebRiskFinding.model_validate(f) for f in web_risk_findings]
    )

    image_mod_data = sections.get(SectionSlug.SAFETY_IMAGE_MODERATION)
    image_mod_matches = (
        (image_mod_data.data or {}).get("matches", []) if image_mod_data else []
    )
    image_moderation = ImageModerationSection(
        matches=[ImageModerationMatch.model_validate(m) for m in image_mod_matches]
    )

    video_mod_data = sections.get(SectionSlug.SAFETY_VIDEO_MODERATION)
    video_mod_matches = (
        (video_mod_data.data or {}).get("matches", []) if video_mod_data else []
    )
    video_moderation = VideoModerationSection(
        matches=[VideoModerationMatch.model_validate(m) for m in video_mod_matches]
    )

    flashpoint_data = sections[SectionSlug.TONE_DYNAMICS_FLASHPOINT].data or {}
    scd_data = sections[SectionSlug.TONE_DYNAMICS_SCD].data or {}
    tone = ToneDynamicsSection(
        scd=SCDReport.model_validate(scd_data["scd"]),
        flashpoint_matches=[
            FlashpointMatch.model_validate(m)
            for m in flashpoint_data.get("flashpoint_matches", [])
        ],
    )

    dedup_data = sections[SectionSlug.FACTS_CLAIMS_DEDUP].data or {}
    known_data = sections[SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO].data or {}
    facts = FactsClaimsSection(
        claims_report=ClaimsReport.model_validate(dedup_data["claims_report"]),
        known_misinformation=[
            FactCheckMatch.model_validate(m)
            for m in known_data.get("known_misinformation", [])
        ],
    )

    sentiment_data = sections[SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT].data or {}
    subjective_data = sections[SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE].data or {}
    opinions = OpinionsSection(
        opinions_report=OpinionsReport(
            sentiment_stats=sentiment_data["sentiment_stats"],
            subjective_claims=subjective_data.get("subjective_claims", []),
        )
    )

    return SidebarPayload(
        source_url=url,
        page_title=None,
        page_kind=PageKind.OTHER,
        scraped_at=datetime.now(UTC),
        cached=False,
        safety=safety,
        web_risk=web_risk,
        image_moderation=image_moderation,
        video_moderation=video_moderation,
        tone_dynamics=tone,
        facts_claims=facts,
        opinions_sentiments=opinions,
    )


async def maybe_finalize_job(
    db: Any,
    job_id: UUID,
    *,
    expected_task_attempt: UUID,
) -> bool:
    """Finalize the job if every slot is done, serialized with slot writers.

    Returns True iff a SidebarPayload was assembled and upserted into
    `vibecheck_analyses` (also True on an idempotent re-finalize where the
    cache row already existed). Returns False when any slot is still
    pending/running/failed, when the job's `attempt_id` no longer matches
    the caller's expected envelope, or when the job has already flipped
    to a terminal status.

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
    sweeper owns those rows. A job that is already `done` (because finalize
    already ran successfully) is treated as an idempotent re-finalize and
    returns True without re-touching either the cache or the job row
    (TASK-1473.34).
    """
    async with db.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(_LOAD_SQL, job_id)
        if row is None:
            return False

        if row["attempt_id"] != expected_task_attempt:
            return False
        if row["status"] == "done" and row["already_finalized"]:
            return True
        if row["status"] not in _NON_TERMINAL_STATUSES:
            return False

        sections = _load_sections(row["sections"])
        if len(sections) < len(SectionSlug):
            return False
        if any(s.state != SectionState.DONE for s in sections.values()):
            return False

        payload = _assemble_payload(row["url"], sections)
        payload_json = json.dumps(payload.model_dump(mode="json"))
        expires_at = datetime.now(UTC) + _CACHE_TTL
        await conn.execute(
            _UPSERT_CACHE_SQL,
            row["normalized_url"],
            payload_json,
            expires_at,
        )
        await conn.execute(
            _MARK_JOB_DONE_SQL,
            job_id,
            payload_json,
            expected_task_attempt,
        )
        return True


__all__ = ["maybe_finalize_job"]
