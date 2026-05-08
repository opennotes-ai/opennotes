from __future__ import annotations

from typing import Any

import pytest

from src.analyses.claims._claims_schemas import ClaimCategory, DedupedClaim
from src.analyses.opinions import trends_oppositions as trends_oppositions_module
from src.analyses.opinions._trends_schemas import TrendsOppositionsReport
from src.analyses.opinions.trends_oppositions_testing import (
    OppositionLLMForTest,
    TrendLLMForTest,
    TrendsOppositionsLLMForTest,
)
from src.config import Settings


class _FakeRunResult:
    def __init__(self, output: Any) -> None:
        self.output = output


class _ScriptedAgent:
    def __init__(
        self,
        responses_by_prompt: dict[str, TrendsOppositionsLLMForTest],
        default: TrendsOppositionsLLMForTest | None = None,
    ) -> None:
        self._responses_by_prompt = responses_by_prompt
        self._default = default or TrendsOppositionsLLMForTest(trends=[], oppositions=[])
        self.calls: list[str] = []

    async def run(self, prompt: str) -> _FakeRunResult:
        self.calls.append(prompt)
        for needle, payload in self._responses_by_prompt.items():
            if needle in prompt:
                return _FakeRunResult(output=payload)
        return _FakeRunResult(output=self._default)


def _cluster(
    canonical_text: str,
    *,
    category: ClaimCategory,
    occurrence_count: int = 1,
    author_count: int = 1,
    utterance_ids: list[str] | None = None,
    representative_authors: list[str] | None = None,
) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=canonical_text,
        category=category,
        occurrence_count=occurrence_count,
        author_count=author_count,
        utterance_ids=utterance_ids or ["u-1"],
        representative_authors=representative_authors or ["alice"],
    )


async def test_extract_trends_oppositions_empty_input_no_llm_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripted = _ScriptedAgent(
        {
            "unused": TrendsOppositionsLLMForTest(
                trends=[],
                oppositions=[],
            )
        }
    )
    monkeypatch.setattr(
        trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted
    )

    report = await trends_oppositions_module.extract_trends_oppositions([])

    assert report == TrendsOppositionsReport(
        trends=[],
        oppositions=[],
        input_cluster_count=0,
        skipped_for_cap=0,
    )
    assert scripted.calls == []


async def test_extract_trends_oppositions_detects_opposition_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clusters = [
        _cluster(
            "We should raise wealth taxes on billionaires.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=12,
        ),
        _cluster(
            "We should not raise wealth taxes.",
            category=ClaimCategory.SELF_CLAIMS,
            occurrence_count=11,
        ),
    ]

    scripted = _ScriptedAgent(
        {
            "We should raise wealth taxes": TrendsOppositionsLLMForTest(
                trends=[],
                oppositions=[
                    OppositionLLMForTest(
                        topic="Wealth-tax policy",
                        supporting_cluster_indices=[0],
                        opposing_cluster_indices=[1],
                        note="A direct policy split between raising and not raising taxes",
                    )
                ],
            ),
        }
    )
    monkeypatch.setattr(trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted)

    report = await trends_oppositions_module.extract_trends_oppositions(clusters)

    assert report.input_cluster_count == 2
    assert report.skipped_for_cap == 0
    assert len(report.oppositions) == 1
    opposition = report.oppositions[0]
    assert opposition.topic == "Wealth-tax policy"
    assert opposition.supporting_cluster_texts == [clusters[0].canonical_text]
    assert opposition.opposing_cluster_texts == [clusters[1].canonical_text]
    assert opposition.note == "A direct policy split between raising and not raising taxes"


async def test_extract_trends_oppositions_extracts_recurring_trends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clusters = [
        _cluster(
            "People should pay more for luxury healthcare.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=25,
        ),
        _cluster(
            "Healthcare spending is too high for households.",
            category=ClaimCategory.SELF_CLAIMS,
            occurrence_count=8,
        ),
        _cluster(
            "Insurance costs are out of control.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=7,
        ),
    ]

    scripted = _ScriptedAgent(
        {
            "Analyze the opinion clusters": TrendsOppositionsLLMForTest(
                trends=[
                    TrendLLMForTest(
                        label="Rising healthcare-cost concerns",
                        cluster_indices=[0, 2],
                        summary="Multiple clusters repeatedly mention healthcare spending pain points.",
                    )
                ],
                oppositions=[],
            )
        }
    )
    monkeypatch.setattr(trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted)

    report = await trends_oppositions_module.extract_trends_oppositions(clusters)

    assert report.input_cluster_count == 3
    assert report.skipped_for_cap == 0
    assert len(report.trends) == 1
    trend = report.trends[0]
    assert trend.label == "Rising healthcare-cost concerns"
    assert trend.summary == "Multiple clusters repeatedly mention healthcare spending pain points."
    assert trend.cluster_texts == [clusters[0].canonical_text, clusters[2].canonical_text]


