"""Supporting-fact enrichment for deduped factual claims.

This module keeps the enrichment logic reusable for both slot execution and
downstream tests. Evidence is attached only for
`ClaimCategory.POTENTIALLY_FACTUAL` claims.

Supporting facts are grounded external references only. The default seam returns
no external facts so tests never hit a network call unless explicitly patched.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import logfire
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai.native_tools import WebSearchTool

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

_INLINE_TAUTOLOGY_PADDING_WORDS = {
    "claim",
    "claims",
    "fact",
    "statement",
    "says",
    "said",
    "that",
    "this",
}

_MIN_TAUTOLOGY_CONTAINMENT_WORDS = 3

ExternalEvidenceFetcher = Callable[
    [list[str], Settings], Awaitable[dict[str, list[dict[str, Any]]]]
]


class _ExternalEvidenceItem(BaseModel):
    canonical_text: str
    statement: str
    source_ref: str


class _ExternalEvidenceResponse(BaseModel):
    facts: list[_ExternalEvidenceItem] = Field(default_factory=list)


class _ExternalEvidenceCandidate(BaseModel):
    canonical_text: str
    statement: str
    source_ref: str


class _ClaimGroup(BaseModel):
    claim_texts: list[str] = Field(default_factory=list)


class _ClusterResponse(BaseModel):
    groups: list[_ClaimGroup] = Field(default_factory=list)


class _SanityResponse(BaseModel):
    candidates: list[_ExternalEvidenceCandidate] = Field(default_factory=list)


class _CurateFact(BaseModel):
    canonical_text: str
    statement: str
    source_ref: str


class _CurateResponse(BaseModel):
    facts: list[_CurateFact] = Field(default_factory=list)


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


_CLUSTER_PROMPT = (
    "Group factual claims that likely share grounding sources.\n"
    "Claims in the same group should concern the same topic, entity, event, or source family.\n"
    "Return groups whose claim_texts collectively contain every input claim exactly once."
)

_SANITY_PROMPT = (
    "Review candidate externally grounded facts.\n"
    "Return only candidates whose statement directly supports canonical_text.\n"
    "Drop off-topic items and near-duplicates. Never invent new candidates."
)

_CURATE_PROMPT = (
    "Curate externally grounded supporting facts for factual claims.\n"
    "Choose concise facts that directly support each canonical_text.\n"
    "Return only facts from the candidate list. Never invent a source_ref."
)


def proportional_shrink(counts: list[int], total_cap: int) -> list[int]:
    """Shrink per-claim counts to a total cap while preserving non-zero entries."""
    if total_cap <= 0:
        return [0 for _count in counts]
    sanitized = [max(0, count) for count in counts]
    total = sum(sanitized)
    if total <= total_cap:
        return sanitized

    nonzero_indexes = [index for index, count in enumerate(sanitized) if count > 0]
    if total_cap <= len(nonzero_indexes):
        capped = [0 for _count in sanitized]
        for index in nonzero_indexes[:total_cap]:
            capped[index] = 1
        return capped

    allotments = [0 for _count in sanitized]
    for index in nonzero_indexes:
        allotments[index] = 1

    remaining_cap = total_cap - len(nonzero_indexes)
    remaining_counts = [max(0, sanitized[index] - 1) for index in range(len(sanitized))]
    remaining_total = sum(remaining_counts)
    if remaining_total <= 0:
        return allotments

    fractional: list[tuple[float, int]] = []
    allocated = 0
    for index, remaining_count in enumerate(remaining_counts):
        if remaining_count == 0:
            continue
        exact = remaining_count * remaining_cap / remaining_total
        whole = int(exact)
        allotments[index] += whole
        allocated += whole
        fractional.append((exact - whole, index))

    for _fraction, index in sorted(fractional, reverse=True)[: remaining_cap - allocated]:
        allotments[index] += 1

    return [
        min(original, allotment)
        for original, allotment in zip(sanitized, allotments, strict=True)
    ]


def _log_claims_eligible_per_job(claim_count: int) -> None:
    logfire.info("vibecheck.evidence.claims_eligible_per_job", claim_count=claim_count)


def _log_candidates_produced_per_job(candidate_count: int) -> None:
    logfire.info(
        "vibecheck.evidence.candidates_produced_per_job",
        candidate_count=candidate_count,
    )


def _log_candidates_per_claim(candidates_per_claim: dict[str, int]) -> None:
    logfire.info(
        "vibecheck.evidence.candidates_per_claim",
        candidates_per_claim=candidates_per_claim,
    )


def _log_synthesis_prompt_length(prompt_length: int) -> None:
    logfire.info(
        "vibecheck.evidence.synthesis_prompt_length",
        prompt_length=prompt_length,
    )


def _log_sanity_prompt_length(prompt_length: int) -> None:
    logfire.info(
        "vibecheck.evidence.sanity_prompt_length",
        prompt_length=prompt_length,
    )


def _log_grounded_fetch_failed(group_size: int, error_type: str) -> None:
    logfire.info(
        "vibecheck.evidence.grounded_fetch_failed",
        group_size=group_size,
        error_type=error_type,
    )


def _log_grounded_fetch_summary(groups_total: int, groups_failed: int) -> None:
    logfire.info(
        "vibecheck.evidence.grounded_fetch_summary",
        groups_total=groups_total,
        groups_failed=groups_failed,
    )


def _log_sanity_failed(error_type: str) -> None:
    logfire.info(
        "vibecheck.evidence.sanity_failed",
        error_type=error_type,
    )


def _log_curate_failed(error_type: str) -> None:
    logfire.info(
        "vibecheck.evidence.curate_failed",
        error_type=error_type,
    )


def _log_grounded_url_filter_drop(claim_text: str, source_ref: str, reason: str) -> None:
    logfire.info(
        "vibecheck.evidence.grounded_url_filter_drop",
        claim_text=claim_text,
        source_ref=source_ref,
        reason=reason,
    )


def _log_supporting_fact_filter_drop(claim_text: str, source_ref: str, reason: str) -> None:
    logfire.info(
        "vibecheck.evidence.supporting_fact_filter_drop",
        claim_text=claim_text,
        source_ref=source_ref,
        reason=reason,
    )


async def fetch_external_evidence_batch(
    claim_texts: list[str],
    settings: Settings,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch grounded external supporting facts through the two-tier pipeline."""
    if not claim_texts:
        return {}

    groups = await _cluster_claims_for_grounding(claim_texts, settings)
    raw_candidates = await _fetch_grounded_candidates_for_groups(groups, settings)
    _log_candidates_produced_per_job(len(raw_candidates))
    _log_candidates_per_claim(_candidate_counts_by_claim(raw_candidates))
    clean_candidates = await _dedupe_and_sanity_check_candidates(raw_candidates, settings)
    facts_by_claim = await _curate_supporting_facts_synthesis(clean_candidates, settings)
    return {
        claim_text: [fact.model_dump(mode="json") for fact in facts]
        for claim_text, facts in facts_by_claim.items()
    }


