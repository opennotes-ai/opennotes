from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.url_content_scan.claims_schemas import ClaimCategory, DedupedClaim
from src.url_content_scan.opinions_schemas import (
    empty_trends_oppositions_report,
)


def _cluster(
    canonical_text: str,
    *,
    category: ClaimCategory,
    occurrence_count: int = 1,
    author_count: int = 1,
) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=canonical_text,
        category=category,
        occurrence_count=occurrence_count,
        author_count=author_count,
        utterance_ids=["u-1"],
        representative_authors=["alice"],
    )


@pytest.mark.asyncio
async def test_run_trends_oppositions_empty_input_returns_empty_report() -> None:
    from src.url_content_scan.analyses.opinions.trends_oppositions import run_trends_oppositions

    report = await run_trends_oppositions([])

    assert report == empty_trends_oppositions_report()
    assert report.input_cluster_count == 0
    assert report.skipped_for_cap == 0
    assert report.trends == []
    assert report.oppositions == []


@pytest.mark.asyncio
async def test_run_trends_oppositions_filters_to_subjective_and_self_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.opinions import trends_oppositions as module

    clusters = [
        _cluster("subjective opinion", category=ClaimCategory.SUBJECTIVE, occurrence_count=10),
        _cluster("self claim", category=ClaimCategory.SELF_CLAIMS, occurrence_count=8),
        _cluster("factual claim", category=ClaimCategory.POTENTIALLY_FACTUAL, occurrence_count=30),
        _cluster("prediction", category=ClaimCategory.PREDICTIONS, occurrence_count=12),
    ]

    captured_prompt: list[str] = []
    fake_result = MagicMock()
    fake_result.output.trends = []
    fake_result.output.oppositions = []

    async def fake_run(agent: object, user_prompt: str) -> object:
        captured_prompt.append(user_prompt)
        return fake_result

    mock_agent = MagicMock()
    monkeypatch.setattr(module, "_TRENDS_AGENT", mock_agent)
    monkeypatch.setattr(module, "_run_agent", fake_run)

    report = await module.run_trends_oppositions(clusters)

    assert report.input_cluster_count == 2
    assert "subjective opinion" in captured_prompt[0]
    assert "self claim" in captured_prompt[0]
    assert "factual claim" not in captured_prompt[0]
    assert "prediction" not in captured_prompt[0]


@pytest.mark.asyncio
async def test_run_trends_oppositions_detects_oppositions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.opinions import trends_oppositions as module

    clusters = [
        _cluster("We should raise taxes.", category=ClaimCategory.SUBJECTIVE, occurrence_count=12),
        _cluster(
            "We should not raise taxes.", category=ClaimCategory.SELF_CLAIMS, occurrence_count=11
        ),
    ]

    fake_opposition = MagicMock()
    fake_opposition.topic = "Tax policy"
    fake_opposition.supporting_cluster_indices = [0]
    fake_opposition.opposing_cluster_indices = [1]
    fake_opposition.note = "A direct policy split"

    fake_result = MagicMock()
    fake_result.output.trends = []
    fake_result.output.oppositions = [fake_opposition]

    async def fake_run(agent: object, user_prompt: str) -> object:
        return fake_result

    monkeypatch.setattr(module, "_run_agent", fake_run)

    report = await module.run_trends_oppositions(clusters)

    assert len(report.oppositions) == 1
    opp = report.oppositions[0]
    assert opp.topic == "Tax policy"
    assert opp.supporting_cluster_texts == [clusters[0].canonical_text]
    assert opp.opposing_cluster_texts == [clusters[1].canonical_text]
    assert opp.note == "A direct policy split"


@pytest.mark.asyncio
async def test_run_trends_oppositions_extracts_trends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.opinions import trends_oppositions as module

    clusters = [
        _cluster(
            "Healthcare too expensive.", category=ClaimCategory.SUBJECTIVE, occurrence_count=25
        ),
        _cluster(
            "Insurance costs are high.", category=ClaimCategory.SUBJECTIVE, occurrence_count=8
        ),
    ]

    fake_trend = MagicMock()
    fake_trend.label = "Healthcare cost concerns"
    fake_trend.cluster_indices = [0, 1]
    fake_trend.summary = "Clusters mention healthcare costs."

    fake_result = MagicMock()
    fake_result.output.trends = [fake_trend]
    fake_result.output.oppositions = []

    async def fake_run(agent: object, user_prompt: str) -> object:
        return fake_result

    monkeypatch.setattr(module, "_run_agent", fake_run)

    report = await module.run_trends_oppositions(clusters)

    assert len(report.trends) == 1
    trend = report.trends[0]
    assert trend.label == "Healthcare cost concerns"
    assert trend.cluster_texts == [clusters[0].canonical_text, clusters[1].canonical_text]


@pytest.mark.asyncio
async def test_run_trends_oppositions_caps_clusters_via_max_clusters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.opinions import trends_oppositions as module

    clusters = [
        _cluster(f"topic-{i:02d}", category=ClaimCategory.SUBJECTIVE, occurrence_count=60 - i)
        for i in range(60)
    ]

    captured_prompt: list[str] = []
    fake_result = MagicMock()
    fake_result.output.trends = []
    fake_result.output.oppositions = []

    async def fake_run(agent: object, user_prompt: str) -> object:
        captured_prompt.append(user_prompt)
        return fake_result

    monkeypatch.setattr(module, "_run_agent", fake_run)

    report = await module.run_trends_oppositions(clusters, max_clusters=50)

    assert report.input_cluster_count == 50
    assert report.skipped_for_cap == 10
    assert "topic-00" in captured_prompt[0]
    assert "topic-49" in captured_prompt[0]
    assert "topic-50" not in captured_prompt[0]


@pytest.mark.asyncio
async def test_run_trends_oppositions_ignores_out_of_range_indices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.opinions import trends_oppositions as module

    clusters = [
        _cluster("Valid cluster A.", category=ClaimCategory.SUBJECTIVE, occurrence_count=10),
        _cluster("Valid cluster B.", category=ClaimCategory.SELF_CLAIMS, occurrence_count=9),
    ]

    fake_trend = MagicMock()
    fake_trend.label = "Mismatched"
    fake_trend.cluster_indices = [0, 99]
    fake_trend.summary = "One valid, one dropped."

    fake_opposition = MagicMock()
    fake_opposition.topic = "Bad indices"
    fake_opposition.supporting_cluster_indices = [99]
    fake_opposition.opposing_cluster_indices = [-1]
    fake_opposition.note = None

    fake_result = MagicMock()
    fake_result.output.trends = [fake_trend]
    fake_result.output.oppositions = [fake_opposition]

    async def fake_run(agent: object, user_prompt: str) -> object:
        return fake_result

    monkeypatch.setattr(module, "_run_agent", fake_run)

    report = await module.run_trends_oppositions(clusters)

    assert len(report.trends) == 1
    assert report.trends[0].cluster_texts == [clusters[0].canonical_text]
    assert report.oppositions[0].supporting_cluster_texts == []
    assert report.oppositions[0].opposing_cluster_texts == []
