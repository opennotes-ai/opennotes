from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
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


class _PromptKeyedFakeAgent:
    def __init__(self, responses: dict[str, _SentimentBatchLLM]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def run(self, prompt: str) -> _FakeRunResult:
        self.calls.append(prompt)
        first_id = _first_prompt_id(prompt)
        return _FakeRunResult(output=self._responses[first_id])


def _first_prompt_id(prompt: str) -> str:
    for line in prompt.splitlines():
        marker = "- utterance_id="
        if line.startswith(marker):
            return line.removeprefix(marker).split(":", 1)[0]
    raise AssertionError(f"prompt did not include an utterance id: {prompt!r}")


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
    monkeypatch.setattr(sentiment_module, "build_agent", lambda *args, **kwargs: fake)

    report = await compute_sentiment_stats(_build_utterances())

    assert len(report.per_utterance) == 6
    assert report.positive_pct == 50.0
    assert report.negative_pct == pytest.approx(33.33, abs=0.01)
    assert report.neutral_pct == pytest.approx(16.67, abs=0.01)
    assert report.mean_valence == pytest.approx((0.9 + 0.8 + 0.7 - 0.8 - 0.7 + 0.0) / 6, abs=1e-4)
    assert {s.utterance_id for s in report.per_utterance} == {"u1", "u2", "u3", "u4", "u5", "u6"}


async def test_compute_sentiment_stats_empty_returns_zeroed_report(monkeypatch):
    fake = _FakeAgent([])
    monkeypatch.setattr(sentiment_module, "build_agent", lambda *args, **kwargs: fake)

    report = await compute_sentiment_stats([])

    assert report.per_utterance == []
    assert report.positive_pct == 0.0
    assert report.negative_pct == 0.0
    assert report.neutral_pct == 0.0
    assert report.mean_valence == 0.0
    assert fake.calls == []


async def test_compute_sentiment_stats_batches_in_tens(monkeypatch):
    utterances = [
        Utterance(utterance_id=f"u{i}", kind="comment", text=f"utterance {i}") for i in range(23)
    ]

    batches = [
        _SentimentBatchLLM(
            scores=[
                _SentimentScoreLLM(utterance_id=f"u{i}", label="neutral", valence=0.0)
                for i in range(start, min(start + 10, 23))
            ]
        )
        for start in range(0, 23, 10)
    ]

    fake = _FakeAgent(batches)
    monkeypatch.setattr(sentiment_module, "build_agent", lambda *args, **kwargs: fake)

    report = await compute_sentiment_stats(utterances)

    assert len(report.per_utterance) == 23
    assert report.neutral_pct == 100.0
    assert len(fake.calls) == 3


async def test_compute_sentiment_stats_enters_vertex_limiter_once_per_batch(
    monkeypatch,
):
    entered = 0

    @asynccontextmanager
    async def _recording_slot(_settings):
        nonlocal entered
        entered += 1
        yield

    utterances = [
        Utterance(utterance_id=f"u{i}", kind="comment", text=f"utterance {i}") for i in range(11)
    ]
    fake = _PromptKeyedFakeAgent(
        {
            "u0": _SentimentBatchLLM(
                scores=[
                    _SentimentScoreLLM(utterance_id=f"u{i}", label="neutral", valence=0.0)
                    for i in range(10)
                ]
            ),
            "u10": _SentimentBatchLLM(
                scores=[_SentimentScoreLLM(utterance_id="u10", label="neutral", valence=0.0)]
            ),
        }
    )

    monkeypatch.setattr(sentiment_module, "build_agent", lambda *args, **kwargs: fake)
    monkeypatch.setattr(sentiment_module, "vertex_slot", _recording_slot, raising=False)

    report = await compute_sentiment_stats(utterances)

    assert len(report.per_utterance) == 11
    assert entered == 2


async def test_compute_sentiment_stats_parallel_batches_preserve_input_order(
    monkeypatch,
):
    utterances = [
        Utterance(utterance_id=f"u{i}", kind="comment", text=f"utterance {i}") for i in range(23)
    ]
    second_batch_started = asyncio.Event()

    class _OutOfOrderFakeAgent:
        calls: list[str]

        def __init__(self) -> None:
            self.calls = []

        async def run(self, prompt: str) -> _FakeRunResult:
            first_id = _first_prompt_id(prompt)
            self.calls.append(first_id)
            if first_id == "u10":
                second_batch_started.set()
            if first_id == "u0":
                await second_batch_started.wait()
            start = int(first_id.removeprefix("u"))
            end = min(start + 10, 23)
            return _FakeRunResult(
                output=_SentimentBatchLLM(
                    scores=[
                        _SentimentScoreLLM(
                            utterance_id=f"u{i}",
                            label="neutral",
                            valence=0.0,
                        )
                        for i in range(start, end)
                    ]
                )
            )

    fake = _OutOfOrderFakeAgent()
    monkeypatch.setattr(sentiment_module, "build_agent", lambda *args, **kwargs: fake)

    report = await asyncio.wait_for(compute_sentiment_stats(utterances), timeout=1.0)

    assert [score.utterance_id for score in report.per_utterance] == [f"u{i}" for i in range(23)]
    assert set(fake.calls) == {"u0", "u10", "u20"}


async def test_compute_sentiment_stats_cancels_sibling_batches_on_failure(
    monkeypatch,
) -> None:
    utterances = [
        Utterance(utterance_id=f"u{i}", kind="comment", text=f"utterance {i}") for i in range(11)
    ]
    second_batch_started = asyncio.Event()
    second_batch_cancelled = asyncio.Event()
    release_second_batch = asyncio.Event()

    class _FailingBatchFakeAgent:
        async def run(self, prompt: str) -> _FakeRunResult:
            first_id = _first_prompt_id(prompt)
            if first_id == "u0":
                await second_batch_started.wait()
                raise RuntimeError("sentiment batch failed")

            second_batch_started.set()
            try:
                await release_second_batch.wait()
            except asyncio.CancelledError:
                second_batch_cancelled.set()
                raise
            return _FakeRunResult(
                output=_SentimentBatchLLM(
                    scores=[_SentimentScoreLLM(utterance_id="u10", label="neutral", valence=0.0)]
                )
            )

    monkeypatch.setattr(
        sentiment_module,
        "build_agent",
        lambda *args, **kwargs: _FailingBatchFakeAgent(),
    )

    with pytest.raises(RuntimeError, match="sentiment batch failed"):
        await compute_sentiment_stats(utterances)

    try:
        await asyncio.wait_for(second_batch_cancelled.wait(), timeout=0.1)
    except TimeoutError as exc:
        release_second_batch.set()
        await asyncio.sleep(0)
        raise AssertionError("sibling sentiment batch was not cancelled") from exc


async def test_compute_sentiment_stats_assigns_fallback_ids(monkeypatch):
    utterances = [
        Utterance(kind="post", text="Great job!"),
        Utterance(kind="comment", text="This is bad."),
    ]
    fake = _FakeAgent(
        [
            _SentimentBatchLLM(
                scores=[
                    _SentimentScoreLLM(utterance_id="utt-0", label="positive", valence=0.9),
                    _SentimentScoreLLM(utterance_id="utt-1", label="negative", valence=-0.9),
                ]
            )
        ]
    )
    monkeypatch.setattr(sentiment_module, "build_agent", lambda *args, **kwargs: fake)

    report = await compute_sentiment_stats(utterances)

    assert [s.utterance_id for s in report.per_utterance] == ["utt-0", "utt-1"]