async def _cluster_claims_for_grounding(
    claim_texts: list[str], settings: Settings
) -> list[list[str]]:
    if not claim_texts:
        return []
    if len(claim_texts) == 1:
        return [[claim_texts[0]]]

    agent = build_agent(
        settings,
        output_type=_ClusterResponse,
        system_prompt=_CLUSTER_PROMPT,
        name="vibecheck.claims_evidence_cluster",
        tier="fast",
    )
    prompt = "Claims:\n" + "\n".join(f"- {claim_text}" for claim_text in claim_texts)
    try:
        async with vertex_slot(settings):
            result = await run_vertex_agent_with_retry(agent, prompt)
    except Exception as exc:
        logger.warning("external evidence claim clustering failed: %s", exc)
        return [list(claim_texts)]

    if not isinstance(result.output, _ClusterResponse) or not result.output.groups:
        return [list(claim_texts)]
    groups = [group.claim_texts for group in result.output.groups]
    return _repair_claim_groups(groups, claim_texts)


def _repair_claim_groups(groups: list[list[str]], claim_texts: list[str]) -> list[list[str]]:
    allowed = set(claim_texts)
    seen: set[str] = set()
    repaired: list[list[str]] = []
    for group in groups:
        cleaned: list[str] = []
        for claim_text in group:
            if claim_text not in allowed or claim_text in seen:
                continue
            seen.add(claim_text)
            cleaned.append(claim_text)
        if cleaned:
            repaired.append(cleaned)
    for claim_text in claim_texts:
        if claim_text not in seen:
            repaired.append([claim_text])
    return repaired


