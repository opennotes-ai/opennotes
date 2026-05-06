"""Slot wrapper for opinion trends/oppositions analysis."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from src.analyses.claims._claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
from src.analyses.opinions._trends_schemas import TrendsOppositionsReport
from src.analyses.opinions.trends_oppositions import extract_trends_oppositions
from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
from src.config import Settings


def _empty_report() -> dict[str, Any]:
    report = TrendsOppositionsReport(
        trends=[],
        oppositions=[],
        input_cluster_count=0,
        skipped_for_cap=0,
    )
    return {"trends_oppositions_report": report.model_dump(mode="json")}


def _coerce_sections(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    if "sections" not in payload:
        return dict(payload)
    sections = payload["sections"]
    if not isinstance(sections, Mapping):
        return {}
    return dict(sections)


def _extract_section_payload(payload: Mapping[str, Any], slug: str) -> dict[str, Any]:
    raw = payload.get(slug)
    data: dict[str, Any] = {}
    if raw is None:
        return data

    if isinstance(raw, SectionSlot):
        if raw.state == SectionState.DONE and isinstance(raw.data, dict):
            data = raw.data
        return data

    if isinstance(raw, Mapping):
        if "state" not in raw or "attempt_id" not in raw:
            return dict(raw)
        try:
            slot = SectionSlot.model_validate(raw)
        except ValidationError:
            return data
        if slot.state == SectionState.DONE and isinstance(slot.data, dict):
            data = slot.data

    return data


def _extract_deduped_claims(payload: Mapping[str, Any]) -> list[DedupedClaim]:
    claims_report = payload.get("claims_report")
    if not isinstance(claims_report, Mapping):
        return []
    try:
        report = ClaimsReport.model_validate(claims_report)
    except ValidationError:
        return []
    return list(report.deduped_claims)


def _load_facts_slot_from_payload(
    payload: Any,
    slug: str,
) -> dict[str, Any]:
    return _extract_section_payload(_coerce_sections(payload), slug)


async def run_trends_oppositions(
    pool: Any,
    job_id: Any,
    task_attempt: Any,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    del pool, job_id, task_attempt

    facts_slot_payload = _load_facts_slot_from_payload(
        payload, SectionSlug.FACTS_CLAIMS_DEDUP.value
    )
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

    report = await extract_trends_oppositions(filtered, settings=settings)
    return {"trends_oppositions_report": report.model_dump(mode="json")}


__all__ = ["run_trends_oppositions"]
