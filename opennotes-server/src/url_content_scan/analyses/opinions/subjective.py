from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from src.url_content_scan.opinions_schemas import (
    OpinionsReport,
    SentimentStatsReport,
    SubjectiveClaim,
    SubjectiveStance,
)
from src.url_content_scan.utterances.schema import Utterance

DEFAULT_SUBJECTIVE_CONCURRENCY = 8


class ExtractedSubjectiveClaim(BaseModel):
    claim_text: str
    stance: SubjectiveStance


SubjectiveExtractor = Callable[
    [Utterance], Awaitable[list[ExtractedSubjectiveClaim | SubjectiveClaim]]
]


def _zero_sentiment_stats() -> SentimentStatsReport:
    return SentimentStatsReport(
        per_utterance=[],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=0.0,
        mean_valence=0.0,
    )


async def run_subjective(
    utterances: list[Utterance],
    *,
    extract_subjective_claims: SubjectiveExtractor,
    max_concurrency: int = DEFAULT_SUBJECTIVE_CONCURRENCY,
    sentiment_stats: SentimentStatsReport | None = None,
) -> OpinionsReport:
    if not utterances:
        return OpinionsReport(
            sentiment_stats=sentiment_stats or _zero_sentiment_stats(),
            subjective_claims=[],
        )

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _extract_one(index: int, utterance: Utterance) -> list[SubjectiveClaim]:
        utterance_id = utterance.utterance_id or f"utt-{index}"
        if not utterance.text.strip():
            return []
        async with semaphore:
            extracted = await extract_subjective_claims(utterance)
        claims: list[SubjectiveClaim] = []
        for item in extracted:
            if isinstance(item, SubjectiveClaim):
                claims.append(item)
            else:
                claims.append(
                    SubjectiveClaim(
                        claim_text=item.claim_text,
                        utterance_id=utterance_id,
                        stance=item.stance,
                    )
                )
        return claims

    subjective_claim_batches: list[list[SubjectiveClaim]] = [[] for _utterance in utterances]

    async def _store_one(index: int, utterance: Utterance) -> None:
        subjective_claim_batches[index] = await _extract_one(index, utterance)

    async with asyncio.TaskGroup() as task_group:
        for index, utterance in enumerate(utterances):
            task_group.create_task(_store_one(index, utterance))
    subjective_claims = [
        claim
        for claim_batch in subjective_claim_batches
        for claim in claim_batch
        if claim.claim_text.strip()
    ]

    return OpinionsReport(
        sentiment_stats=sentiment_stats or _zero_sentiment_stats(),
        subjective_claims=subjective_claims,
    )


__all__ = [
    "DEFAULT_SUBJECTIVE_CONCURRENCY",
    "ExtractedSubjectiveClaim",
    "SubjectiveExtractor",
    "run_subjective",
]