async def _fetch_grounded_candidates_for_groups(
    groups: list[list[str]], settings: Settings
) -> list[_ExternalEvidenceCandidate]:
    if not groups:
        return []

    grouped_calls = _chunk_groups(
        groups,
        max(1, settings.EVIDENCE_GROUNDED_FETCH_GROUPS_PER_CALL),
    )
    results = await asyncio.gather(
        *[_fetch_grounded_candidates_for_group(call_groups, settings) for call_groups in grouped_calls],
        return_exceptions=True,
    )

    candidates: list[_ExternalEvidenceCandidate] = []
    groups_failed = 0
    for call_groups, result in zip(grouped_calls, results, strict=True):
        if isinstance(result, BaseException):
            groups_failed += 1
            logger.warning("external evidence grounded fetch failed: %s", result)
            _log_grounded_fetch_failed(
                sum(len(group) for group in call_groups),
                type(result).__name__,
            )
            continue
        candidates.extend(result)
    _log_grounded_fetch_summary(len(grouped_calls), groups_failed)
    return candidates


def _chunk_groups(groups: list[list[str]], groups_per_call: int) -> list[list[list[str]]]:
    return [
        groups[index : index + groups_per_call]
        for index in range(0, len(groups), groups_per_call)
    ]


async def _fetch_grounded_candidates_for_group(
    groups: list[list[str]], settings: Settings
) -> list[_ExternalEvidenceCandidate]:
    claim_texts = [claim_text for group in groups for claim_text in group]
    agent = build_agent(
        settings,
        output_type=_ExternalEvidenceResponse,
        system_prompt=_EXTERNAL_EVIDENCE_PROMPT,
        name="vibecheck.claims_evidence_fetch",
        tier="fast",
        builtin_tools=[WebSearchTool(search_context_size="low", max_uses=len(claim_texts))],
    )
    prompt = "Claims:\n" + "\n".join(f"- {claim_text}" for claim_text in claim_texts)
    async with vertex_slot(settings):
        result = await run_vertex_agent_with_retry(agent, prompt)
    response = result.output
    grounded_urls = _grounded_urls_from_result(result)
    if not isinstance(response, _ExternalEvidenceResponse):
        return []
    allowed = set(claim_texts)
    candidates: list[_ExternalEvidenceCandidate] = []
    for fact in response.facts:
        canonical_text = fact.canonical_text.strip()
        if canonical_text not in allowed:
            continue
        statement = fact.statement.strip()
        source_ref = fact.source_ref.strip()
        if not statement or not source_ref:
            continue
        if _normalize_url(source_ref) not in grounded_urls:
            _log_grounded_url_filter_drop(
                canonical_text,
                source_ref,
                "not_in_grounded_metadata",
            )
            continue
        candidates.append(
            _ExternalEvidenceCandidate(
                canonical_text=canonical_text,
                statement=statement,
                source_ref=source_ref,
            )
        )
    return candidates


