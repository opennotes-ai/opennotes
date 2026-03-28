"""Tests for ClaimRelevanceService."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from src.claim_relevance_check.schemas import RelevanceCheckResult, RelevanceOutcome
from src.claim_relevance_check.service import ClaimRelevanceService
from src.llm_config.providers.base import LLMResponse


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_llm_service():
    return MagicMock()


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.RELEVANCE_CHECK_ENABLED = True
    s.RELEVANCE_CHECK_MODEL = MagicMock()
    s.RELEVANCE_CHECK_MODEL.to_pydantic_ai.return_value = "openai:gpt-5-mini"
    s.RELEVANCE_CHECK_MAX_TOKENS = 150
    s.RELEVANCE_CHECK_TIMEOUT = 5.0
    s.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False
    s.INSTANCE_ID = "test"
    return s


def _mock_agent_result(output: RelevanceCheckResult) -> MagicMock:
    result = MagicMock()
    result.output = output
    return result


class TestCheckRelevance:
    """Tests for ClaimRelevanceService.check_relevance using Agent(output_type=...)."""

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.Agent")
    async def test_relevant_match_returns_relevant(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        relevance_output = RelevanceCheckResult(
            is_relevant=True,
            reasoning="The fact check directly addresses the flat earth claim.",
        )
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(return_value=_mock_agent_result(relevance_output))

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="The earth is flat and NASA is hiding the truth.",
            matched_content="The claim that the Earth is flat has been thoroughly debunked.",
            matched_source="https://snopes.com/fact-check/flat-earth",
        )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "flat earth" in reasoning.lower()
        mock_agent_cls.assert_called_once()
        agent_instance.run.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.Agent")
    async def test_irrelevant_match_returns_not_relevant(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        relevance_output = RelevanceCheckResult(
            is_relevant=False,
            reasoning="The fact check is about vaccines, not weather.",
        )
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(return_value=_mock_agent_result(relevance_output))

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
    @patch("src.claim_relevance_check.service.Agent")
    async def test_llm_error_returns_indeterminate(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(side_effect=Exception("LLM service unavailable"))

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
    @patch("src.claim_relevance_check.service.Agent")
    async def test_unexpected_model_behavior_triggers_retry(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(
            side_effect=UnexpectedModelBehavior("Content filter or parse failure")
        )

        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"has_claims": True, "reasoning": "Contains claims"}),
                model="gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Potentially sensitive message",
            matched_content="Fact check with sensitive content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "fact-check" in reasoning.lower() or "indeterminate" in reasoning.lower()
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_disabled_feature_flag_returns_relevant(
        self, mock_db, mock_llm_service, mock_settings
    ) -> None:
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
    @patch("src.claim_relevance_check.service.Agent")
    async def test_none_matched_source_handled(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        relevance_output = RelevanceCheckResult(
            is_relevant=True,
            reasoning="Content is relevant.",
        )
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(return_value=_mock_agent_result(relevance_output))

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        outcome, _reasoning = await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test content",
            matched_source=None,
        )

        assert outcome == RelevanceOutcome.RELEVANT
        agent_instance.run.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.Agent")
    async def test_timeout_returns_indeterminate(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        import asyncio

        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            return _mock_agent_result(RelevanceCheckResult(is_relevant=True, reasoning="Test"))

        agent_instance = mock_agent_cls.return_value
        agent_instance.run = slow_run
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
    @patch("src.claim_relevance_check.service.Agent")
    async def test_agent_uses_configured_model(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_settings.RELEVANCE_CHECK_MODEL.to_pydantic_ai.return_value = "anthropic:claude-3-haiku"
        relevance_output = RelevanceCheckResult(is_relevant=True, reasoning="Test")
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(return_value=_mock_agent_result(relevance_output))

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)

        await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test content",
            matched_source=None,
        )

        mock_agent_cls.assert_called_once_with(
            model="anthropic:claude-3-haiku",
            output_type=RelevanceCheckResult,
        )

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.Agent")
    async def test_agent_run_passes_model_settings(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 200
        relevance_output = RelevanceCheckResult(is_relevant=True, reasoning="Test")
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(return_value=_mock_agent_result(relevance_output))

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        await service.check_relevance(
            db=mock_db,
            original_message="Test message",
            matched_content="Test content",
            matched_source=None,
        )

        call_kwargs = agent_instance.run.call_args.kwargs
        ms = call_kwargs["model_settings"]
        assert ms["max_tokens"] == 200
        assert ms["temperature"] == 0.0

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.Agent")
    async def test_agent_receives_user_prompt_and_instructions(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        relevance_output = RelevanceCheckResult(is_relevant=True, reasoning="Test")
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(return_value=_mock_agent_result(relevance_output))

        service = ClaimRelevanceService(mock_llm_service, settings=mock_settings)
        original_msg = "Unique test message content 12345"

        await service.check_relevance(
            db=mock_db,
            original_message=original_msg,
            matched_content="Some matched content",
            matched_source="https://example.com",
        )

        call_args = agent_instance.run.call_args
        user_prompt = (
            call_args.args[0] if call_args.args else call_args.kwargs.get("user_prompt", "")
        )
        instructions = call_args.kwargs.get("instructions", "")
        assert original_msg in user_prompt
        assert len(instructions) > 0


class TestContentFilterRetry:
    """Tests for content filter detection and retry logic."""

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.Agent")
    async def test_unexpected_model_behavior_triggers_retry_then_content_filter(
        self, mock_agent_cls, mock_db, mock_llm_service, mock_settings
    ) -> None:
        agent_instance = mock_agent_cls.return_value
        agent_instance.run = AsyncMock(
            side_effect=UnexpectedModelBehavior("content filter triggered")
        )

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
