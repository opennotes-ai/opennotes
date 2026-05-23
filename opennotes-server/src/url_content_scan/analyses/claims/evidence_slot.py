"""Slot runner to enrich deduped claims with external supporting facts."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.url_content_scan.analyses.claims.evidence import (
    ExternalEvidenceFetcher,
    build_supporting_facts_by_claim,
)
from src.url_content_scan.claims_schemas import ClaimCategory, ClaimsReport


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


def _empty_report() -> ClaimsReport:
    return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)


def _unique_items_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


async def run_claims_evidence(
    payload: Any,
    settings: Any,
    *,
    external_fetcher: ExternalEvidenceFetcher | None = None,
) -> dict[str, Any]:
    """Enrich deduped claims with external supporting facts.

    Args:
        payload: section slot data containing a ``claims_report`` key, or a
            raw ``ClaimsReport`` instance.
        settings: application settings forwarded to the evidence fetcher.
        external_fetcher: optional seam override for testing.
    """
    claims_report = _extract_claims_report(payload)
    if claims_report is None:
        return {"claims_report": _empty_report().model_dump(mode="json")}

    fetcher_kwargs: dict[str, Any] = {}
    if external_fetcher is not None:
        fetcher_kwargs["external_fetcher"] = external_fetcher
    supporting_facts_by_claim = await build_supporting_facts_by_claim(
        claims_report.deduped_claims, settings, **fetcher_kwargs
    )

    claims = []
    for claim in claims_report.deduped_claims:
        supporting_facts = supporting_facts_by_claim.get(claim.canonical_text, [])
        facts_to_verify = (
            len(_unique_items_in_order(claim.utterance_ids))
            if not supporting_facts and claim.category == ClaimCategory.POTENTIALLY_FACTUAL
            else 0
        )
        updated = claim.model_copy(
            update={
                "supporting_facts": supporting_facts,
                "facts_to_verify": facts_to_verify,
            }
        )
        claims.append(updated)

    return {
        "claims_report": claims_report.model_copy(update={"deduped_claims": claims}).model_dump(
            mode="json"
        )
    }


__all__ = ["run_claims_evidence"]