async def _dedupe_and_sanity_check_candidates(
    candidates: list[_ExternalEvidenceCandidate], settings: Settings
) -> list[_ExternalEvidenceCandidate]:
    unique_candidates = _dedupe_candidates(candidates)
    if len(unique_candidates) <= 1:
        return unique_candidates
    grouped = _capped_candidates_by_claim(
        unique_candidates, settings.EVIDENCE_SYNTHESIS_CANDIDATE_CAP
    )
    capped_candidates = [
        candidate for claim_candidates in grouped.values() for candidate in claim_candidates
    ]
    if not capped_candidates:
        return []

    agent = build_agent(
        settings,
        output_type=_SanityResponse,
        system_prompt=_SANITY_PROMPT,
        name="vibecheck.claims_evidence_sanity",
        tier="fast",
    )
    prompt = _format_candidate_prompt(capped_candidates)
    _log_sanity_prompt_length(len(prompt))
    try:
        async with vertex_slot(settings):
            result = await run_vertex_agent_with_retry(agent, prompt)
    except Exception as exc:
        logger.warning("external evidence sanity check failed: %s", exc)
        _log_sanity_failed(type(exc).__name__)
        return unique_candidates
    response = result.output
    if not isinstance(response, _SanityResponse):
        return unique_candidates

    allowed_keys = {_candidate_key(candidate) for candidate in capped_candidates}
    input_claim_texts = {candidate.canonical_text for candidate in capped_candidates}
    out: list[_ExternalEvidenceCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in response.candidates:
        normalized = _ExternalEvidenceCandidate(
            canonical_text=candidate.canonical_text.strip(),
            statement=candidate.statement.strip(),
            source_ref=candidate.source_ref.strip(),
        )
        key = _candidate_key(normalized)
        if (
            not normalized.statement
            or not normalized.source_ref
            or normalized.canonical_text not in input_claim_texts
            or key not in allowed_keys
            or key in seen
        ):
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _dedupe_candidates(
    candidates: list[_ExternalEvidenceCandidate],
) -> list[_ExternalEvidenceCandidate]:
    seen: set[tuple[str, str, str]] = set()
    out: list[_ExternalEvidenceCandidate] = []
    for candidate in candidates:
        normalized = _ExternalEvidenceCandidate(
            canonical_text=candidate.canonical_text.strip(),
            statement=candidate.statement.strip(),
            source_ref=candidate.source_ref.strip(),
        )
        if not normalized.canonical_text or not normalized.statement or not normalized.source_ref:
            continue
        key = _candidate_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _candidate_key(candidate: _ExternalEvidenceCandidate) -> tuple[str, str, str]:
    return (
        candidate.canonical_text,
        candidate.statement,
        _normalize_url(candidate.source_ref),
    )


async def _curate_supporting_facts_synthesis(
    candidates: list[_ExternalEvidenceCandidate], settings: Settings
) -> dict[str, list[SupportingFact]]:
    grouped = _capped_candidates_by_claim(candidates, settings.EVIDENCE_SYNTHESIS_CANDIDATE_CAP)
    if not grouped:
        return {}

    capped_candidates = [candidate for claim_candidates in grouped.values() for candidate in claim_candidates]
    prompt = _format_candidate_prompt(capped_candidates)
    _log_synthesis_prompt_length(len(prompt))
    agent = build_agent(
        settings,
        output_type=_CurateResponse,
        system_prompt=_CURATE_PROMPT,
        name="vibecheck.claims_evidence_curate",
        tier="synthesis",
    )
    try:
        async with vertex_slot(settings):
            result = await run_vertex_agent_with_retry(agent, prompt)
    except Exception as exc:
        logger.warning("external evidence curation failed: %s", exc)
        _log_curate_failed(type(exc).__name__)
        return {}
    response = result.output
    if not isinstance(response, _CurateResponse):
        return {}

    allowed_claims = set(grouped)
    allowed_keys = {_candidate_key(candidate) for candidate in capped_candidates}
    facts_by_claim: dict[str, list[SupportingFact]] = defaultdict(list)
    for fact in response.facts:
        canonical_text = fact.canonical_text.strip()
        statement = fact.statement.strip()
        source_ref = fact.source_ref.strip()
        candidate = _ExternalEvidenceCandidate(
            canonical_text=canonical_text,
            statement=statement,
            source_ref=source_ref,
        )
        if (
            canonical_text not in allowed_claims
            or not statement
            or not source_ref
            or _candidate_key(candidate) not in allowed_keys
        ):
            continue
        facts_by_claim[canonical_text].append(
            SupportingFact(
                statement=statement,
                source_kind=SourceKind.EXTERNAL,
                source_ref=source_ref,
            )
        )

    _log_final_facts_per_claim({claim: len(facts) for claim, facts in facts_by_claim.items()})
    return dict(facts_by_claim)


def _capped_candidates_by_claim(
    candidates: list[_ExternalEvidenceCandidate], cap: int
) -> dict[str, list[_ExternalEvidenceCandidate]]:
    grouped: dict[str, list[_ExternalEvidenceCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.canonical_text].append(candidate)
    if not grouped:
        return {}

    claim_texts = list(grouped)
    allotments = proportional_shrink([len(grouped[claim]) for claim in claim_texts], cap)
    return {
        claim_text: grouped[claim_text][:allotment]
        for claim_text, allotment in zip(claim_texts, allotments, strict=True)
        if allotment > 0
    }


def _format_candidate_prompt(candidates: list[_ExternalEvidenceCandidate]) -> str:
    lines: list[str] = ["Candidates:"]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"{index}. canonical_text: {candidate.canonical_text}",
                f"   statement: {candidate.statement}",
                f"   source_ref: {candidate.source_ref}",
            ]
        )
    return "\n".join(lines)


