"""Tests for ClaimRelevanceService."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.claim_relevance_check.schemas import RelevanceOutcome
from src.claim_relevance_check.service import ClaimRelevanceService
from src.llm_config.providers.base import LLMResponse


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service."""
    return MagicMock()


@pytest.fixture
def mock_settings():
    """Create a mock settings object with all relevance check attributes."""
    s = MagicMock()
    s.RELEVANCE_CHECK_ENABLED = True
    s.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
    s.RELEVANCE_CHECK_MAX_TOKENS = 150
    s.RELEVANCE_CHECK_TIMEOUT = 5.0
    s.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False
    s.INSTANCE_ID = "test"
    return s


class TestCheckRelevance:
    """Tests for ClaimRelevanceService.check_relevance method."""

    @pytest.mark.asyncio
    async def test_relevant_match_returns_relevant(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": True,
                        "reasoning": "The fact check directly addresses the flat earth claim.",
                    }
                ),
                model="gpt-5-mini",
                tokens_used=50,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="The earth is flat and NASA is hiding the truth.",
            matched_content="The claim that the Earth is flat has been thoroughly debunked.",
            matched_source="https://snopes.com/fact-check/flat-earth",
        )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "flat earth" in reasoning.lower()
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_irrelevant_match_returns_not_relevant(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": False,
                        "reasoning": "The fact check is about vaccines, not weather.",
                    }
                ),
                model="gpt-5-mini",
                tokens_used=45,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="It looks like it will rain tomorrow.",
            matched_content="COVID vaccines have been proven safe and effective.",
            matched_source="https://factcheck.org/vaccines",
        )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        assert len(reasoning) > 0

    @pytest.mark.asyncio
    async def test_llm_error_returns_indeterminate(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock(side_effect=Exception("LLM service unavailable"))

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test matched content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "error" in reasoning.lower() or "failed" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_malformed_json_returns_indeterminate(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content="This is not valid JSON",
                model="gpt-5-mini",
                tokens_used=10,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, _reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test matched content",
            matched_source=None,
        )

        assert outcome == RelevanceOutcome.INDETERMINATE

    @pytest.mark.asyncio
    async def test_disabled_feature_flag_returns_relevant(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock()
        mock_settings.RELEVANCE_CHECK_ENABLED = False

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)

        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "disabled" in reasoning.lower()
        mock_llm_service.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_llm_service_returns_indeterminate(self, mock_db, mock_settings) -> None:
        service = ClaimRelevanceService(llm_service=None, settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "not configured" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_none_matched_source_handled(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Content is relevant."}),
                model="gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, _reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test content",
            matched_source=None,
        )

        assert outcome == RelevanceOutcome.RELEVANT
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_returns_indeterminate(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        import asyncio

        async def slow_complete(*args, **kwargs):
            await asyncio.sleep(10)
            return LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = slow_complete
        mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)

        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test matched content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "timed out" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_uses_configured_provider_and_model(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="anthropic/claude-3-haiku",
                tokens_used=20,
                finish_reason="stop",
                provider="anthropic",
            )
        )

        mock_settings.RELEVANCE_CHECK_MODEL = "anthropic/claude-3-haiku"

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)

        await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test content",
            matched_source=None,
        )

        call_args = mock_llm_service.complete.call_args
        assert call_args.kwargs.get("model") == "anthropic/claude-3-haiku"

    @pytest.mark.asyncio
    async def test_prompt_includes_original_message(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        original_msg = "Unique test message content 12345"

        await service.check_relevance(
            db=mock_db,
            original_message=original_msg,
            matched_content="Some matched content",
            matched_source="https://example.com",
        )

        call_args = mock_llm_service.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        all_content = " ".join(m.content for m in messages)
        assert original_msg in all_content


class TestContentFilterRetry:
    """Tests for content filter detection and retry logic."""

    @pytest.mark.asyncio
    async def test_content_filter_triggers_retry(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            return LLMResponse(
                content=json.dumps({"has_claims": True, "reasoning": "Contains claims"}),
                model="gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Potentially sensitive message",
            matched_content="Fact check with sensitive content",
            matched_source="https://example.com",
        )

        assert call_count == 2
        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "fact-check" in reasoning.lower() or "indeterminate" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_both_filtered_returns_content_filtered(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content="",
                model="gpt-5-mini",
                tokens_used=0,
                finish_reason="content_filter",
                provider="openai",
            )
        )

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Problematic user message content",
            matched_content="Normal fact check content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.CONTENT_FILTERED
        assert "message" in reasoning.lower()
        assert "filter" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_retry_no_llm_service_returns_indeterminate(self, mock_db, mock_settings) -> None:
        service = ClaimRelevanceService(llm_service=None, settings=mock_settings)
        outcome, reasoning = await service._retry_without_fact_check(
            db=mock_db,
            original_message="Test message",
            start_time=0.0,
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "not configured" in reasoning.lower()
