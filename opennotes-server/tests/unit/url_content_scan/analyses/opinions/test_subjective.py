from __future__ import annotations

import pytest

from src.url_content_scan.utterances.schema import Utterance


@pytest.mark.asyncio
async def test_run_subjective_tolerates_empty_outputs() -> None:
    from src.url_content_scan.analyses.opinions.subjective import run_subjective

    utterances = [
        Utterance(utterance_id="u-1", kind="post", text="The sky is blue."),
        Utterance(utterance_id="u-2", kind="comment", text="Water boils at 100C."),
    ]

    async def fake_extract(_utterance: Utterance) -> list[object]:
        return []

    report = await run_subjective(utterances, extract_subjective_claims=fake_extract)

    assert report.subjective_claims == []
    assert report.sentiment_stats.per_utterance == []
    assert report.sentiment_stats.positive_pct == 0.0
    assert report.sentiment_stats.negative_pct == 0.0
    assert report.sentiment_stats.neutral_pct == 0.0
