"""Slot wrapper for opinion trends/oppositions analysis."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from src.analyses.claims._claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
from src.analyses.opinions._trends_schemas import TrendsOppositionsReport
from src.analyses.opinions.trends_oppositions import extract_trends_oppositions
from src.analyses.schemas import SectionSlot, SectionSlug, SectionState
from src.config import Settings

_LOAD_SECTIONS_SQL = """
SELECT sections
FROM vibecheck_jobs
WHERE job_id = $1
"""


class TrendsDependenciesNotReadyError(RuntimeError):
    """Dependency data is present but not in a DONE state and cannot be used."""


def _empty_report() -> dict[str, Any]:
    report = TrendsOppositionsReport(
        trends=[],
        oppositions=[],
        input_cluster_count=0,
        skipped_for_cap=0,
    )
    return {"trends_oppositions_report": report.model_dump(mode="json")}


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


def _extract_section_payload(
    payload: Mapping[str, Any],
    slug: str,
) -> tuple[dict[str, Any], bool]:
    """Return `(payload, is_dependency_ready)` for a dependency section.

    `is_dependency_ready` is true when the dependency is present or DONE.
    Missing, failed, pending, and otherwise unavailable sections are treated as
    not ready; malformed data remains tolerated as an empty payload for DONE
    sections.
    """
    raw = payload.get(slug)
    data: dict[str, Any] = {}
    is_dependency_ready = False
    if raw is None:
        pass
    elif isinstance(raw, SectionSlot):
        if raw.state == SectionState.DONE:
            data = raw.data if isinstance(raw.data, dict) else {}
            is_dependency_ready = True
    elif isinstance(raw, Mapping):
        if "state" not in raw or "attempt_id" not in raw:
            data = dict(raw)
            is_dependency_ready = True
        else:
            try:
                slot = SectionSlot.model_validate(raw)
            except ValidationError:
                data = {}
                is_dependency_ready = True
            else:
                if slot.state == SectionState.DONE:
                    is_dependency_ready = True
                    data = slot.data if isinstance(slot.data, dict) else {}
                else:
                    is_dependency_ready = False
    else:
        pass

    return data, is_dependency_ready


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
) -> tuple[dict[str, Any], bool]:
    return _extract_section_payload(_coerce_sections(payload), slug)


async def run_trends_oppositions(
    pool: Any,
    job_id: Any,
    task_attempt: Any,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    is_retry = payload is None
    facts_slot_payload, facts_slot_ready = _load_facts_slot_from_payload(
        payload, SectionSlug.FACTS_CLAIMS_DEDUP.value
    )
    if not facts_slot_payload:
        if is_retry:
            db_sections = await _load_sections_from_db(pool, job_id)
            facts_slot_payload, facts_slot_ready = _load_facts_slot_from_payload(
                db_sections,
                SectionSlug.FACTS_CLAIMS_DEDUP.value,
            )
        else:
            return _empty_report()

    if is_retry and not facts_slot_ready:
        raise TrendsDependenciesNotReadyError(
            f"dependencies not ready for {SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS.value}"
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
