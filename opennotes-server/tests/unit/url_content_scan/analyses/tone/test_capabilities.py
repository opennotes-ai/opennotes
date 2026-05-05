from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from src.url_content_scan.tone_schemas import FlashpointMatch, RiskLevel
from src.url_content_scan.utterances.schema import Utterance


def _utterance(
    utterance_id: str,
    text: str,
    *,
    author: str | None,
    parent_id: str | None = None,
    timestamp: datetime | None = None,
    kind: str = "comment",
) -> Utterance:
    return Utterance(
        utterance_id=utterance_id,
        kind=kind,
        text=text,
        author=author,
        parent_id=parent_id,
        timestamp=timestamp,
    )


@pytest.mark.asyncio
async def test_run_flashpoint_returns_high_matches_via_shared_service_api() -> None:
    from src.url_content_scan.analyses.tone import run_flashpoint

    class FakeFlashpointService:
        async def detect_flashpoint_for_utterance(
            self,
            utterance: Utterance,
            context: list[Utterance],
            max_context: int | None = None,
            score_threshold: int | None = None,
        ) -> FlashpointMatch | None:
            if utterance.utterance_id != "reply-1":
                return None
            return FlashpointMatch(
                utterance_id=utterance.utterance_id or "",
                derailment_score=81,
                risk_level=RiskLevel.HOSTILE,
                reasoning=f"context={len(context)}",
                context_messages=len(context),
            )

    utterances = [
        _utterance("root-1", "Initial post", author="alice", kind="post"),
        _utterance("reply-1", "You are ignoring the point", author="bob", parent_id="root-1"),
        _utterance("reply-2", "Let's cool this down", author="carol", parent_id="reply-1"),
    ]

    matches = await run_flashpoint(utterances, service=FakeFlashpointService())

    assert [match.utterance_id for match in matches] == ["reply-1"]
    assert matches[0].derailment_score == 81
    assert matches[0].context_messages == 1


@pytest.mark.asyncio
async def test_run_flashpoint_uses_parent_chain_context_for_threaded_replies() -> None:
    from src.url_content_scan.analyses.tone import run_flashpoint

    seen_contexts: dict[str, list[str]] = {}

    class RecordingFlashpointService:
        async def detect_flashpoint_for_utterance(
            self,
            utterance: Utterance,
            context: list[Utterance],
            max_context: int | None = None,
            score_threshold: int | None = None,
        ) -> FlashpointMatch | None:
            seen_contexts[utterance.utterance_id or ""] = [
                item.utterance_id or "" for item in context
            ]
            return None

    utterances = [
        _utterance("root-1", "Launch thread", author="alice", kind="post"),
        _utterance("reply-1", "First reply", author="bob", parent_id="root-1"),
        _utterance("reply-2", "Nested reply", author="carol", parent_id="reply-1"),
        _utterance("reply-3", "Sibling reply", author="drew", parent_id="root-1"),
    ]

    await run_flashpoint(utterances, service=RecordingFlashpointService())

    assert seen_contexts["root-1"] == []
    assert seen_contexts["reply-1"] == ["root-1"]
    assert seen_contexts["reply-2"] == ["root-1", "reply-1"]
    assert seen_contexts["reply-3"] == ["root-1"]


@pytest.mark.asyncio
async def test_run_flashpoint_limits_concurrency_to_eight() -> None:
    from src.url_content_scan.analyses.tone import run_flashpoint

    active = 0
    peak = 0
    lock = asyncio.Lock()

    class SlowFlashpointService:
        async def detect_flashpoint_for_utterance(
            self,
            utterance: Utterance,
            context: list[Utterance],
            max_context: int | None = None,
            score_threshold: int | None = None,
        ) -> FlashpointMatch | None:
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1
            return None

    utterances = [
        _utterance(f"utt-{index}", f"Message {index}", author=f"user-{index % 3}")
        for index in range(24)
    ]

    await run_flashpoint(utterances, service=SlowFlashpointService())

    assert peak <= 8


@pytest.mark.unit
def test_run_scd_reports_non_zero_multi_speaker_stats() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    utterances = [
        _utterance(
            "utt-1",
            "We should ship it this week.",
            author="alice",
            timestamp=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        ),
        _utterance(
            "utt-2",
            "I want a tighter QA pass first.",
            author="bob",
            timestamp=datetime(2026, 5, 4, 12, 2, tzinfo=UTC),
        ),
        _utterance(
            "utt-3",
            "Let's split the release if needed.",
            author="alice",
            timestamp=datetime(2026, 5, 4, 12, 3, tzinfo=UTC),
        ),
        _utterance(
            "utt-4",
            "We can cover docs and rollout today.",
            author="carol",
            timestamp=datetime(2026, 5, 4, 12, 6, tzinfo=UTC),
        ),
    ]

    report = run_scd(utterances)

    assert report.insufficient_conversation is False
    assert "speaker_count=3" in report.summary
    assert "turn_entropy=" in report.summary
    assert "repeat_ratio=" in report.summary
    assert "alice" in report.per_speaker_notes
    assert report.speaker_arcs
    assert "multi_speaker" in report.tone_labels


@pytest.mark.unit
def test_run_scd_tolerates_empty_input() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = run_scd([])

    assert report.insufficient_conversation is True
    assert "speaker_count=0" in report.summary
    assert report.speaker_arcs == []


@pytest.mark.unit
def test_run_scd_tolerates_missing_timestamps() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    utterances = [
        _utterance("utt-1", "Same point", author="alice", timestamp=None),
        _utterance("utt-2", "Same point", author="bob", timestamp=None),
        _utterance("utt-3", "New point", author="alice", timestamp=None),
    ]

    report = run_scd(utterances)

    assert report.insufficient_conversation is False
    assert "timing_coverage=0.00" in report.summary
    assert "repeat_ratio=" in report.summary
