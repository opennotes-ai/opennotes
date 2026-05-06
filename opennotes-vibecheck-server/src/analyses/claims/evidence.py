"""Supporting-fact enrichment for deduped factual claims.

This module keeps the enrichment logic reusable for both slot execution and
downstream tests. Evidence is attached only for
`ClaimCategory.POTENTIALLY_FACTUAL` claims.

Inline evidence is derived from source utterance text where possible.
External evidence is currently seam-driven and budgeted; the default seam returns
no external facts so tests never hit a network call unless explicitly patched.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, ValidationError
from pydantic_ai.builtin_tools import WebSearchTool

from src.analyses.claims._claims_schemas import (
    ClaimCategory,
    DedupedClaim,
    SourceKind,
    SupportingFact,
)
from src.config import Settings
from src.services.gemini_agent import build_agent, run_vertex_agent_with_retry
from src.services.vertex_limiter import vertex_slot

logger = logging.getLogger(__name__)

ExternalEvidenceFetcher = Callable[
    [list[str], Settings], Awaitable[dict[str, list[dict[str, Any]]]]
]


class _ExternalEvidenceItem(BaseModel):
    canonical_text: str
    statement: str
    source_ref: str


class _ExternalEvidenceResponse(BaseModel):
    facts: list[_ExternalEvidenceItem] = Field(default_factory=list)


_EXTERNAL_EVIDENCE_PROMPT = (
    "Find concise externally verifiable supporting facts for factual claims.\n"
    "\n"
    "Rules:\n"
    "- Use web search grounding for any external fact.\n"
    "- Return at most two facts per claim.\n"
    "- Each fact must support the claim directly, not merely mention the topic.\n"
    "- source_ref must be the best grounded URL for the fact.\n"
    "- If you cannot find a grounded source, return no fact for that claim.\n"
    "- canonical_text must exactly match one claim from the input."
)


async def fetch_external_evidence_batch(
    claim_texts: list[str],
    settings: Settings,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch grounded external supporting facts for a bounded claim batch."""
    if not claim_texts:
        return {}

    agent = build_agent(
        settings,
        output_type=_ExternalEvidenceResponse,
        system_prompt=_EXTERNAL_EVIDENCE_PROMPT,
        name="vibecheck.claims_evidence_external",
        tier="synthesis",
        builtin_tools=[WebSearchTool(search_context_size="low", max_uses=len(claim_texts))],
    )
    prompt = "Claims:\n" + "\n".join(f"- {claim_text}" for claim_text in claim_texts)
    async with vertex_slot(settings):
        result = await run_vertex_agent_with_retry(agent, prompt)
    response = result.output
    grounded_urls = _grounded_urls_from_result(result)
    facts_by_claim: dict[str, list[dict[str, Any]]] = {claim_text: [] for claim_text in claim_texts}
    if not isinstance(response, _ExternalEvidenceResponse):
        return facts_by_claim
    allowed = set(claim_texts)
    for fact in response.facts:
        canonical_text = fact.canonical_text.strip()
        if canonical_text not in allowed:
            continue
        statement = fact.statement.strip()
        source_ref = fact.source_ref.strip()
        if not statement or not source_ref:
            continue
        if _normalize_url(source_ref) not in grounded_urls:
            logger.warning("external evidence source_ref not in grounded URLs; dropping fact")
            continue
        facts_by_claim[canonical_text].append(
            {
                "statement": statement,
                "source_kind": SourceKind.EXTERNAL.value,
                "source_ref": source_ref,
            }
        )
    return facts_by_claim


def _normalize_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except Exception:
        return value.strip()
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or parsed.path
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _grounded_urls_from_result(result: Any) -> set[str]:
    urls: set[str] = set()
    try:
        calls = result.response.builtin_tool_calls
    except Exception:
        return urls
    for _call, returned in calls:
        content = returned.content
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            uri = item.get("uri")
            if isinstance(uri, str) and uri.strip():
                urls.add(_normalize_url(uri))
    return urls


def _coerce_supporting_fact(value: dict[str, Any] | SupportingFact) -> SupportingFact | None:
    if isinstance(value, SupportingFact):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return SupportingFact.model_validate(value)
    except ValidationError as exc:
        logger.warning("invalid supporting-fact payload skipped: %s", exc)
        return None


def _unique_items_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _inline_supporting_facts(
    claim: DedupedClaim,
    utterance_text_by_id: dict[str, str],
) -> list[SupportingFact]:
    facts: list[SupportingFact] = []
    for utterance_id in _unique_items_in_order(claim.utterance_ids):
        statement = utterance_text_by_id.get(utterance_id)
        if not statement:
            continue
        facts.append(
            SupportingFact(
                statement=claim.canonical_text,
                source_kind=SourceKind.UTTERANCE,
                source_ref=utterance_id,
            )
        )
    return facts


def _dedupe_supporting_facts(facts: list[SupportingFact]) -> list[SupportingFact]:
    seen: set[tuple[str, str, str]] = set()
    out: list[SupportingFact] = []
    for fact in facts:
        key = (fact.statement, fact.source_kind, fact.source_ref)
        if key in seen:
            continue
        seen.add(key)
        out.append(fact)
    return out


async def build_supporting_facts_by_claim(
    claims: list[DedupedClaim],
    utterance_text_by_id: dict[str, str],
    settings: Settings,
    *,
    external_fetcher: ExternalEvidenceFetcher = fetch_external_evidence_batch,
) -> dict[str, list[SupportingFact]]:
    """Build supporting facts for eligible claims keyed by canonical claim text."""
    eligible_claims = [
        claim for claim in claims if claim.category == ClaimCategory.POTENTIALLY_FACTUAL
    ]
    if not eligible_claims:
        return {}

    claim_texts = _unique_items_in_order([c.canonical_text for c in eligible_claims])
    if not claim_texts:
        return {}

    facts_by_claim: dict[str, list[SupportingFact]] = {}
    for claim in eligible_claims:
        inline_facts = _inline_supporting_facts(claim, utterance_text_by_id)
        if inline_facts:
            facts_by_claim[claim.canonical_text] = inline_facts

    budgeted_texts = claim_texts[: settings.EVIDENCE_MAX_EXTERNAL_RETRIEVALS]
    if budgeted_texts:
        try:
            raw_external = await external_fetcher(budgeted_texts, settings)
        except Exception as exc:
            logger.warning(
                "external evidence batch lookup failed for %d claims: %s",
                len(budgeted_texts),
                exc,
            )
            raw_external = {}
    else:
        raw_external = {}

    for canonical_text in claim_texts:
        external_facts = [
            converted
            for raw in raw_external.get(canonical_text, []) if (converted := _coerce_supporting_fact(raw))
        ]
        if canonical_text in facts_by_claim:
            facts_by_claim[canonical_text].extend(external_facts)
        elif external_facts:
            facts_by_claim[canonical_text] = external_facts

    return {
        canonical_text: _dedupe_supporting_facts(facts)
        for canonical_text, facts in facts_by_claim.items()
    }


__all__ = ["build_supporting_facts_by_claim", "fetch_external_evidence_batch"]
