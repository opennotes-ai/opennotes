"""Slot runner to infer assumptions (premises) for deduped claims."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.url_content_scan.analyses.claims.premises import PremiseSeam, build_premises_by_claim
from src.url_content_scan.claims_schemas import ClaimsReport, DedupedClaim


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


def _empty_report() -> ClaimsReport:
    return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)


async def run_claims_premises(
    payload: Any,
    settings: Any,
    *,
    premise_extractor: PremiseSeam | None = None,
) -> dict[str, Any]:
    """Enrich deduped claims with premise IDs.

    Args:
        payload: section slot data containing a ``claims_report`` key, or a
            raw ``ClaimsReport`` instance.
        settings: application settings forwarded to the premises extractor.
        premise_extractor: optional seam override for testing.
    """
    claims_report = _extract_claims_report(payload)
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
