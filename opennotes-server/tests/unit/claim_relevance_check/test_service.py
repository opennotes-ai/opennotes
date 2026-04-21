"""Tests for ClaimRelevanceService."""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from src.claim_relevance_check.schemas import RelevanceCheckResult, RelevanceOutcome
from src.claim_relevance_check.service import ClaimRelevanceService, relevance_agent


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.RELEVANCE_CHECK_ENABLED = True
    s.RELEVANCE_CHECK_MODEL = MagicMock()
    s.RELEVANCE_CHECK_MAX_TOKENS = 150
    s.RELEVANCE_CHECK_TIMEOUT = 5.0
    s.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False
    s.INSTANCE_ID = "test"
    return s


class TestCheckRelevance:
    """Tests for ClaimRelevanceService.check_relevance using relevance_agent.override()."""

    @pytest.mark.asyncio
    async def test_relevant_match_returns_relevant(self, mock_settings) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="The fact check directly addresses the flat earth claim.",
            )
        )
        with relevance_agent.override(model=test_model):
            service = ClaimRelevanceService(settings=mock_settings)
            outcome, reasoning = await service.check_relevance(
                original_message="The earth is flat and NASA is hiding the truth.",
                matched_content="The claim that the Earth is flat has been thoroughly debunked.",
                matched_source="https://snopes.com/fact-check/flat-earth",
            )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "flat earth" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_irrelevant_match_returns_not_relevant(self, mock_settings) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=False,
                reasoning="The fact check is about vaccines, not weather.",
            )
        )
        with relevance_agent.override(model=test_model):
            service = ClaimRelevanceService(settings=mock_settings)
            outcome, reasoning = await service.check_relevance(
                original_message="It looks like it will rain tomorrow.",
                matched_content="COVID vaccines have been proven safe and effective.",
                matched_source="https://factcheck.org/vaccines",
            )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        assert len(reasoning) > 0

    @pytest.mark.asyncio
    async def test_llm_error_returns_indeterminate(self, mock_settings) -> None:
        def raise_error(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise Exception("LLM service unavailable")

        with relevance_agent.override(model=FunctionModel(raise_error)):
            service = ClaimRelevanceService(settings=mock_settings)
            outcome, reasoning = await service.check_relevance(
                original_message="Test message",
                matched_content="Test matched content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "error" in reasoning.lower() or "failed" in reasoning.lower()

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.pydantic_model_request")
    async def test_unexpected_model_behavior_triggers_retry(
        self, mock_model_request, mock_settings
    ) -> None:
        def raise_unexpected(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Content filter or parse failure")

        mock_response = MagicMock()
        mock_response.finish_reason = "stop"
        mock_response.text = json.dumps({"has_claims": True, "reasoning": "Contains claims"})
        mock_model_request.return_value = mock_response

        with relevance_agent.override(model=FunctionModel(raise_unexpected)):
            service = ClaimRelevanceService(settings=mock_settings)
            outcome, reasoning = await service.check_relevance(
                original_message="Potentially sensitive message",
                matched_content="Fact check with sensitive content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "fact-check" in reasoning.lower() or "indeterminate" in reasoning.lower()
        mock_model_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_disabled_feature_flag_returns_relevant(self, mock_settings) -> None:
        mock_settings.RELEVANCE_CHECK_ENABLED = False

        service = ClaimRelevanceService(settings=mock_settings)

        outcome, reasoning = await service.check_relevance(
            original_message="Test message",
            matched_content="Test content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "disabled" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_no_model_configured_returns_indeterminate(self, mock_settings) -> None:
        mock_settings.RELEVANCE_CHECK_MODEL = None
        service = ClaimRelevanceService(settings=mock_settings)
        outcome, reasoning = await service.check_relevance(
            original_message="Test message",
            matched_content="Test content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "not configured" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_none_matched_source_handled(self, mock_settings) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="Content is relevant.",
            )
        )
        with relevance_agent.override(model=test_model):
            service = ClaimRelevanceService(settings=mock_settings)
            outcome, _reasoning = await service.check_relevance(
                original_message="Test message",
                matched_content="Test content",
                matched_source=None,
            )

        assert outcome == RelevanceOutcome.RELEVANT

    @pytest.mark.asyncio
    async def test_timeout_returns_indeterminate(self, mock_settings) -> None:
        import asyncio

        async def slow_response(messages: list, agent_info: AgentInfo) -> ModelResponse:
            await asyncio.sleep(10)
            return ModelResponse(parts=[TextPart(content="test")])

        mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1

        with relevance_agent.override(model=FunctionModel(slow_response)):
            service = ClaimRelevanceService(settings=mock_settings)

            outcome, reasoning = await service.check_relevance(
                original_message="Test message",
                matched_content="Test matched content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "timed out" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_agent_uses_configured_model(self, mock_settings) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="Test",
            )
        )
        with relevance_agent.override(model=test_model):
            service = ClaimRelevanceService(settings=mock_settings)
            outcome, _reasoning = await service.check_relevance(
                original_message="Test message",
                matched_content="Test content",
                matched_source=None,
            )

        assert outcome == RelevanceOutcome.RELEVANT
        assert test_model.last_model_request_parameters is not None

    @pytest.mark.asyncio
    async def test_agent_run_passes_model_settings(self, mock_settings) -> None:
        mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 200

        captured_settings: list[dict] = []

        def capture_settings(messages: list, agent_info: AgentInfo) -> ModelResponse:
            if agent_info.model_settings:
                captured_settings.append(
                    {
                        "max_tokens": agent_info.model_settings.get("max_tokens"),
                        "temperature": agent_info.model_settings.get("temperature"),
                    }
                )
            return ModelResponse(
                parts=[
                    TextPart(
                        content=RelevanceCheckResult(
                            is_relevant=True, reasoning="Test"
                        ).model_dump_json()
                    ),
                ]
            )

        with relevance_agent.override(model=FunctionModel(capture_settings)):
            service = ClaimRelevanceService(settings=mock_settings)
            await service.check_relevance(
                original_message="Test message",
                matched_content="Test content",
                matched_source=None,
            )

        assert len(captured_settings) == 1
        assert captured_settings[0]["max_tokens"] == 200
        assert captured_settings[0]["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_agent_receives_user_prompt_and_instructions(self, mock_settings) -> None:
        captured_messages: list = []
        captured_instructions: list = []

        def capture_prompt(messages: list, agent_info: AgentInfo) -> ModelResponse:
            captured_messages.extend(messages)
            if agent_info.instructions:
                captured_instructions.append(agent_info.instructions)
            return ModelResponse(
                parts=[
                    TextPart(
                        content=RelevanceCheckResult(
                            is_relevant=True, reasoning="Test"
                        ).model_dump_json()
                    ),
                ]
            )

        service = ClaimRelevanceService(settings=mock_settings)
        original_msg = "Unique test message content 12345"

        with relevance_agent.override(model=FunctionModel(capture_prompt)):
            await service.check_relevance(
                original_message=original_msg,
                matched_content="Some matched content",
                matched_source="https://example.com",
            )

        user_prompt_parts = []
        for msg in captured_messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part, "content"):
                        user_prompt_parts.append(part.content)
        full_prompt = " ".join(user_prompt_parts)
        assert original_msg in full_prompt
        assert len(captured_instructions) > 0


class TestContentFilterRetry:
    """Tests for content filter detection and retry logic."""

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.pydantic_model_request")
    async def test_unexpected_model_behavior_triggers_retry_then_content_filter(
        self, mock_model_request, mock_settings
    ) -> None:
        def raise_unexpected(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("content filter triggered")

        mock_response = MagicMock()
        mock_response.finish_reason = "content_filter"
        mock_response.text = ""
        mock_model_request.return_value = mock_response

        with relevance_agent.override(model=FunctionModel(raise_unexpected)):
            service = ClaimRelevanceService(settings=mock_settings)
            outcome, reasoning = await service.check_relevance(
                original_message="Problematic user message content",
                matched_content="Normal fact check content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.CONTENT_FILTERED
        assert "message" in reasoning.lower()
        assert "filter" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_retry_no_model_configured_returns_indeterminate(self, mock_settings) -> None:
        mock_settings.RELEVANCE_CHECK_MODEL = None
        service = ClaimRelevanceService(settings=mock_settings)
        outcome, reasoning = await service._retry_without_fact_check(
            original_message="Test message",
            start_time=0.0,
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "not configured" in reasoning.lower()
