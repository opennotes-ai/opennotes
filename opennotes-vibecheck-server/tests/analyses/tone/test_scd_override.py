"""Tests for SCD stream-type override wiring.

This file validates schema plumbing and call wiring only. The model is mocked so
existing tests never hit Vertex/Gemini.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import pytest

from src.analyses.schemas import UtteranceStreamType
from src.analyses.tone import scd as scd_mod
from src.analyses.tone._scd_schemas import SCDReport
from src.config import Settings
from src.utterances import Utterance


def _utt(
    author: str | None,
    text: str,
    kind: Literal["post", "comment", "reply"] = "comment",
) -> Utterance:
    return Utterance(
        utterance_id=f"{author or 'anon'}-{hash(text) & 0xFFFF:04x}",
        kind=kind,
        text=text,
        author=author,
        timestamp=datetime(2026, 5, 6, tzinfo=UTC),
    )


@dataclass
class _FakeRunResult:
    output: SCDReport


@dataclass
class _FakeAgent:
    """Records calls and returns a preset SCDReport when awaited."""

    report: SCDReport
    run_calls: list[str] = field(default_factory=list)

    async def run(self, user_prompt: str) -> _FakeRunResult:
        self.run_calls.append(user_prompt)
        return _FakeRunResult(output=self.report)


@dataclass
class _BuildAgentSpy:
    """Records build_agent invocations and returns a shared fake agent."""

    report: SCDReport
    build_calls: list[dict[str, object]] = field(default_factory=list)
    last_agent: _FakeAgent | None = None

    def __call__(
        self,
        _settings: Settings,
        *,
        output_type=None,
        system_prompt=None,
        name=None,
    ) -> _FakeAgent:
        self.build_calls.append(
            {
                "settings": _settings,
                "output_type": output_type,
                "system_prompt": system_prompt,
                "name": name,
            }
        )
        agent = _FakeAgent(report=self.report)
        self.last_agent = agent
        return agent


@pytest.fixture
def settings() -> Settings:
    return Settings(
        VERTEXAI_PROJECT="test-project",
        VERTEXAI_LOCATION="us-central1",
        VERTEXAI_MODEL="google-vertex:gemini-3.1-pro-preview",
    )


def _build_report(
    observed: UtteranceStreamType,
    discrepancy: bool,
) -> SCDReport:
    return SCDReport(
        narrative="The dialogue is iterative and layered.",
        speaker_arcs=[],
        summary="Two speakers trade perspective and settle into a stable arc.",
        tone_labels=["constructive", "skeptical"],
        per_speaker_notes={"alice": "Held steady through the exchange."},
        insufficient_conversation=False,
        upstream_stream_type=UtteranceStreamType.UNKNOWN,
        observed_stream_type=observed,
        observed_confidence=0.99 if discrepancy else 1.0,
        disagreement_rationale=("Model flagged a stream-shape mismatch." if discrepancy else ""),
    )


def _dialogue_case() -> list[Utterance]:
    return [
        _utt("alice", "I think we should compare those numbers before finalizing."),
        _utt("bob", "I disagree, let's verify the assumptions first."),
        _utt("alice", "Good call; the assumptions changed after the audit."),
        _utt("bob", "Exactly, once we align on that we can move fast."),
    ]


def _comment_section_case() -> list[Utterance]:
    return [
        _utt("alice", "Has anyone else seen this fail-safe warning?"),
        _utt("bob", "Yes, I did and it happened again after deploy."),
        _utt("carol", "What changed in the worker retry window?"),
        _utt("dana", "Same here, no, I think it's a regression."),
        _utt("ely", "Can someone confirm the exact sequence before we reroll?"),
    ]


def _article_case() -> list[Utterance]:
    return [
        _utt(
            "alice",
            "The design has been intentionally minimal by default because older browsers "
            "tend to run out of memory when the parser keeps large ASTs around. "
            "When we avoid nested trees and defer expensive transforms until needed, we "
            "get both lower memory footprint and more predictable latency profiles across "
            "mixed traffic patterns.",
            kind="post",
        ),
        _utt("bob", "Could you share the benchmark comparison?", kind="comment"),
        _utt(
            "alice",
            "Absolutely—I'll paste the charts once the rerun finishes. It should be "
            "clear from the trace logs and the slot timings.",
            kind="comment",
        ),
    ]


@pytest.mark.parametrize(
    (
        "upstream_stream_type",
        "observed_stream_type",
        "expect_nonempty_rationale",
    ),
    [
        (UtteranceStreamType.DIALOGUE, UtteranceStreamType.DIALOGUE, False),
        (UtteranceStreamType.COMMENT_SECTION, UtteranceStreamType.COMMENT_SECTION, False),
        (
            UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
            UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
            False,
        ),
        (UtteranceStreamType.MIXED, UtteranceStreamType.MIXED, False),
        (UtteranceStreamType.UNKNOWN, UtteranceStreamType.UNKNOWN, False),
        (UtteranceStreamType.DIALOGUE, UtteranceStreamType.COMMENT_SECTION, True),
        (
            UtteranceStreamType.COMMENT_SECTION,
            UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
            True,
        ),
    ],
)
async def test_regression_matrix(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    upstream_stream_type: UtteranceStreamType,
    observed_stream_type: UtteranceStreamType,
    expect_nonempty_rationale: bool,
):
    report = _build_report(observed_stream_type, expect_nonempty_rationale)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    result = await scd_mod.analyze_scd(_dialogue_case(), settings, utterance_stream_type=upstream_stream_type)

    assert len(spy.build_calls) == 1
    assert spy.last_agent is not None
    assert len(spy.last_agent.run_calls) == 1
    assert result.upstream_stream_type is upstream_stream_type
    assert result.observed_stream_type is observed_stream_type
    assert bool(result.disagreement_rationale) is expect_nonempty_rationale


async def test_mislabel_dialogue_prior_records_upstream_stream_type(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.COMMENT_SECTION, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    result = await scd_mod.analyze_scd(
        _comment_section_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.DIALOGUE,
    )

    assert result.upstream_stream_type is UtteranceStreamType.DIALOGUE


async def test_mislabel_dialogue_prior_observed_stream_type_corrected(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.COMMENT_SECTION, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    result = await scd_mod.analyze_scd(
        _comment_section_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.DIALOGUE,
    )

    assert result.observed_stream_type is UtteranceStreamType.COMMENT_SECTION


async def test_mislabel_dialogue_prior_reports_disagreement_rationale(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.COMMENT_SECTION, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    result = await scd_mod.analyze_scd(
        _comment_section_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.DIALOGUE,
    )

    assert spy.last_agent is not None
    assert len(spy.last_agent.run_calls) == 1
    assert isinstance(result.disagreement_rationale, str)
    assert len(result.disagreement_rationale.strip()) > 0


async def test_mislabel_dialogue_prior_single_llm_call(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.COMMENT_SECTION, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    await scd_mod.analyze_scd(
        _comment_section_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.DIALOGUE,
    )

    assert len(spy.build_calls) == 1
    call = spy.build_calls[0]
    assert call["output_type"] is SCDReport


async def test_mislabel_comment_section_prior_records_upstream_stream_type(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.ARTICLE_OR_MONOLOGUE, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    result = await scd_mod.analyze_scd(
        _article_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    )

    assert result.upstream_stream_type is UtteranceStreamType.COMMENT_SECTION


async def test_mislabel_comment_section_prior_observed_stream_type_corrected(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.ARTICLE_OR_MONOLOGUE, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    result = await scd_mod.analyze_scd(
        _article_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    )

    assert result.observed_stream_type is UtteranceStreamType.ARTICLE_OR_MONOLOGUE


async def test_mislabel_comment_section_prior_reports_disagreement_rationale(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.ARTICLE_OR_MONOLOGUE, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    result = await scd_mod.analyze_scd(
        _article_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    )

    assert len(result.disagreement_rationale.strip()) > 0


async def test_mislabel_comment_section_prior_single_llm_call(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.ARTICLE_OR_MONOLOGUE, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    await scd_mod.analyze_scd(
        _article_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    )

    assert len(spy.build_calls) == 1
    call = spy.build_calls[0]
    assert call["settings"] is settings


async def test_mislabeled_article_fixture_not_insufficient(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    report = _build_report(UtteranceStreamType.ARTICLE_OR_MONOLOGUE, True)
    spy = _BuildAgentSpy(report=report)
    monkeypatch.setattr(scd_mod, "build_agent", spy)

    result = await scd_mod.analyze_scd(
        _article_case(),
        settings,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    )

    assert result.insufficient_conversation is False
    assert spy.last_agent is not None
    assert len(spy.last_agent.run_calls) == 1
