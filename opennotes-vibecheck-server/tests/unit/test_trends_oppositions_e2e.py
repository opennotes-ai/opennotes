"""Automated verification for TASK-1508.09.05.

These tests avoid live LLM calls, but they exercise the public
`run_trends_oppositions` slot plus the analyzer prompt/output/index-resolution
contract using a scripted agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from src.analyses.claims._claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
from src.analyses.opinions import trends_oppositions as trends_oppositions_module
from src.analyses.opinions import trends_oppositions_slot
from src.analyses.opinions.trends_oppositions_testing import (
    OppositionLLMForTest,
    TrendLLMForTest,
    TrendsOppositionsLLMForTest,
)
from src.analyses.schemas import SectionSlug
from src.config import Settings


@dataclass
class _FakeRunResult:
    output: Any


class _ScriptedAgent:
    def __init__(self, output: Any) -> None:
        self.output = output
        self.calls: list[str] = []

    async def run(self, prompt: str) -> _FakeRunResult:
        self.calls.append(prompt)
        return _FakeRunResult(output=self.output)


def _settings() -> Settings:
    return Settings()


def _slot_payload(*clusters: DedupedClaim) -> dict[str, Any]:
    return {
        "state": "done",
        "attempt_id": str(uuid4()),
        "data": {
            "claims_report": ClaimsReport(
                deduped_claims=list(clusters),
                total_claims=len(clusters),
                total_unique=len(clusters),
            ).model_dump(mode="json")
        },
    }


def _cluster(
    text: str,
    category: ClaimCategory,
    *,
    occurrence_count: int,
    author_count: int,
    utterance_ids: list[str],
    representative_authors: list[str],
) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=text,
        category=category,
        occurrence_count=occurrence_count,
        author_count=author_count,
        utterance_ids=utterance_ids,
        representative_authors=representative_authors,
    )


@pytest.mark.asyncio
async def test_trends_oppositions_e2e_wealth_tax_fixture_produces_trends_and_oppositions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripted = _ScriptedAgent(
        TrendsOppositionsLLMForTest(
            trends=[
                TrendLLMForTest(
                    label="Tax fairness debate",
                    cluster_indices=[0, 2],
                    summary="Speakers repeatedly frame the wealth tax as a fairness and services question.",
                )
            ],
            oppositions=[
                OppositionLLMForTest(
                    topic="Wealth tax economic impact",
                    supporting_cluster_indices=[0],
                    opposing_cluster_indices=[1],
                    note="One side emphasizes revenue and fairness; the other predicts investment harm.",
                )
            ],
        )
    )
    monkeypatch.setattr(
        trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted
    )

    support = "Billionaires should pay a wealth tax to fund public services."
    oppose = "A wealth tax would punish investment and hurt the economy."
    services = "A wealth tax is fair because extreme fortunes depend on public infrastructure."
    factual = "The federal budget currently has a shortfall."
    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: _slot_payload(
                _cluster(
                    support,
                    ClaimCategory.SUBJECTIVE,
                    occurrence_count=14,
                    author_count=8,
                    utterance_ids=["u-support-1", "u-support-2", "u-support-3"],
                    representative_authors=["ana", "bea", "cam"],
                ),
                _cluster(
                    oppose,
                    ClaimCategory.SELF_CLAIMS,
                    occurrence_count=13,
                    author_count=7,
                    utterance_ids=["u-oppose-1", "u-oppose-2"],
                    representative_authors=["dev", "eli"],
                ),
                _cluster(
                    services,
                    ClaimCategory.SUBJECTIVE,
                    occurrence_count=9,
                    author_count=5,
                    utterance_ids=["u-services-1", "u-services-2"],
                    representative_authors=["flo", "gus"],
                ),
                _cluster(
                    factual,
                    ClaimCategory.POTENTIALLY_FACTUAL,
                    occurrence_count=50,
                    author_count=20,
                    utterance_ids=["u-fact-1"],
                    representative_authors=["hal"],
                ),
            )
        }
    }

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=payload,
        settings=_settings(),
    )

    report = result["trends_oppositions_report"]
    assert report["input_cluster_count"] == 3
    assert report["skipped_for_cap"] == 0
    assert report["trends"] == [
        {
            "label": "Tax fairness debate",
            "cluster_texts": [support, services],
            "summary": "Speakers repeatedly frame the wealth tax as a fairness and services question.",
        }
    ]
    assert report["oppositions"] == [
        {
            "topic": "Wealth tax economic impact",
            "supporting_cluster_texts": [support],
            "opposing_cluster_texts": [oppose],
            "note": "One side emphasizes revenue and fairness; the other predicts investment harm.",
        }
    ]

    assert len(scripted.calls) == 1
    prompt = scripted.calls[0]
    assert "[0] (occ=14, authors=8, category=subjective)" in prompt
    assert "[1] (occ=13, authors=7, category=self_claims)" in prompt
    assert "[2] (occ=9, authors=5, category=subjective)" in prompt
    assert support in prompt
    assert oppose in prompt
    assert services in prompt
    assert factual not in prompt


@pytest.mark.asyncio
async def test_trends_oppositions_e2e_no_relevant_opinion_clusters_returns_empty_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripted = _ScriptedAgent(
        TrendsOppositionsLLMForTest(
            trends=[],
            oppositions=[],
        )
    )
    monkeypatch.setattr(
        trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted
    )

    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: _slot_payload(
                _cluster(
                    "The proposed wealth tax would apply to households above a statutory threshold.",
                    ClaimCategory.POTENTIALLY_FACTUAL,
                    occurrence_count=4,
                    author_count=3,
                    utterance_ids=["u-fact-only"],
                    representative_authors=["ivy"],
                ),
                _cluster(
                    "The vote is scheduled for next month.",
                    ClaimCategory.PREDICTIONS,
                    occurrence_count=2,
                    author_count=2,
                    utterance_ids=["u-prediction"],
                    representative_authors=["jay"],
                ),
            )
        }
    }

    result = await trends_oppositions_slot.run_trends_oppositions(
        pool=object(),
        job_id=uuid4(),
        task_attempt=uuid4(),
        payload=payload,
        settings=_settings(),
    )

    report = result["trends_oppositions_report"]
    assert report["trends"] == []
    assert report["oppositions"] == []
    assert report["input_cluster_count"] == 0
    assert report["skipped_for_cap"] == 0
    assert scripted.calls == []
