from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.url_content_scan.utterances.schema import Utterance


@pytest.mark.asyncio
async def test_run_sentiment_uses_default_classifier_when_not_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.url_content_scan.analyses.opinions.sentiment import (
        _SentimentAgentOutput,
        run_sentiment,
    )

    utterances = [
        Utterance(utterance_id="u-1", kind="post", text="I love this feature."),
        Utterance(utterance_id="u-2", kind="comment", text="This is broken."),
    ]

    async def fake_run(prompt: str, **kwargs: object) -> SimpleNamespace:
        assert prompt in {"I love this feature.", "This is broken."}
        assert kwargs["model"] is not None
        by_prompt = {
            "I love this feature.": _SentimentAgentOutput(label="positive", valence=0.8),
            "This is broken.": _SentimentAgentOutput(label="negative", valence=-0.7),
        }
        return SimpleNamespace(output=by_prompt[prompt])

    monkeypatch.setattr(
        "src.url_content_scan.analyses.opinions.sentiment._SENTIMENT_AGENT.run",
        fake_run,
    )

    report = await run_sentiment(utterances)

    assert [row.label for row in report.per_utterance] == ["positive", "negative"]
    assert report.positive_pct == 50.0
    assert report.negative_pct == 50.0
    assert report.neutral_pct == 0.0
