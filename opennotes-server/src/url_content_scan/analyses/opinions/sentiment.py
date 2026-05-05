from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from src.url_content_scan.opinions_schemas import SentimentScore, SentimentStatsReport
from src.url_content_scan.utterances.schema import Utterance

DEFAULT_SENTIMENT_CONCURRENCY = 8


class SentimentClassification(BaseModel):
    label: str = Field(pattern="^(positive|negative|neutral)$")
    valence: float = Field(ge=-1.0, le=1.0)


SentimentClassifier = Callable[[Utterance], Awaitable[SentimentClassification]]


def _round_pct(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count * 100 / total, 2)


async def run_sentiment(
    utterances: list[Utterance],
    *,
    classify_sentiment: SentimentClassifier,
    max_concurrency: int = DEFAULT_SENTIMENT_CONCURRENCY,
) -> SentimentStatsReport:
    if not utterances:
        return SentimentStatsReport(
            per_utterance=[],
            positive_pct=0.0,
            negative_pct=0.0,
            neutral_pct=0.0,
            mean_valence=0.0,
        )

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _classify_one(index: int, utterance: Utterance) -> SentimentScore:
        utterance_id = utterance.utterance_id or f"utt-{index}"
        if not utterance.text.strip():
            return SentimentScore(utterance_id=utterance_id, label="neutral", valence=0.0)
        async with semaphore:
            classification = await classify_sentiment(utterance)
        return SentimentScore(
            utterance_id=utterance_id,
            label=classification.label,
            valence=classification.valence,
        )

    per_utterance = await asyncio.gather(
        *[_classify_one(index, utterance) for index, utterance in enumerate(utterances)]
    )

    total = len(per_utterance)
    positive = sum(1 for row in per_utterance if row.label == "positive")
    negative = sum(1 for row in per_utterance if row.label == "negative")
    neutral = sum(1 for row in per_utterance if row.label == "neutral")
    mean_valence = round(sum(row.valence for row in per_utterance) / total, 4)

    return SentimentStatsReport(
        per_utterance=per_utterance,
        positive_pct=_round_pct(positive, total),
        negative_pct=_round_pct(negative, total),
        neutral_pct=_round_pct(neutral, total),
        mean_valence=mean_valence,
    )


__all__ = [
    "DEFAULT_SENTIMENT_CONCURRENCY",
    "SentimentClassification",
    "SentimentClassifier",
    "run_sentiment",
]
