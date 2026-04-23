"""TDD tests for the safety moderation slot orchestrator.

Covers TASK-1474.12 ACs 2-4 (parallel OpenAI + GCP, partial-success,
both-fail raises ModerationSlotError).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.analyses.safety._schemas import HarmfulContentMatch
from src.utterances.schema import Utterance


def make_utterance(utterance_id: str = "utt_1", text: str = "some text") -> Utterance:
    return Utterance(utterance_id=utterance_id, kind="post", text=text, author="alice")


def make_match(utterance_id: str = "utt_1", source: str = "openai") -> HarmfulContentMatch:
    return HarmfulContentMatch(
        utterance_id=utterance_id,
        utterance_text="some text",
        max_score=0.9,
        categories={"violence": True},
        scores={"violence": 0.9},
        flagged_categories=["violence"],
        source=source,  # type: ignore[arg-type]
    )


class TestBothProvidersSucceed:
    async def test_both_providers_succeed_returns_combined_matches(self):
        from src.analyses.safety.moderation_slot import run_safety_moderation

        openai_match = make_match(utterance_id="utt_1", source="openai")
        gcp_match = make_match(utterance_id="utt_1", source="gcp")

        payload = type("Payload", (), {"utterances": [make_utterance()]})()

        with (
            patch(
                "src.analyses.safety.moderation_slot.check_content_moderation_bulk",
                new=AsyncMock(return_value=[openai_match]),
            ),
            patch(
                "src.analyses.safety.moderation_slot.moderate_texts_gcp",
                new=AsyncMock(return_value=[gcp_match]),
            ),
        ):
            result = await run_safety_moderation(
                pool=None,
                job_id=uuid4(),
                task_attempt=uuid4(),
                payload=payload,
                settings=None,
            )

        matches = result["harmful_content_matches"]
        assert len(matches) == 2
        sources = {m["source"] for m in matches}
        assert sources == {"openai", "gcp"}

    async def test_matches_include_the_flagged_utterance_text(self):
        from src.analyses.safety.moderation_slot import run_safety_moderation

        openai_match = make_match(utterance_id="utt_1", source="openai")
        payload = type(
            "Payload",
            (),
            {
                "utterances": [
                    make_utterance(
                        utterance_id="utt_1",
                        text="This is the exact harmful sentence.",
                    )
                ]
            },
        )()

        with (
            patch(
                "src.analyses.safety.moderation_slot.check_content_moderation_bulk",
                new=AsyncMock(return_value=[openai_match]),
            ),
            patch(
                "src.analyses.safety.moderation_slot.moderate_texts_gcp",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await run_safety_moderation(
                pool=None,
                job_id=uuid4(),
                task_attempt=uuid4(),
                payload=payload,
                settings=None,
            )

        assert result["harmful_content_matches"] == [
            {
                "utterance_id": "utt_1",
                "utterance_text": "This is the exact harmful sentence.",
                "max_score": 0.9,
                "categories": {"violence": True},
                "scores": {"violence": 0.9},
                "flagged_categories": ["violence"],
                "source": "openai",
            }
        ]


class TestOnlyOpenAISucceeds:
    async def test_only_openai_succeeds_gcp_raises(self):
        from src.analyses.safety.moderation_slot import run_safety_moderation

        openai_match = make_match(utterance_id="utt_1", source="openai")

        payload = type("Payload", (), {"utterances": [make_utterance()]})()

        with (
            patch(
                "src.analyses.safety.moderation_slot.check_content_moderation_bulk",
                new=AsyncMock(return_value=[openai_match]),
            ),
            patch(
                "src.analyses.safety.moderation_slot.moderate_texts_gcp",
                new=AsyncMock(side_effect=RuntimeError("gcp down")),
            ),
        ):
            result = await run_safety_moderation(
                pool=None,
                job_id=uuid4(),
                task_attempt=uuid4(),
                payload=payload,
                settings=None,
            )

        matches = result["harmful_content_matches"]
        assert len(matches) == 1
        assert matches[0]["source"] == "openai"


class TestOnlyGCPSucceeds:
    async def test_only_gcp_succeeds_openai_raises(self):
        from src.analyses.safety.moderation_slot import run_safety_moderation

        gcp_match = make_match(utterance_id="utt_1", source="gcp")

        payload = type("Payload", (), {"utterances": [make_utterance()]})()

        with (
            patch(
                "src.analyses.safety.moderation_slot.check_content_moderation_bulk",
                new=AsyncMock(side_effect=RuntimeError("openai down")),
            ),
            patch(
                "src.analyses.safety.moderation_slot.moderate_texts_gcp",
                new=AsyncMock(return_value=[gcp_match]),
            ),
        ):
            result = await run_safety_moderation(
                pool=None,
                job_id=uuid4(),
                task_attempt=uuid4(),
                payload=payload,
                settings=None,
            )

        matches = result["harmful_content_matches"]
        assert len(matches) == 1
        assert matches[0]["source"] == "gcp"


class TestBothProvidersFail:
    async def test_both_providers_raise_raises_moderation_slot_error(self):
        from src.analyses.safety.moderation_slot import (
            ModerationSlotError,
            run_safety_moderation,
        )

        payload = type("Payload", (), {"utterances": [make_utterance()]})()

        with (
            patch(
                "src.analyses.safety.moderation_slot.check_content_moderation_bulk",
                new=AsyncMock(side_effect=RuntimeError("openai down")),
            ),
            patch(
                "src.analyses.safety.moderation_slot.moderate_texts_gcp",
                new=AsyncMock(side_effect=RuntimeError("gcp down")),
            ),
            pytest.raises(ModerationSlotError) as exc_info,
        ):
            await run_safety_moderation(
                pool=None,
                job_id=uuid4(),
                task_attempt=uuid4(),
                payload=payload,
                settings=None,
            )

        msg = str(exc_info.value)
        assert "openai down" in msg
        assert "gcp down" in msg


class TestEmptyUtterances:
    async def test_empty_utterances_returns_empty_matches_no_http(self):
        from src.analyses.safety.moderation_slot import run_safety_moderation

        payload = type("Payload", (), {"utterances": []})()

        call_count = 0

        async def spy_openai(utterances, moderation_service=None):
            nonlocal call_count
            call_count += 1
            return []

        async def spy_gcp(utterances, *, httpx_client, **kwargs):
            nonlocal call_count
            call_count += 1
            return []

        with (
            patch(
                "src.analyses.safety.moderation_slot.check_content_moderation_bulk",
                new=spy_openai,
            ),
            patch(
                "src.analyses.safety.moderation_slot.moderate_texts_gcp",
                new=spy_gcp,
            ),
        ):
            result = await run_safety_moderation(
                pool=None,
                job_id=uuid4(),
                task_attempt=uuid4(),
                payload=payload,
                settings=None,
            )

        assert result["harmful_content_matches"] == []
