from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.config import Settings, get_settings
from src.url_content_scan.opinions_schemas import SentimentScore, SentimentStatsReport
from src.url_content_scan.utterances.schema import Utterance

DEFAULT_SENTIMENT_CONCURRENCY = 8

_SYSTEM_PROMPT = """\
Classify the sentiment of a single utterance.

Return:
- label: positive, negative, or neutral
- valence: a score in [-1.0, 1.0]

Use neutral for factual or unclear text.
"""


class SentimentClassification(BaseModel):
    label: str = Field(pattern="^(positive|negative|neutral)$")
    valence: float = Field(ge=-1.0, le=1.0)


class _SentimentAgentOutput(SentimentClassification):
    pass


_SENTIMENT_AGENT: Agent[None, _SentimentAgentOutput] = Agent(
    name="url-content-scan-sentiment",
    output_type=_SentimentAgentOutput,
    instrument=True,
)


SentimentClassifier = Callable[[Utterance], Awaitable[SentimentClassification]]


async def classify_sentiment(
    utterance: Utterance,
    *,
    settings: Settings | None = None,
) -> SentimentClassification:
    text = utterance.text.strip()
    if not text:
        return SentimentClassification(label="neutral", valence=0.0)

    cfg = settings or get_settings()
    result = await _SENTIMENT_AGENT.run(
        text,
        model=cfg.DEFAULT_MINI_MODEL.to_pydantic_ai_model(),
        instructions=_SYSTEM_PROMPT,
        model_settings=ModelSettings(temperature=0.0),
    )
    return SentimentClassification(
        label=result.output.label,
        valence=result.output.valence,
    )


def _round_pct(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count * 100 / total, 2)


async def run_sentiment(
    utterances: list[Utterance],
    *,
    classify_sentiment: SentimentClassifier | None = None,
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
    classifier = classify_sentiment or globals()["classify_sentiment"]

    async def _classify_one(index: int, utterance: Utterance) -> SentimentScore:
        utterance_id = utterance.utterance_id or f"utt-{index}"
        if not utterance.text.strip():
            return SentimentScore(utterance_id=utterance_id, label="neutral", valence=0.0)
        async with semaphore:
            classification = await classifier(utterance)
        return SentimentScore(
            utterance_id=utterance_id,
            label=classification.label,
            valence=classification.valence,
        )

    per_utterance: list[SentimentScore | None] = [None for _utterance in utterances]

    async def _store_one(index: int, utterance: Utterance) -> None:
        per_utterance[index] = await _classify_one(index, utterance)

    async with asyncio.TaskGroup() as task_group:
        for index, utterance in enumerate(utterances):
            task_group.create_task(_store_one(index, utterance))

    scores = [score for score in per_utterance if score is not None]

    total = len(scores)
    positive = sum(1 for row in scores if row.label == "positive")
    negative = sum(1 for row in scores if row.label == "negative")
    neutral = sum(1 for row in scores if row.label == "neutral")
    mean_valence = round(sum(row.valence for row in scores) / total, 4)

    return SentimentStatsReport(
        per_utterance=scores,
        positive_pct=_round_pct(positive, total),
        negative_pct=_round_pct(negative, total),
        neutral_pct=_round_pct(neutral, total),
        mean_valence=mean_valence,
    )


__all__ = [
    "DEFAULT_SENTIMENT_CONCURRENCY",
    "SentimentClassification",
    "SentimentClassifier",
    "classify_sentiment",
    "run_sentiment",
]
