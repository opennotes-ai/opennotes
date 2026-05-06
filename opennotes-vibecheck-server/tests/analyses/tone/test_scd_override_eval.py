"""Opt-in eval-style coverage for adaptive SCD stream-type override behavior."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Literal

import pytest

from src.analyses.schemas import UtteranceStreamType
from src.analyses.tone import scd as scd_mod
from src.config import Settings
from src.utterances import Utterance


def _utt(author: str | None, text: str, kind: Literal["post", "comment", "reply"] = "comment") -> Utterance:
    return Utterance(
        utterance_id=f"{author or 'anon'}-{hash(text) & 0xFFFF:04x}",
        kind=kind,
        text=text,
        author=author,
        timestamp=datetime(2026, 5, 6, tzinfo=UTC),
    )


pytestmark = pytest.mark.skipif(
    os.getenv("VIBECHECK_RUN_EVALS") != "1",
    reason="Set VIBECHECK_RUN_EVALS=1 to run live Vertex-backed SCD override evals.",
)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.mark.asyncio
@pytest.mark.eval
async def test_comment_section_for_comment_prior_disagrees_from_dialogue_prior(settings: Settings) -> None:
    utterances = [
        _utt("reader1", "Did anyone else notice this update in the release notes?"),
        _utt("reader2", "I did, but I found the API docs a bit out of date still."),
        _utt("reader3", "My team saw the same and filed a follow-up issue."),
        _utt("reader4", "There's no ETA yet, so we wait until engineering posts one."),
        _utt("reader5", "Good call, I pinged support but no one answered."),
    ]

    report = await scd_mod.analyze_scd(
        utterances,
        settings,
        utterance_stream_type=UtteranceStreamType.DIALOGUE,
    )

    assert report.upstream_stream_type is UtteranceStreamType.DIALOGUE
    assert report.observed_stream_type is UtteranceStreamType.COMMENT_SECTION
    assert report.disagreement_rationale.strip()


@pytest.mark.asyncio
@pytest.mark.eval
async def test_article_or_monologue_for_comment_section_prior_disagrees_from_article_prior(settings: Settings) -> None:
    utterances = [
        _utt(
            "author",
            "Our company posted a 2,000-line design memo after the migration. "
            "The document argues for staged rollouts, stronger guardrails, and a "
            "single source of truth for incident response. It includes a timeline "
            "and clear ownership boundaries for each subsystem.",
            kind="post",
        ),
        _utt(
            "author",
            "In follow-up, we decided to pause auto-promotions for one week while "
            "we run additional smoke tests.",
            kind="comment",
        ),
        _utt(
            "reviewer",
            "This is useful context; please confirm whether the rollback plan "
            "contains a dry-run window, because that was missing before.",
            kind="comment",
        ),
    ]

    report = await scd_mod.analyze_scd(
        utterances,
        settings,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
    )

    assert report.upstream_stream_type is UtteranceStreamType.COMMENT_SECTION
    assert report.observed_stream_type is UtteranceStreamType.ARTICLE_OR_MONOLOGUE
    assert report.disagreement_rationale.strip()
