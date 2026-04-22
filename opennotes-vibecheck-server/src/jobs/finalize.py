"""Job finalization: assemble SidebarPayload once every slot is done.

`maybe_finalize_job` is safe to call after any slot write. It takes a job-
level advisory lock so concurrent invocations can't double-write the cache
and can't observe a half-merged slot snapshot. If every slot is `done`, it
assembles a `SidebarPayload` from the slot fragments and UPSERTs into
`vibecheck_analyses` (the legacy 72h cache).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._schemas import OpinionsReport
from src.analyses.safety._schemas import HarmfulContentMatch
from src.analyses.schemas import (
    FactsClaimsSection,
    OpinionsSection,
    PageKind,
    SafetySection,
    SectionSlot,
    SectionSlug,
    SectionState,
    SidebarPayload,
    ToneDynamicsSection,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport

_CACHE_TTL = timedelta(hours=72)

_LOAD_SQL = """
SELECT url, sections, sidebar_payload IS NOT NULL AS already_finalized
FROM vibecheck_jobs
WHERE job_id = $1
"""

_UPSERT_CACHE_SQL = """
INSERT INTO vibecheck_analyses (url, sidebar_payload, expires_at)
VALUES ($1, $2::jsonb, $3)
ON CONFLICT (url) DO UPDATE
SET sidebar_payload = EXCLUDED.sidebar_payload,
    expires_at = EXCLUDED.expires_at
"""


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
    safety = SafetySection(
        harmful_content_matches=[
            HarmfulContentMatch.model_validate(m)
            for m in safety_data.get("harmful_content_matches", [])
        ]
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
        tone_dynamics=tone,
        facts_claims=facts,
        opinions_sentiments=opinions,
    )


async def maybe_finalize_job(db: Any, job_id: UUID) -> bool:
    """Finalize the job if every slot is done, under an advisory lock.

    Returns True iff a SidebarPayload was assembled and upserted into
    `vibecheck_analyses` (also True on an idempotent re-finalize where the
    cache row already existed). False when any slot is still pending/
    running/failed.

    The lock is keyed on `hashtext(job_id::text)` and held for the duration
    of the transaction so two concurrent finalizers serialize rather than
    both writing the cache (and potentially racing on sub-schema assembly).
    """
    async with db.acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1::text))",
            str(job_id),
        )
        row = await conn.fetchrow(_LOAD_SQL, job_id)
        if row is None:
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
            row["url"],
            payload_json,
            expires_at,
        )
        return True


__all__ = ["maybe_finalize_job"]
