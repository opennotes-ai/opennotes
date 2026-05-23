"""Detect recurring opinion trends and explicit oppositions from deduped claims."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.config import Settings, get_settings
from src.url_content_scan.claims_schemas import ClaimCategory, DedupedClaim
from src.url_content_scan.observability import url_scan_instrumentation
from src.url_content_scan.opinions_schemas import (
    ClaimOpposition,
    ClaimTrend,
    TrendsOppositionsReport,
    empty_trends_oppositions_report,
)

_INDEXABLE_CATEGORIES: set[ClaimCategory] = {
    ClaimCategory.SUBJECTIVE,
    ClaimCategory.SELF_CLAIMS,
}

_SYSTEM_PROMPT = (
    "You are a trends and opposition detector over opinion clusters. "
    "Use the indexed clusters below to infer recurring themes and explicit "
    "oppositions. Output compact items with reusable cluster indices only."
)


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


_TRENDS_AGENT: Agent[None, _TrendsOppositionsLLM] = Agent(
    name="url-content-scan-trends-oppositions",
    output_type=_TrendsOppositionsLLM,
    capabilities=[url_scan_instrumentation()],
)


AgentRunner = Callable[[Any, str], Awaitable[Any]]


async def _run_agent(agent: Any, user_prompt: str) -> Any:
    from src.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    return await agent.run(
        user_prompt,
        model=settings.DEFAULT_MINI_MODEL.to_pydantic_ai_model(),
        instructions=_SYSTEM_PROMPT,
        model_settings=ModelSettings(temperature=0.0),
    )


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
    lines.append("Return JSON-like object with keys `trends` and `oppositions`.")
    return "\n".join(lines)


def _resolve_indices(indices: list[int], clusters: list[DedupedClaim]) -> list[str]:
    texts = [cluster.canonical_text for cluster in clusters]
    seen: set[int] = set()
    resolved: list[str] = []
    for idx in indices:
        if idx in seen or not (0 <= idx < len(texts)):
            continue
        seen.add(idx)
        resolved.append(texts[idx])
    return resolved


async def run_trends_oppositions(
    clusters: list[DedupedClaim],
    *,
    settings: Settings | None = None,
    max_clusters: int | None = None,
) -> TrendsOppositionsReport:
    cfg = settings or get_settings()
    configured_max = (
        cfg.URL_SCAN_TRENDS_OPPOSITIONS_MAX_CLUSTERS if max_clusters is None else max_clusters
    )

    filtered = [c for c in clusters if c.category in _INDEXABLE_CATEGORIES]
    filtered.sort(key=lambda c: c.occurrence_count, reverse=True)

    capping_window = max(configured_max, 0)
    capped = filtered[:capping_window]

    if not capped:
        empty = empty_trends_oppositions_report()
        empty.skipped_for_cap = max(0, len(filtered) - len(capped))
        return empty

    prompt = _format_prompt(capped)
    result = await _run_agent(_TRENDS_AGENT, prompt)
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


__all__ = ["run_trends_oppositions"]
