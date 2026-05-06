"""Slot worker to enrich deduped claims with supporting facts."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims.evidence import build_supporting_facts_by_claim
from src.analyses.slot_utterances import load_job_utterances
from src.config import Settings


def _extract_claims_report(raw: Any) -> ClaimsReport | None:
    """Extract a `ClaimsReport` from payload-like inputs."""
    if isinstance(raw, ClaimsReport):
        return raw
    if raw is None:
        return None
    if isinstance(raw, dict) and "claims_report" in raw:
        raw = raw["claims_report"]
    if isinstance(raw, ClaimsReport):
        return raw
    if isinstance(raw, dict):
        try:
            return ClaimsReport.model_validate(raw)
        except ValidationError:
            return None
    return None


def _extract_payload_claims_report(payload: Any) -> ClaimsReport | None:
    if payload is None:
        return None
    if hasattr(payload, "claims_report"):
        return _extract_claims_report(payload.claims_report)
    if isinstance(payload, dict) and "claims_report" in payload:
        return _extract_claims_report(payload["claims_report"])
    return None


async def _load_deduped_report(
    pool: Any,
    job_id: UUID,
) -> ClaimsReport | None:
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT sections -> $2 AS data FROM vibecheck_jobs WHERE job_id = $1",
            job_id,
            "facts_claims__dedup",
        )
    if row is None:
        return None
    if isinstance(row, str):
        row = _coerce_json(row)
    if not isinstance(row, dict):
        return None
    raw_data = row.get("data")
    if raw_data is None and row.get("state") == "done" and row.get("claims_report"):
        # Defensive fallback for legacy slot payload shapes that store
        # ``claims_report`` directly at the slot root.
        raw_data = {"claims_report": row.get("claims_report")}
    if not isinstance(raw_data, dict):
        return None
    claims_data = raw_data.get("claims_report", raw_data)
    return _extract_claims_report(claims_data) if isinstance(claims_data, dict) else None


def _coerce_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def _empty_report() -> ClaimsReport:
    return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)


async def run_claims_evidence(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    del task_attempt

    claims_report = _extract_payload_claims_report(payload)
    if claims_report is None:
        claims_report = await _load_deduped_report(pool, job_id)
    if claims_report is None:
        return {"claims_report": _empty_report().model_dump(mode="json")}

    utterances = await load_job_utterances(pool, job_id)
    utterance_text_by_id = {
        str(utterance.utterance_id): utterance.text for utterance in utterances
    }
    supporting_facts_by_claim = await build_supporting_facts_by_claim(
        claims_report.deduped_claims, utterance_text_by_id, settings
    )

    claims = []
    for claim in claims_report.deduped_claims:
        updated = claim.model_copy(
            update={
                "supporting_facts": supporting_facts_by_claim.get(
                    claim.canonical_text, []
                )
            }
        )
        claims.append(updated)

    return {
        "claims_report": claims_report.model_copy(
            update={"deduped_claims": claims}
        ).model_dump(mode="json")
    }


__all__ = ["run_claims_evidence"]
