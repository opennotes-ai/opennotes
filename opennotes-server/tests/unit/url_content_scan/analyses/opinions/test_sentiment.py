from __future__ import annotations

import pytest

from src.url_content_scan.utterances.schema import Utterance


@pytest.mark.asyncio
async def test_run_sentiment_aggregates_labels_over_all_utterances() -> None:
    from src.url_content_scan.analyses.opinions.sentiment import (
        SentimentClassification,
        run_sentiment,
    )

    utterances = [
        Utterance(utterance_id="u-1", kind="post", text="I love this feature."),
        Utterance(utterance_id="u-2", kind="comment", text="This is broken."),
        Utterance(utterance_id="u-3", kind="reply", text="The release shipped yesterday."),
    ]

    async def fake_classify(utterance: Utterance) -> SentimentClassification:
        by_id = {
            "u-1": SentimentClassification(label="positive", valence=0.9),
            "u-2": SentimentClassification(label="negative", valence=-0.8),
            "u-3": SentimentClassification(label="neutral", valence=0.0),
        }
        return by_id[utterance.utterance_id or ""]

    report = await run_sentiment(utterances, classify_sentiment=fake_classify)

    assert len(report.per_utterance) == len(utterances)
    counts = {
        "positive": sum(1 for row in report.per_utterance if row.label == "positive"),
        "negative": sum(1 for row in report.per_utterance if row.label == "negative"),
        "neutral": sum(1 for row in report.per_utterance if row.label == "neutral"),
    }
    assert sum(counts.values()) == len(utterances)
    assert counts == {"positive": 1, "negative": 1, "neutral": 1}
    assert report.positive_pct == pytest.approx(33.33, abs=0.01)
    assert report.negative_pct == pytest.approx(33.33, abs=0.01)
    assert report.neutral_pct == pytest.approx(33.33, abs=0.01)
    assert report.mean_valence == pytest.approx((0.9 - 0.8 + 0.0) / 3, abs=1e-4)
