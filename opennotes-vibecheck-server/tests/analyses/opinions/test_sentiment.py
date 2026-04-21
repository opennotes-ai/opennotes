from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.analyses.opinions import sentiment as sentiment_module
from src.analyses.opinions._schemas import _SentimentBatchLLM, _SentimentScoreLLM
from src.analyses.opinions.sentiment import compute_sentiment_stats
from src.utterances.schema import Utterance


@dataclass
class _FakeRunResult:
    output: Any


class _FakeAgent:
    def __init__(self, batches: list[_SentimentBatchLLM]) -> None:
        self._batches = list(batches)
        self.calls: list[str] = []

    async def run(self, prompt: str) -> _FakeRunResult:
        self.calls.append(prompt)
        if not self._batches:
            return _FakeRunResult(output=_SentimentBatchLLM(scores=[]))
        return _FakeRunResult(output=self._batches.pop(0))


def _build_utterances() -> list[Utterance]:
    return [
        Utterance(utterance_id="u1", kind="post", text="I love this feature!"),
        Utterance(utterance_id="u2", kind="comment", text="Absolutely brilliant work."),
        Utterance(utterance_id="u3", kind="reply", text="Fantastic improvement."),
        Utterance(utterance_id="u4", kind="comment", text="This is terrible and broken."),
        Utterance(utterance_id="u5", kind="comment", text="I hate the new layout."),
        Utterance(utterance_id="u6", kind="reply", text="The release shipped on Tuesday."),
    ]


def _fixture_batch() -> _SentimentBatchLLM:
    return _SentimentBatchLLM(
        scores=[
            _SentimentScoreLLM(utterance_id="u1", label="positive", valence=0.9),
            _SentimentScoreLLM(utterance_id="u2", label="positive", valence=0.8),
            _SentimentScoreLLM(utterance_id="u3", label="positive", valence=0.7),
            _SentimentScoreLLM(utterance_id="u4", label="negative", valence=-0.8),
            _SentimentScoreLLM(utterance_id="u5", label="negative", valence=-0.7),
            _SentimentScoreLLM(utterance_id="u6", label="neutral", valence=0.0),
        ]
    )


async def test_compute_sentiment_stats_50_33_17_distribution(monkeypatch):
    fake = _FakeAgent([_fixture_batch()])
    monkeypatch.setattr(
        sentiment_module, "build_agent", lambda *args, **kwargs: fake
    )

    report = await compute_sentiment_stats(_build_utterances())

    assert len(report.per_utterance) == 6
    assert report.positive_pct == 50.0
    assert report.negative_pct == pytest.approx(33.33, abs=0.01)
    assert report.neutral_pct == pytest.approx(16.67, abs=0.01)
    assert report.mean_valence == pytest.approx((0.9 + 0.8 + 0.7 - 0.8 - 0.7 + 0.0) / 6, abs=1e-4)
    assert {s.utterance_id for s in report.per_utterance} == {"u1", "u2", "u3", "u4", "u5", "u6"}


async def test_compute_sentiment_stats_empty_returns_zeroed_report(monkeypatch):
    fake = _FakeAgent([])
    monkeypatch.setattr(
        sentiment_module, "build_agent", lambda *args, **kwargs: fake
    )

    report = await compute_sentiment_stats([])

    assert report.per_utterance == []
    assert report.positive_pct == 0.0
    assert report.negative_pct == 0.0
    assert report.neutral_pct == 0.0
    assert report.mean_valence == 0.0
    assert fake.calls == []


async def test_compute_sentiment_stats_batches_in_tens(monkeypatch):
    utterances = [
        Utterance(utterance_id=f"u{i}", kind="comment", text=f"utterance {i}")
        for i in range(23)
    ]

    batches = [
        _SentimentBatchLLM(
            scores=[
                _SentimentScoreLLM(
                    utterance_id=f"u{i}", label="neutral", valence=0.0
                )
                for i in range(start, min(start + 10, 23))
            ]
        )
        for start in range(0, 23, 10)
    ]

    fake = _FakeAgent(batches)
    monkeypatch.setattr(
        sentiment_module, "build_agent", lambda *args, **kwargs: fake
    )

    report = await compute_sentiment_stats(utterances)

    assert len(report.per_utterance) == 23
    assert report.neutral_pct == 100.0
    assert len(fake.calls) == 3


async def test_compute_sentiment_stats_assigns_fallback_ids(monkeypatch):
    utterances = [
        Utterance(kind="post", text="Great job!"),
        Utterance(kind="comment", text="This is bad."),
    ]
    fake = _FakeAgent(
        [
            _SentimentBatchLLM(
                scores=[
                    _SentimentScoreLLM(
                        utterance_id="utt-0", label="positive", valence=0.9
                    ),
                    _SentimentScoreLLM(
                        utterance_id="utt-1", label="negative", valence=-0.9
                    ),
                ]
            )
        ]
    )
    monkeypatch.setattr(
        sentiment_module, "build_agent", lambda *args, **kwargs: fake
    )

    report = await compute_sentiment_stats(utterances)

    assert [s.utterance_id for s in report.per_utterance] == ["utt-0", "utt-1"]
