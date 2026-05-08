"""Slot worker to infer assumptions (premises) for deduped claims."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from src.analyses.claims._claims_schemas import ClaimsReport, DedupedClaim
from src.analyses.claims.premises import PremiseSeam, build_premises_by_claim
from src.config import Settings


def _extract_claims_report(raw: Any) -> ClaimsReport | None:
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
        try:
            row = json.loads(row)
        except Exception:
            return None
    if not isinstance(row, dict):
        return None
    raw_data = row.get("data")
    if (
        raw_data is None
        and row.get("state") == "done"
        and row.get("claims_report") is not None
    ):
        # Backward-safe fallback when older slot rows store the payload at the
        # root instead of under ``data``.
        raw_data = {"claims_report": row.get("claims_report")}
    if not isinstance(raw_data, dict):
        return None
    return _extract_claims_report(raw_data.get("claims_report", raw_data))


def _empty_report() -> ClaimsReport:
    return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)


async def run_claims_premises(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
    *,
    premise_extractor: PremiseSeam | None = None,
) -> dict[str, Any]:
    del task_attempt

    claims_report = _extract_payload_claims_report(payload)
    if claims_report is None:
        claims_report = await _load_deduped_report(pool, job_id)
    if claims_report is None:
        return {"claims_report": _empty_report().model_dump(mode="json")}

    extractor_kwargs: dict[str, Any] = {}
    if premise_extractor is not None:
        extractor_kwargs["premise_extractor"] = premise_extractor
    premises, premise_ids_by_claim = await build_premises_by_claim(
        claims_report.deduped_claims, settings, **extractor_kwargs
    )

    updated_claims: list[DedupedClaim] = []
    for claim in claims_report.deduped_claims:
        premise_ids = premise_ids_by_claim.get(claim.canonical_text, claim.premise_ids)
        updated = claim.model_copy(update={"premise_ids": list(premise_ids)})
        updated_claims.append(updated)

    return {
        "claims_report": claims_report.model_copy(
            update={
                "deduped_claims": updated_claims,
                "premises": premises if premises.premises else None,
            }
        ).model_dump(mode="json")
    }


__all__ = ["run_claims_premises"]
