"""Detect recurring opinion trends and explicit oppositions from deduped claims."""
from __future__ import annotations

from pydantic import BaseModel

from src.analyses.claims._claims_schemas import ClaimCategory, DedupedClaim
from src.analyses.opinions._trends_schemas import (
    ClaimOpposition,
    ClaimTrend,
    TrendsOppositionsReport,
    empty_trends_oppositions_report,
)
from src.config import Settings, get_settings
from src.services.gemini_agent import build_agent, run_vertex_agent_with_retry
from src.services.vertex_limiter import vertex_slot


class _TrendLLM(BaseModel):
    label: str
    cluster_indices: list[int]
    summary: str


class _OppositionLLM(BaseModel):
    topic: str
    supporting_cluster_indices: list[int]
    opposing_cluster_indices: list[int]
    note: str | None = None


class _TrendsOppositionsLLM(BaseModel):
    trends: list[_TrendLLM]
    oppositions: list[_OppositionLLM]


_SYSTEM_PROMPT = (
    "You are a trends and opposition detector over opinion clusters. "
    "Use the indexed clusters below to infer recurring themes and explicit "
    "oppositions. Output compact items with reusable cluster indices only."
)

_INDEXABLE_CATEGORIES: set[ClaimCategory] = {
    ClaimCategory.SUBJECTIVE,
    ClaimCategory.SELF_CLAIMS,
}


def _format_prompt(clusters: list[DedupedClaim]) -> str:
    lines = [
        "Analyze the opinion clusters and return trends and explicit opposition pairs.",
        "",
    ]
    for i, cluster in enumerate(clusters):
        lines.append(
            f"[{i}] (occ={cluster.occurrence_count}, authors={cluster.author_count}, "
            f"category={cluster.category}) {cluster.canonical_text}"
        )
    lines.append("")
    lines.append(
        "Return JSON-like object with keys `trends` and `oppositions`."
    )
    return "\n".join(lines)


def _resolve_indices(
    indices: list[int], clusters: list[DedupedClaim]
) -> list[str]:
    texts = [cluster.canonical_text for cluster in clusters]
    seen: set[int] = set()
    resolved: list[str] = []
    for idx in indices:
        if idx in seen or not (0 <= idx < len(texts)):
            continue
        seen.add(idx)
        resolved.append(texts[idx])
    return resolved


async def extract_trends_oppositions(
    clusters: list[DedupedClaim],
    *,
    settings: Settings | None = None,
    max_clusters: int | None = None,
) -> TrendsOppositionsReport:
    """Build opinion trends/oppositions from deduped claim clusters."""
    settings = settings or get_settings()
    configured_max_clusters = (
        settings.VIBECHECK_TRENDS_OPPOSITIONS_MAX_CLUSTERS
        if max_clusters is None
        else max_clusters
    )
    filtered = [
        cluster
        for cluster in clusters
        if cluster.category in _INDEXABLE_CATEGORIES
    ]
    filtered.sort(key=lambda c: c.occurrence_count, reverse=True)

    capping_window = max(configured_max_clusters, 0)
    capped = filtered[:capping_window]

    if not capped:
        empty = empty_trends_oppositions_report()
        empty.skipped_for_cap = max(0, len(filtered) - len(capped))
        return empty

    prompt = _format_prompt(capped)
    agent = build_agent(
        settings,
        output_type=_TrendsOppositionsLLM,
        system_prompt=_SYSTEM_PROMPT,
        name="vibecheck.trends_oppositions",
    )
    async with vertex_slot(settings):
        result = await run_vertex_agent_with_retry(agent, prompt)

    parsed: _TrendsOppositionsLLM = result.output

    return TrendsOppositionsReport(
        trends=[
            ClaimTrend(
                label=trend.label,
                cluster_texts=_resolve_indices(trend.cluster_indices, capped),
                summary=trend.summary,
            )
            for trend in parsed.trends
        ],
        oppositions=[
            ClaimOpposition(
                topic=opposition.topic,
                supporting_cluster_texts=_resolve_indices(
                    opposition.supporting_cluster_indices, capped
                ),
                opposing_cluster_texts=_resolve_indices(
                    opposition.opposing_cluster_indices, capped
                ),
                note=opposition.note,
            )
            for opposition in parsed.oppositions
        ],
        input_cluster_count=len(capped),
        skipped_for_cap=len(filtered) - len(capped),
    )


__all__ = ["extract_trends_oppositions"]
