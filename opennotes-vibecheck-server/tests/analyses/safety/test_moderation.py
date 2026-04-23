"""Unit tests for the harmful-content moderation capability."""

import logging
from unittest.mock import AsyncMock

import pytest

from src.analyses.safety._schemas import HarmfulContentMatch
from src.analyses.safety.moderation import (
    OpenAIModerationTransientError,
    check_content_moderation,
    check_content_moderation_bulk,
)
from src.services.openai_moderation import ModerationResult
from src.utterances.schema import Utterance


def make_utterance(
    utterance_id: str = "utt_1",
    text: str = "test message",
) -> Utterance:
    return Utterance(
        utterance_id=utterance_id,
        kind="post",
        text=text,
        author="alice",
    )


def make_moderation_result(
    flagged: bool = False,
    max_score: float = 0.0,
    categories: dict[str, bool] | None = None,
    scores: dict[str, float] | None = None,
    flagged_categories: list[str] | None = None,
) -> ModerationResult:
    return ModerationResult(
        flagged=flagged,
        categories=categories or {"violence": False, "sexual": False},
        scores=scores or {"violence": 0.01, "sexual": 0.02},
        max_score=max_score,
        flagged_categories=flagged_categories or [],
    )


class TestCheckContentModeration:
    """Tests for the check_content_moderation capability function."""

    def test_function_importable(self):
        from src.analyses.safety.moderation import check_content_moderation

        assert callable(check_content_moderation)

    async def test_returns_none_when_service_not_configured(self):
        utterance = make_utterance()
        result = await check_content_moderation(
            utterance=utterance,
            moderation_service=None,
        )

        assert result is None

    async def test_returns_none_when_not_flagged(self):
        mock_service = AsyncMock()
        mock_service.moderate_text = AsyncMock(return_value=make_moderation_result(flagged=False))

        utterance = make_utterance(text="harmless message")
        result = await check_content_moderation(
            utterance=utterance,
            moderation_service=mock_service,
        )

        assert result is None

    async def test_does_not_expose_multimodal_path(self):
        """POC is text-only — moderate_multimodal must never be called."""
        mock_service = AsyncMock()
        mock_service.moderate_text = AsyncMock(return_value=make_moderation_result(flagged=False))
        mock_service.moderate_multimodal = AsyncMock()

        utterance = make_utterance(text="hello")
        await check_content_moderation(
            utterance=utterance,
            moderation_service=mock_service,
        )

        mock_service.moderate_multimodal.assert_not_called()

    async def test_returns_none_on_exception(self):
        mock_service = AsyncMock()
        mock_service.moderate_text = AsyncMock(side_effect=Exception("API error"))

        utterance = make_utterance()
        result = await check_content_moderation(
            utterance=utterance,
            moderation_service=mock_service,
        )

        assert result is None


class TestModerationResultSchema:
    def test_moderation_result_roundtrip(self):
        result = ModerationResult(
            flagged=True,
            categories={"hate": True},
            scores={"hate": 0.9},
            max_score=0.9,
            flagged_categories=["hate"],
        )
        assert result.flagged is True
        assert result.flagged_categories == ["hate"]


class TestHarmfulContentMatchSchema:
    def test_required_fields(self):
        match = HarmfulContentMatch(
            utterance_id="utt_1",
            max_score=0.5,
            categories={"hate": False},
            scores={"hate": 0.5},
            flagged_categories=[],
            source="openai",
        )
        assert match.utterance_id == "utt_1"
        assert match.max_score == 0.5


class TestOpenAIProducerSourceField:
    async def test_openai_producer_emits_match_with_source_openai(self):
        from unittest.mock import AsyncMock

        from src.analyses.safety.moderation import check_content_moderation_bulk
        from src.services.openai_moderation import ModerationResult

        mock_service = AsyncMock()
        mock_service.moderate_texts = AsyncMock(
            return_value=[
                ModerationResult(
                    flagged=True,
                    categories={"violence": True},
                    scores={"violence": 0.95},
                    max_score=0.95,
                    flagged_categories=["violence"],
                )
            ]
        )
        utterance = make_utterance(utterance_id="utt_src_test", text="harmful text")
        results = await check_content_moderation_bulk([utterance], mock_service)

        assert len(results) == 1
        match = results[0]
        assert match is not None
        assert isinstance(match, HarmfulContentMatch)
        assert match.source == "openai"


class TestBulkModeration:
    async def test_flagged_result_produces_harmful_content_match_with_full_shape(self):
        mock_service = AsyncMock()
        mock_service.moderate_texts = AsyncMock(
            return_value=[
                make_moderation_result(
                    flagged=True,
                    max_score=0.91,
                    categories={"hate": True, "violence": False},
                    scores={"hate": 0.91, "violence": 0.03},
                    flagged_categories=["hate"],
                ),
                make_moderation_result(flagged=False, max_score=0.02),
            ]
        )
        utt_flagged = make_utterance(utterance_id="utt_a", text="hateful content")
        utt_clean = make_utterance(utterance_id="utt_b", text="harmless content")

        results = await check_content_moderation_bulk([utt_flagged, utt_clean], mock_service)

        assert len(results) == 2
        match = results[0]
        assert isinstance(match, HarmfulContentMatch)
        assert match.utterance_id == "utt_a"
        assert match.categories == {"hate": True, "violence": False}
        assert match.scores == {"hate": 0.91, "violence": 0.03}
        assert match.flagged_categories == ["hate"]
        assert match.max_score == pytest.approx(0.91)
        assert results[1] is None

    async def test_single_moderate_texts_call_multimodal_never_invoked(self):
        mock_service = AsyncMock()
        mock_service.moderate_texts = AsyncMock(
            return_value=[
                make_moderation_result(flagged=False),
                make_moderation_result(flagged=False),
                make_moderation_result(flagged=False),
            ]
        )
        mock_service.moderate_multimodal = AsyncMock()

        utterances = [
            make_utterance(utterance_id="utt_1", text="first"),
            make_utterance(utterance_id="utt_2", text="second"),
            make_utterance(utterance_id="utt_3", text="third"),
        ]

        await check_content_moderation_bulk(utterances, mock_service)

        mock_service.moderate_texts.assert_called_once()
        mock_service.moderate_multimodal.assert_not_called()

    async def test_exception_raises_transient_error_with_context_logged(self, caplog):
        mock_service = AsyncMock()
        mock_service.moderate_texts = AsyncMock(side_effect=Exception("API error"))

        utterances = [
            make_utterance(utterance_id="utt_x", text="some text"),
            make_utterance(utterance_id="utt_y", text="more text"),
        ]

        with caplog.at_level(logging.WARNING):
            with pytest.raises(OpenAIModerationTransientError) as exc_info:
                await check_content_moderation_bulk(utterances, mock_service)

        assert "API error" in str(exc_info.value)
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(hasattr(r, "batch_size") and r.batch_size == 2 for r in warning_records)