def _candidate_counts_by_claim(
    candidates: list[_ExternalEvidenceCandidate],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        counts[candidate.canonical_text] += 1
    return dict(counts)


def _log_final_facts_per_claim(facts_per_claim: dict[str, int]) -> None:
    logfire.info(
        "vibecheck.evidence.synthesis_curate",
        facts_per_claim=facts_per_claim,
    )


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


def _normalize_for_similarity(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(normalized.split())


def _matches_with_padding(normalized_statement: str, normalized_claim: str) -> bool:
    extra_text = ""
    if normalized_statement.startswith(f"{normalized_claim} "):
        extra_text = normalized_statement[len(normalized_claim) :].strip()
    elif normalized_statement.endswith(f" {normalized_claim}"):
        extra_text = normalized_statement[: -len(normalized_claim)].strip()
    else:
        return False
    extra_words = extra_text.split()
    return bool(extra_words) and all(
        word in _INLINE_TAUTOLOGY_PADDING_WORDS for word in extra_words
    )


def _is_inline_tautology(statement: str, claim_text: str) -> bool:
    normalized_statement = _normalize_for_similarity(statement)
    normalized_claim = _normalize_for_similarity(claim_text)
    if not normalized_statement or not normalized_claim:
        return False
    if normalized_statement == normalized_claim:
        return True
    if _matches_with_padding(normalized_statement, normalized_claim):
        return True
    if len(normalized_claim.split()) < _MIN_TAUTOLOGY_CONTAINMENT_WORDS:
        return False
    padded_claim = f" {normalized_claim} "
    padded_statement = f" {normalized_statement} "
    if padded_claim not in padded_statement:
        return False
    start = padded_statement.index(padded_claim)
    prefix = padded_statement[:start].strip()
    return bool(prefix)


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


def _keep_external_supporting_fact(fact: SupportingFact, canonical_text: str) -> bool:
    if fact.source_kind != SourceKind.EXTERNAL:
        _log_supporting_fact_filter_drop(
            canonical_text,
            fact.source_ref,
            "non_external_source_kind",
        )
        return False
    if _is_inline_tautology(fact.statement, canonical_text):
        _log_supporting_fact_filter_drop(
            canonical_text,
            fact.source_ref,
            "tautological_statement",
        )
        return False
    return True


async def build_supporting_facts_by_claim(
    claims: list[DedupedClaim],
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
    budgeted_texts = claim_texts[: settings.EVIDENCE_MAX_EXTERNAL_CLAIMS]
    _log_claims_eligible_per_job(len(budgeted_texts))
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
            for raw in raw_external.get(canonical_text, [])
            if (converted := _coerce_supporting_fact(raw))
            and _keep_external_supporting_fact(converted, canonical_text)
        ]
        if external_facts:
            facts_by_claim[canonical_text] = external_facts

    return {
        canonical_text: _dedupe_supporting_facts(facts)
        for canonical_text, facts in facts_by_claim.items()
    }


__all__ = [
    "build_supporting_facts_by_claim",
    "fetch_external_evidence_batch",
]