async def test_extract_trends_oppositions_capting_limits_prompt_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clusters = [
        _cluster(
            f"topic-{i:02d}",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=60 - i,
        )
        for i in range(60)
    ]

    scripted = _ScriptedAgent(
        {
            "topic-00": TrendsOppositionsLLMForTest(trends=[], oppositions=[]),
        }
    )
    monkeypatch.setattr(trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted)

    report = await trends_oppositions_module.extract_trends_oppositions(clusters, max_clusters=50)

    assert report.input_cluster_count == 50
    assert report.skipped_for_cap == 10
    assert scripted.calls
    prompt = scripted.calls[0]
    assert "topic-00" in prompt
    assert "topic-49" in prompt
    assert "topic-50" not in prompt
    assert "topic-59" not in prompt


async def test_extract_trends_oppositions_uses_settings_cluster_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clusters = [
        _cluster(
            f"settings-topic-{i}",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=10 - i,
        )
        for i in range(3)
    ]

    scripted = _ScriptedAgent(
        {
            "settings-topic-0": TrendsOppositionsLLMForTest(
                trends=[],
                oppositions=[],
            ),
        }
    )
    monkeypatch.setattr(trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted)

    report = await trends_oppositions_module.extract_trends_oppositions(
        clusters,
        settings=Settings(VIBECHECK_TRENDS_OPPOSITIONS_MAX_CLUSTERS=1),
    )

    assert report.input_cluster_count == 1
    assert report.skipped_for_cap == 2
    assert scripted.calls
    assert "settings-topic-0" in scripted.calls[0]
    assert "settings-topic-1" not in scripted.calls[0]


async def test_extract_trends_oppositions_filters_to_subjective_and_self_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clusters = [
        _cluster(
            "I think the UI is intuitive.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=10,
        ),
        _cluster(
            "I personally prefer the dark theme.",
            category=ClaimCategory.SELF_CLAIMS,
            occurrence_count=8,
        ),
        _cluster(
            "The moon orbits Earth.",
            category=ClaimCategory.POTENTIALLY_FACTUAL,
            occurrence_count=30,
        ),
        _cluster(
            "It might rain tomorrow.",
            category=ClaimCategory.PREDICTIONS,
            occurrence_count=12,
        ),
    ]

    scripted = _ScriptedAgent({})
    monkeypatch.setattr(trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted)

    report = await trends_oppositions_module.extract_trends_oppositions(clusters)

    assert report.input_cluster_count == 2
    assert report.skipped_for_cap == 0
    assert scripted.calls
    prompt = scripted.calls[0]
    assert "I think the UI is intuitive." in prompt
    assert "I personally prefer the dark theme." in prompt
    assert "The moon orbits Earth." not in prompt
    assert "It might rain tomorrow." not in prompt


async def test_extract_trends_oppositions_ignores_out_of_range_indices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clusters = [
        _cluster(
            "The policy is fair.",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=10,
        ),
        _cluster(
            "Taxes should be lower.",
            category=ClaimCategory.SELF_CLAIMS,
            occurrence_count=9,
        ),
    ]

    scripted = _ScriptedAgent(
        {
            "The policy is fair": TrendsOppositionsLLMForTest(
                trends=[
                    TrendLLMForTest(
                        label="Mismatched indexing",
                        cluster_indices=[0, 7],
                        summary="One valid and one dropped index.",
                    )
                ],
                oppositions=[
                    OppositionLLMForTest(
                        topic="Mismatched indices",
                        supporting_cluster_indices=[3],
                        opposing_cluster_indices=[-1],
                    )
                ],
            )
        }
    )
    monkeypatch.setattr(trends_oppositions_module, "build_agent", lambda *args, **kwargs: scripted)

    report = await trends_oppositions_module.extract_trends_oppositions(clusters)

    assert len(report.trends) == 1
    assert report.trends[0].cluster_texts == [clusters[0].canonical_text]
    assert report.oppositions[0].supporting_cluster_texts == []
    assert report.oppositions[0].opposing_cluster_texts == []
