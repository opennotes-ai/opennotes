"""Tests for `analyze_scd`.

We stub the LLM by monkey-patching `build_agent` inside `scd` so tests never
hit Vertex AI. The fake agent records its inputs and returns a predetermined
`SCDReport`, letting us assert both the LLM-path behavior AND that the
single-speaker short-circuit avoids the LLM entirely.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import pytest
from pydantic import ValidationError

from src.analyses.schemas import UtteranceStreamType
from src.analyses.tone import scd as scd_mod
from src.analyses.tone._scd_schemas import SCDReport, SpeakerArc
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
        timestamp=datetime(2026, 4, 21, tzinfo=UTC),
    )


@dataclass
class _FakeRunResult:
    output: SCDReport


@dataclass
class _FakeAgent:
    """Records calls; returns a preset SCDReport when awaited."""

    report: SCDReport
    run_calls: list[str] = field(default_factory=list)

    async def run(self, user_prompt: str) -> _FakeRunResult:
        self.run_calls.append(user_prompt)
        return _FakeRunResult(output=self.report)


@dataclass
class _BuildAgentSpy:
    """Records that build_agent was invoked with the expected arguments."""

    report: SCDReport
    build_calls: list[dict[str, object]] = field(default_factory=list)
    last_agent: _FakeAgent | None = None

    def __call__(self, settings, *, output_type=None, system_prompt=None, name=None):
        self.build_calls.append(
            {
                "settings": settings,
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


@pytest.fixture
def fake_report() -> SCDReport:
    return SCDReport(
        narrative=(
            "Two voices come in at different angles and circle each other for "
            "a few turns. One keeps poking at the framing; the other holds "
            "the line at first, then gives a little ground on a narrow point. "
            "By the end the heat has come off and they land somewhere "
            "uneasy but civil."
        ),
        speaker_arcs=[
            SpeakerArc(
                speaker="alice",
                note="Stays skeptical throughout, mostly through pointed questions.",
                utterance_id_range=[1, 3],
            ),
            SpeakerArc(
                speaker="bob",
                note="Starts defensive and softens into a narrow concession.",
                utterance_id_range=None,
            ),
        ],
        summary=(
            "Two speakers exchange disagreement with occasional rhetorical "
            "questions, gradually moving toward a reluctant concession."
        ),
        tone_labels=["disagreement", "rhetorical", "conciliatory"],
        per_speaker_notes={
            "alice": "Persistently skeptical; relies on rhetorical questions.",
            "bob": "Defensive initially, then concedes on a narrow point.",
        },
        insufficient_conversation=False,
    )


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch, fake_report: SCDReport) -> _BuildAgentSpy:
    s = _BuildAgentSpy(report=fake_report)
    monkeypatch.setattr(scd_mod, "build_agent", s)
    return s


class TestAnalyzeScdMultiSpeaker:
    async def test_returns_llm_report_with_per_speaker_notes(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
        fake_report: SCDReport,
    ):
        utterances = [
            _utt("alice", "I don't think that's quite right."),
            _utt("bob", "Why would you even say that?"),
            _utt("alice", "Because the premise is shaky."),
            _utt("bob", "Fine — maybe on that one point."),
        ]

        report = await scd_mod.analyze_scd(utterances, settings)

        assert report == fake_report
        assert report.per_speaker_notes
        assert set(report.per_speaker_notes.keys()) == {"alice", "bob"}
        assert report.insufficient_conversation is False

    async def test_multi_speaker_run_populates_new_shape(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        utterances = [
            _utt("alice", "I don't think that's quite right."),
            _utt("bob", "Why would you even say that?"),
            _utt("alice", "Because the premise is shaky."),
            _utt("bob", "Fine — maybe on that one point."),
        ]

        report = await scd_mod.analyze_scd(utterances, settings)

        assert report.narrative.strip()
        assert report.speaker_arcs
        assert report.summary.strip()
        assert report.tone_labels
        assert report.per_speaker_notes

    async def test_multi_speaker_run_speaker_arcs_have_correct_shape(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        utterances = [
            _utt("alice", "I don't think that's quite right."),
            _utt("bob", "Why would you even say that?"),
            _utt("alice", "Because the premise is shaky."),
            _utt("bob", "Fine — maybe on that one point."),
        ]

        report = await scd_mod.analyze_scd(utterances, settings)

        assert report.speaker_arcs
        for arc in report.speaker_arcs:
            assert isinstance(arc.speaker, str)
            assert arc.speaker
            assert isinstance(arc.note, str)
            assert arc.note
            if arc.utterance_id_range is not None:
                assert isinstance(arc.utterance_id_range, list)
                assert len(arc.utterance_id_range) == 2
                assert all(isinstance(i, int) for i in arc.utterance_id_range)

    async def test_builds_agent_with_prompt_and_output_type(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        utterances = [
            _utt("alice", "I disagree with you."),
            _utt("bob", "That's a stretch."),
        ]

        await scd_mod.analyze_scd(utterances, settings)

        assert len(spy.build_calls) == 1
        call = spy.build_calls[0]
        assert call["output_type"] is SCDReport
        system_prompt = call["system_prompt"]
        assert isinstance(system_prompt, str)
        assert "Trajectory Summary" in system_prompt
        assert call["settings"] is settings

    async def test_formats_utterances_as_author_text_lines(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        utterances = [
            _utt("alice", "First line."),
            _utt("bob", "Second line."),
        ]

        await scd_mod.analyze_scd(utterances, settings)

        assert spy.last_agent is not None
        assert spy.last_agent.run_calls == [
            "Upstream-claimed utterance_stream_type: unknown\n"
            "Treat this as advisory. Classify the observed stream yourself in the output.\n\n"
            "[1] alice: First line.\n[2] bob: Second line."
        ]

    async def test_forwards_advisory_stream_type_and_records_upstream(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        utterances = [
            _utt("alice", "First line."),
            _utt("bob", "Second line."),
        ]

        report = await scd_mod.analyze_scd(
            utterances,
            settings,
            utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
        )

        assert report.upstream_stream_type is UtteranceStreamType.COMMENT_SECTION
        assert spy.last_agent is not None
        assert (
            "Upstream-claimed utterance_stream_type: comment_section"
            in spy.last_agent.run_calls[0]
        )

    async def test_missing_author_gets_stable_speaker_label(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        utterances = [
            _utt("alice", "Here is a claim."),
            _utt("bob", "I disagree with the framing."),
            _utt(None, "Anonymous aside."),
        ]

        await scd_mod.analyze_scd(utterances, settings)

        assert spy.last_agent is not None
        formatted = spy.last_agent.run_calls[0]
        assert "[1] alice: Here is a claim." in formatted
        assert "[2] bob: I disagree with the framing." in formatted
        assert "[3] Speaker1: Anonymous aside." in formatted


class TestAnalyzeScdInsufficientConversation:
    async def test_zero_utterances_short_circuits(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        report = await scd_mod.analyze_scd([], settings)

        assert report.insufficient_conversation is True
        assert report.per_speaker_notes == {}
        assert report.tone_labels == []
        assert report.narrative == ""
        assert report.speaker_arcs == []
        assert spy.build_calls == []
        assert spy.last_agent is None

    async def test_single_utterance_short_circuits(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        utterances = [_utt("alice", "Standalone blog post with no replies.", kind="post")]

        report = await scd_mod.analyze_scd(utterances, settings)

        assert report.insufficient_conversation is True
        assert report.summary  # not empty — has a placeholder explanation
        assert report.narrative == ""
        assert report.speaker_arcs == []
        assert spy.build_calls == []
        assert spy.last_agent is None

    async def test_single_author_multi_utterance_short_circuits(
        self,
        spy: _BuildAgentSpy,
        settings: Settings,
    ):
        utterances = [
            _utt("alice", "First self-reply."),
            _utt("alice", "Second self-reply."),
        ]

        report = await scd_mod.analyze_scd(utterances, settings)

        assert report.insufficient_conversation is True
        assert report.narrative == ""
        assert report.speaker_arcs == []
        assert spy.build_calls == []
        assert spy.last_agent is None


class TestPromptVendored:
    def test_scd_prompt_file_is_loaded_and_non_empty(self):
        scd_mod._load_scd_prompt.cache_clear()
        prompt = scd_mod._load_scd_prompt()
        assert prompt.strip()
        assert "Trajectory Summary" in prompt
        assert "narrative" in prompt
        assert "speaker_arcs" in prompt
        assert "FEELS" in prompt
        assert "monologue" in prompt
        assert "many-voiced" in prompt
        assert "brigaded" in prompt
        assert "coordinated" in prompt
        assert "promotional" in prompt
        assert "critical" in prompt
        assert "analytical" in prompt
        assert "Goffman 1981 participation framework" in prompt
        assert "Bell 1984 audience design" in prompt
        assert "Biber & Finegan 1989 evaluative stance" in prompt


class TestSCDReportSchemaShape:
    def test_speaker_arc_with_range(self):
        arc = SpeakerArc(speaker="alice", note="x", utterance_id_range=[3, 7])
        round_tripped = SpeakerArc.model_validate(arc.model_dump())
        assert round_tripped.speaker == "alice"
        assert round_tripped.note == "x"
        assert round_tripped.utterance_id_range == [3, 7]

    def test_speaker_arc_without_range_defaults_to_none(self):
        arc = SpeakerArc(speaker="alice", note="x")
        assert arc.utterance_id_range is None

    def test_scd_report_new_fields_default_empty(self):
        report = SCDReport(summary="placeholder", insufficient_conversation=True)
        assert report.narrative == ""
        assert report.speaker_arcs == []

    def test_speaker_arc_rejects_wrong_length(self):
        with pytest.raises(ValidationError):
            SpeakerArc(speaker="x", note="y", utterance_id_range=[3])

    def test_speaker_arc_rejects_start_after_end(self):
        with pytest.raises(ValidationError):
            SpeakerArc(speaker="x", note="y", utterance_id_range=[7, 3])

    def test_speaker_arc_rejects_zero_or_negative_index(self):
        with pytest.raises(ValidationError):
            SpeakerArc(speaker="x", note="y", utterance_id_range=[0, 5])
