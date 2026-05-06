"""Slot wrapper for opinion highlights analysis."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from src.analyses.claims._claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
from src.analyses.opinions._highlights_schemas import (
    HighlightsThresholdInfo,
    OpinionsHighlightsReport,
)
from src.analyses.opinions.highlights import compute_highlights
from src.analyses.opinions.trends_oppositions_slot import FIRST_RUN_DEPENDENCY_PAYLOAD
from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
from src.analyses.slot_utterances import load_job_utterances
from src.config import Settings

_LOAD_SECTIONS_SQL = """
SELECT sections
FROM vibecheck_jobs
WHERE job_id = $1
"""


def _empty_report() -> dict[str, Any]:
    report = OpinionsHighlightsReport(
        highlights=[],
        threshold=HighlightsThresholdInfo(
            total_authors=0,
            total_utterances=0,
            min_authors_required=2,
            min_occurrences_required=3,
        ),
        fallback_engaged=False,
        floor_eligible_count=0,
        total_input_count=0,
    )
    return {"highlights_report": report.model_dump(mode="json")}


def _coerce_sections(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return {}
    if not isinstance(payload, Mapping):
        return {}
    sections = payload.get("sections", payload)
    if not isinstance(sections, Mapping):
        return {}
    return dict(sections)


async def _load_sections_from_db(pool: Any, job_id: Any) -> dict[str, Any]:
    if not hasattr(pool, "acquire"):
        return {}
    async with pool.acquire() as conn:
        sections = await conn.fetchval(_LOAD_SECTIONS_SQL, job_id)
    return _coerce_sections(sections)


def _extract_section_payload(payload: Mapping[str, Any], slug: str) -> tuple[dict[str, Any], str]:
    raw = payload.get(slug)
    data: dict[str, Any] = {}
    state = "missing"
    if raw is None:
        return data, state
    if isinstance(raw, SectionSlot):
        if raw.state == SectionState.DONE:
            data = raw.data if isinstance(raw.data, dict) else {}
            return data, SectionState.DONE.value
        return data, raw.state.value
    if isinstance(raw, Mapping):
        if "state" not in raw or "attempt_id" not in raw:
            data = dict(raw)
            return data, SectionState.DONE.value
        try:
            slot = SectionSlot.model_validate(raw)
        except ValidationError:
            return data, "malformed"
        if slot.state == SectionState.DONE:
            data = slot.data if isinstance(slot.data, dict) else {}
            return data, slot.state.value
        return data, slot.state.value
    return data, "malformed"


def _extract_deduped_claims(payload: Mapping[str, Any]) -> list[DedupedClaim]:
    claims_report = payload.get("claims_report")
    if not isinstance(claims_report, Mapping):
        return []
    try:
        report = ClaimsReport.model_validate(claims_report)
    except ValidationError:
        return []
    return list(report.deduped_claims)


def _load_facts_slot_from_payload(payload: Any, slug: str) -> tuple[dict[str, Any], str]:
    return _extract_section_payload(_coerce_sections(payload), slug)


def _is_initial_run_mode(payload: Any) -> bool:
    return payload is FIRST_RUN_DEPENDENCY_PAYLOAD


async def run_highlights(
    pool: Any,
    job_id: Any,
    task_attempt: Any,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    del task_attempt
    is_initial_run_mode = _is_initial_run_mode(payload)
    if is_initial_run_mode:
        payload = {}

    facts_slot_payload, facts_slot_state = _load_facts_slot_from_payload(
        payload, SectionSlug.FACTS_CLAIMS_DEDUP.value
    )

    if (payload is None or is_initial_run_mode) and not facts_slot_payload:
        db_sections = await _load_sections_from_db(pool, job_id)
        facts_slot_payload, facts_slot_state = _load_facts_slot_from_payload(
            db_sections, SectionSlug.FACTS_CLAIMS_DEDUP.value
        )

    if facts_slot_state in {
        "missing",
        "malformed",
        "failed",
        SectionState.PENDING.value,
        SectionState.RUNNING.value,
    }:
        return _empty_report()
    if not facts_slot_payload:
        return _empty_report()

    deduped_claims = _extract_deduped_claims(facts_slot_payload)
    if not deduped_claims:
        return _empty_report()

    filtered = [
        claim
        for claim in deduped_claims
        if claim.category in {ClaimCategory.SUBJECTIVE, ClaimCategory.SELF_CLAIMS}
    ]
    if not filtered:
        return _empty_report()

    utterances = await load_job_utterances(pool, job_id)
    total_utterances = len(utterances)
    total_authors = len({utterance.author for utterance in utterances if utterance.author})
    report = compute_highlights(
        filtered,
        total_authors=total_authors,
        total_utterances=total_utterances,
        settings=settings,
    )
    return {"highlights_report": report.model_dump(mode="json")}


__all__ = ["run_highlights"]
