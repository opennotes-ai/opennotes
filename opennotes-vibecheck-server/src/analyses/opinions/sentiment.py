"""Sentiment statistics over a list of utterances.

POC uses the shared pydantic-ai Gemini agent. A sentence-level sentiment model
(VADER, transformer-based, etc.) could replace the LLM path later without
changing the public ``compute_sentiment_stats`` signature.
"""

from __future__ import annotations

import asyncio

from src.analyses.opinions._schemas import (
    SentimentScore,
    SentimentStatsReport,
    _SentimentBatchLLM,
)
from src.config import Settings, get_settings
from src.services.gemini_agent import build_agent, run_vertex_agent_with_retry
from src.services.vertex_limiter import vertex_slot
from src.utterances.schema import Utterance

_BATCH_SIZE = 10

_SYSTEM_PROMPT = (
    "You are a sentiment classifier. For each utterance, return a sentiment "
    "label ('positive', 'negative', or 'neutral') and a valence score in "
    "[-1.0, 1.0] where -1.0 is strongly negative, 0.0 is neutral, and 1.0 is "
    "strongly positive. Preserve the input utterance_id exactly. Return one "
    "score per utterance, in the same order."
)


def _utterance_id(utterance: Utterance, index: int) -> str:
    return utterance.utterance_id or f"utt-{index}"


def _format_batch(batch: list[tuple[str, Utterance]]) -> str:
    lines = ["Classify the sentiment of each utterance below.", ""]
    for uid, utt in batch:
        lines.append(f"- utterance_id={uid}: {utt.text}")
    return "\n".join(lines)


def _aggregate(scores: list[SentimentScore]) -> SentimentStatsReport:
    total = len(scores)
    if total == 0:
        return SentimentStatsReport(
            per_utterance=[],
            positive_pct=0.0,
            negative_pct=0.0,
            neutral_pct=0.0,
            mean_valence=0.0,
        )
    positive = sum(1 for s in scores if s.label == "positive")
    negative = sum(1 for s in scores if s.label == "negative")
    neutral = sum(1 for s in scores if s.label == "neutral")
    mean_valence = sum(s.valence for s in scores) / total
    return SentimentStatsReport(
        per_utterance=scores,
        positive_pct=round(positive * 100 / total, 2),
        negative_pct=round(negative * 100 / total, 2),
        neutral_pct=round(neutral * 100 / total, 2),
        mean_valence=round(mean_valence, 4),
    )


async def compute_sentiment_stats(
    utterances: list[Utterance],
    *,
    settings: Settings | None = None,
) -> SentimentStatsReport:
    """Compute per-utterance sentiment scores and aggregate distribution stats.

    Batches utterances into groups of ~10 for cost efficiency. Returns a pure
    Pydantic report with no Vibecheck-specific coupling.
    """
    if not utterances:
        return _aggregate([])

    settings = settings or get_settings()
    agent = build_agent(
        settings,
        output_type=_SentimentBatchLLM,
        system_prompt=_SYSTEM_PROMPT,
        name="vibecheck.sentiment",
    )

    indexed: list[tuple[str, Utterance]] = [
        (_utterance_id(utt, idx), utt) for idx, utt in enumerate(utterances)
    ]

    async def _run_batch(batch: list[tuple[str, Utterance]]) -> list[SentimentScore]:
        prompt = _format_batch(batch)
        async with vertex_slot(settings):
            result = await run_vertex_agent_with_retry(agent, prompt)
        parsed: _SentimentBatchLLM = result.output
        ids_in_order = [uid for uid, _ in batch]
        by_id = {s.utterance_id: s for s in parsed.scores}
        scores: list[SentimentScore] = []
        for uid in ids_in_order:
            llm_score = by_id.get(uid)
            if llm_score is None:
                continue
            scores.append(
                SentimentScore(
                    utterance_id=uid,
                    label=llm_score.label,
                    valence=llm_score.valence,
                )
            )
        return scores

    batches = [
        indexed[start : start + _BATCH_SIZE] for start in range(0, len(indexed), _BATCH_SIZE)
    ]
    tasks = [asyncio.create_task(_run_batch(batch)) for batch in batches]
    try:
        batch_scores = await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    except Exception:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    all_scores = [score for scores in batch_scores for score in scores]

    return _aggregate(all_scores)
