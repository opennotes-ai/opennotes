"""Tests for stream-aware SCD behavior in opennotes-server.

Ports vibecheck-server PR484 / PR487 (audit row 73).  The opennotes-server
`run_scd` is statistics-based (no LLM), so it echoes the upstream
`utterance_stream_type` unchanged and sets `observed_confidence=1.0` when
the type is known, 0.0 when UNKNOWN.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.url_content_scan.tone_schemas import UtteranceStreamType
from src.url_content_scan.utterances.schema import Utterance


def _utterance(
    utterance_id: str,
    text: str,
    *,
    author: str | None,
    timestamp: datetime | None = None,
) -> Utterance:
    return Utterance(
        utterance_id=utterance_id,
        kind="comment",
        text=text,
        author=author,
        timestamp=timestamp,
    )


def _two_speaker_utterances() -> list[Utterance]:
    return [
        _utterance(
            "u-1", "First point.", author="alice", timestamp=datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
        ),
        _utterance(
            "u-2", "Second point.", author="bob", timestamp=datetime(2026, 5, 4, 12, 1, tzinfo=UTC)
        ),
        _utterance(
            "u-3", "Third point.", author="alice", timestamp=datetime(2026, 5, 4, 12, 2, tzinfo=UTC)
        ),
    ]


@pytest.mark.asyncio
async def test_run_scd_returns_unknown_stream_type_by_default() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = await run_scd(_two_speaker_utterances())

    assert report.upstream_stream_type is UtteranceStreamType.UNKNOWN
    assert report.observed_stream_type is UtteranceStreamType.UNKNOWN


@pytest.mark.asyncio
async def test_run_scd_echoes_known_stream_type() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = await run_scd(
        _two_speaker_utterances(),
        utterance_stream_type=UtteranceStreamType.DIALOGUE,
    )

    assert report.upstream_stream_type is UtteranceStreamType.DIALOGUE
    assert report.observed_stream_type is UtteranceStreamType.DIALOGUE


@pytest.mark.asyncio
async def test_run_scd_sets_full_confidence_for_known_stream_type() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = await run_scd(
        _two_speaker_utterances(),
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    )

    assert report.observed_confidence == 1.0


@pytest.mark.asyncio
async def test_run_scd_sets_zero_confidence_for_unknown_stream_type() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = await run_scd(
        _two_speaker_utterances(),
        utterance_stream_type=UtteranceStreamType.UNKNOWN,
    )

    assert report.observed_confidence == 0.0


@pytest.mark.asyncio
async def test_run_scd_has_empty_disagreement_rationale() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = await run_scd(
        _two_speaker_utterances(),
        utterance_stream_type=UtteranceStreamType.DIALOGUE,
    )

    assert report.disagreement_rationale == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stream_type",
    [
        UtteranceStreamType.DIALOGUE,
        UtteranceStreamType.COMMENT_SECTION,
        UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
        UtteranceStreamType.MIXED,
        UtteranceStreamType.UNKNOWN,
    ],
)
async def test_run_scd_echoes_all_stream_types(stream_type: UtteranceStreamType) -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = await run_scd(
        _two_speaker_utterances(),
        utterance_stream_type=stream_type,
    )

    assert report.upstream_stream_type is stream_type
    assert report.observed_stream_type is stream_type


@pytest.mark.asyncio
async def test_run_scd_empty_input_propagates_stream_type() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = await run_scd(
        [],
        utterance_stream_type=UtteranceStreamType.ARTICLE_OR_MONOLOGUE,
    )

    assert report.insufficient_conversation is True
    assert report.upstream_stream_type is UtteranceStreamType.ARTICLE_OR_MONOLOGUE
    assert report.observed_stream_type is UtteranceStreamType.ARTICLE_OR_MONOLOGUE
    assert report.observed_confidence == 1.0


@pytest.mark.asyncio
async def test_run_scd_empty_input_unknown_has_zero_confidence() -> None:
    from src.url_content_scan.analyses.tone import run_scd

    report = await run_scd([], utterance_stream_type=UtteranceStreamType.UNKNOWN)

    assert report.observed_confidence == 0.0
