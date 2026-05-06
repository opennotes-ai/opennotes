"""Automated verification for TASK-1508.09.05.

The tests here intentionally keep the LLM path mocked so they can run as
stable automation while still driving the public `run_trends_oppositions`
slot wrapper end-to-end with realistic FACTS_CLAIMS_DEDUP payloads.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from src.analyses.claims._claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim
from src.analyses.opinions import trends_oppositions_slot
from src.analyses.opinions._trends_schemas import TrendsOppositionsReport
from src.analyses.schemas import SectionSlug
from src.config import Settings


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


def _cluster(text: str, category: ClaimCategory) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=text,
        category=category,
        occurrence_count=1,
        author_count=1,
        utterance_ids=["utterance-1"],
        representative_authors=["analyzer"],
    )


@pytest.mark.asyncio
async def test_trends_oppositions_e2e_realistic_fixture_produces_trends_and_oppositions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[DedupedClaim] = []

    async def fake_extract(clusters: list[DedupedClaim], **kwargs: Any) -> TrendsOppositionsReport:
        assert kwargs["settings"] is not None
        captured.extend(clusters)
        return TrendsOppositionsReport(
            trends=[
                {
                    "label": "Tax fairness debate",
                    "cluster_ids": [clusters[0].canonical_text, clusters[1].canonical_text],
                    "summary": "Multiple speakers repeat the wealth-tax fairness tradeoff.",
                }
            ],
            oppositions=[
                {
                    "topic": "Wealth tax impacts",
                    "supporting_cluster_ids": [clusters[0].canonical_text],
                    "opposing_cluster_ids": [clusters[1].canonical_text],
                    "note": "One cluster argues revenue and fairness, the other forecasts economic harm.",
                }
            ],
            input_cluster_count=len(clusters),
            skipped_for_cap=0,
        )

    monkeypatch.setattr(
        trends_oppositions_slot, "extract_trends_oppositions", fake_extract
    )

    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: _slot_payload(
                _cluster(
                    "Billionaires should pay a wealth tax to fund public services.",
                    ClaimCategory.SUBJECTIVE,
                ),
                _cluster(
                    "A wealth tax would punish investment and hurt the economy.",
                    ClaimCategory.SELF_CLAIMS,
                ),
                _cluster(
                    "The federal budget currently has a shortfall.",
                    ClaimCategory.POTENTIALLY_FACTUAL,
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
    assert len(captured) == 2
    assert [cluster.canonical_text for cluster in captured] == [
        "Billionaires should pay a wealth tax to fund public services.",
        "A wealth tax would punish investment and hurt the economy.",
    ]
    assert len(report["trends"]) >= 1
    assert len(report["oppositions"]) >= 1


@pytest.mark.asyncio
async def test_trends_oppositions_e2e_unanimous_or_empty_fixtures_return_empty_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_extract(clusters: list[DedupedClaim], **kwargs: Any) -> TrendsOppositionsReport:
        assert kwargs["settings"] is not None
        assert len(clusters) == 2
        return TrendsOppositionsReport(
            trends=[],
            oppositions=[],
            input_cluster_count=2,
            skipped_for_cap=0,
        )

    monkeypatch.setattr(
        trends_oppositions_slot, "extract_trends_oppositions", fake_extract
    )

    payload = {
        "sections": {
            SectionSlug.FACTS_CLAIMS_DEDUP.value: _slot_payload(
                _cluster(
                    "A wealth tax is necessary for social equity.",
                    ClaimCategory.SUBJECTIVE,
                ),
                _cluster(
                    "A wealth tax is necessary for social equity.",
                    ClaimCategory.SELF_CLAIMS,
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
