from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.config import Settings, get_settings
from src.url_content_scan.opinions_schemas import (
    OpinionsReport,
    SentimentStatsReport,
    SubjectiveClaim,
    SubjectiveStance,
)
from src.url_content_scan.utterances.schema import Utterance

DEFAULT_SUBJECTIVE_CONCURRENCY = 8

_SYSTEM_PROMPT = """\
Extract subjective claims from a single utterance.

A subjective claim expresses an opinion, preference, evaluation, or stance.
Exclude factual claims that can be externally verified.

For each extracted claim, classify stance as:
- supports
- opposes
- evaluates
"""


class ExtractedSubjectiveClaim(BaseModel):
    claim_text: str
    stance: SubjectiveStance


class _SubjectiveClaimOutput(BaseModel):
    claim_text: str
    stance: SubjectiveStance


class _SubjectiveExtractionResponse(BaseModel):
    claims: list[_SubjectiveClaimOutput] = Field(default_factory=list)


_SUBJECTIVE_AGENT: Agent[None, _SubjectiveExtractionResponse] = Agent(
    name="url-content-scan-subjective",
    output_type=_SubjectiveExtractionResponse,
    instrument=True,
)


SubjectiveExtractor = Callable[
    [Utterance], Awaitable[list[ExtractedSubjectiveClaim | SubjectiveClaim]]
]


async def extract_subjective_claims(
    utterance: Utterance,
    *,
    settings: Settings | None = None,
) -> list[ExtractedSubjectiveClaim]:
    text = utterance.text.strip()
    if not text:
        return []

    cfg = settings or get_settings()
    result = await _SUBJECTIVE_AGENT.run(
        text,
        model=cfg.DEFAULT_MINI_MODEL.to_pydantic_ai_model(),
        instructions=_SYSTEM_PROMPT,
        model_settings=ModelSettings(temperature=0.0),
    )
    return [
        ExtractedSubjectiveClaim(claim_text=claim.claim_text, stance=claim.stance)
        for claim in result.output.claims
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
    extract_subjective_claims: SubjectiveExtractor | None = None,
    max_concurrency: int = DEFAULT_SUBJECTIVE_CONCURRENCY,
    sentiment_stats: SentimentStatsReport | None = None,
) -> OpinionsReport:
    if not utterances:
        return OpinionsReport(
            sentiment_stats=sentiment_stats or _zero_sentiment_stats(),
            subjective_claims=[],
        )

    semaphore = asyncio.Semaphore(max_concurrency)
    extractor = extract_subjective_claims or globals()["extract_subjective_claims"]

    async def _extract_one(index: int, utterance: Utterance) -> list[SubjectiveClaim]:
        utterance_id = utterance.utterance_id or f"utt-{index}"
        if not utterance.text.strip():
            return []
        async with semaphore:
            extracted = await extractor(utterance)
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
    "extract_subjective_claims",
    "run_subjective",
]
