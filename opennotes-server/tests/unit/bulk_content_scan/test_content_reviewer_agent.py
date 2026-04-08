"""Unit tests for ContentReviewerAgent and ContentReviewerService.

TDD tests written first (RED phase) before implementation.
Uses pydantic-ai TestModel - no real LLM calls.
"""

from unittest.mock import AsyncMock

import pendulum
import pytest
from pydantic_ai.models.test import TestModel

from src.bulk_content_scan.schemas import (
    ContentItem,
    ContentModerationClassificationResult,
    OpenAIModerationMatch,
    SimilarityMatch,
)


def make_content_item(
    content_id: str = "msg_1",
    content_text: str = "The vaccines cause autism, I read it online",
    author_id: str = "user_1",
    author_username: str | None = "testuser",
    channel_id: str = "ch_1",
    community_server_id: str = "server_1",
) -> ContentItem:
    return ContentItem(
        content_id=content_id,
        platform="discord",
        content_text=content_text,
        author_id=author_id,
        author_username=author_username,
        timestamp=pendulum.now("UTC"),
        channel_id=channel_id,
        community_server_id=community_server_id,
    )


def make_similarity_match(
    score: float = 0.87,
    matched_claim: str = "Vaccines do not cause autism",
    matched_source: str = "https://cdc.gov/vaccines/safety",
) -> SimilarityMatch:
    from uuid import uuid4

    return SimilarityMatch(
        score=score,
        matched_claim=matched_claim,
        matched_source=matched_source,
        fact_check_item_id=uuid4(),
    )


def make_openai_moderation_match(
    max_score: float = 0.85,
    flagged_categories: list[str] | None = None,
) -> OpenAIModerationMatch:
    if flagged_categories is None:
        flagged_categories = ["hate/threatening"]
    categories = dict.fromkeys(flagged_categories, True)
    scores = dict.fromkeys(flagged_categories, max_score)
    return OpenAIModerationMatch(
        max_score=max_score,
        categories=categories,
        scores=scores,
        flagged_categories=flagged_categories,
    )


def make_classification_result(
    confidence: float = 0.85,
    category_labels: dict[str, bool] | None = None,
    recommended_action: str = "review",
    action_tier: str = "tier_2_consensus",
    explanation: str = "Content appears to spread vaccine misinformation",
) -> ContentModerationClassificationResult:
    if category_labels is None:
        category_labels = {"misinformation": True, "hate": False}
    return ContentModerationClassificationResult(
        confidence=confidence,
        category_labels=category_labels,
        recommended_action=recommended_action,
        action_tier=action_tier,
        explanation=explanation,
    )


class TestContentReviewerAgentModule:
    """Tests for the module-level content_reviewer_agent."""

    def test_agent_is_importable(self):
        """content_reviewer_agent should be importable from the module."""
        from src.bulk_content_scan.content_reviewer_agent import content_reviewer_agent

        assert content_reviewer_agent is not None

    def test_agent_has_correct_output_type(self):
        """Agent output_type should be ContentModerationClassificationResult."""
        from src.bulk_content_scan.content_reviewer_agent import content_reviewer_agent

        assert content_reviewer_agent.output_type is ContentModerationClassificationResult

    def test_flashpoint_tool_is_registered(self):
        """detect_flashpoint_tool should be registered on the agent."""
        from src.bulk_content_scan.content_reviewer_agent import content_reviewer_agent

        tool_names = list(content_reviewer_agent._function_toolset.tools.keys())
        assert "detect_flashpoint_tool" in tool_names

    def test_agent_has_instrumentation_enabled(self):
        """Agent should be created with instrument=True."""
        from src.bulk_content_scan.content_reviewer_agent import content_reviewer_agent

        assert content_reviewer_agent.instrument is True

    @pytest.mark.asyncio
    async def test_agent_produces_valid_output_with_test_model(self):
        """Agent should produce a valid ContentModerationClassificationResult with TestModel."""
        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )

        expected = make_classification_result()
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        deps = ContentReviewerDeps(
            flashpoint_service=None,
            context_items=[],
        )

        result = await content_reviewer_agent.run(
            "Classify this content.",
            deps=deps,
            model=test_model,
        )

        output = result.output
        assert isinstance(output, ContentModerationClassificationResult)
        assert 0.0 <= output.confidence <= 1.0
        assert isinstance(output.category_labels, dict)
        assert isinstance(output.explanation, str)


class TestContentReviewerDeps:
    """Tests for ContentReviewerDeps dataclass."""

    def test_deps_is_importable(self):
        """ContentReviewerDeps should be importable."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerDeps

        assert ContentReviewerDeps is not None

    def test_deps_accepts_none_flashpoint_service(self):
        """ContentReviewerDeps should accept None for flashpoint_service."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerDeps

        deps = ContentReviewerDeps(flashpoint_service=None, context_items=[])
        assert deps.flashpoint_service is None

    def test_deps_accepts_context_items_list(self):
        """ContentReviewerDeps should store context_items."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerDeps

        items = [make_content_item("ctx_1"), make_content_item("ctx_2")]
        deps = ContentReviewerDeps(flashpoint_service=None, context_items=items)
        assert len(deps.context_items) == 2


class TestContentReviewerServiceImport:
    """Tests for ContentReviewerService class."""

    def test_service_is_importable(self):
        """ContentReviewerService should be importable."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        assert ContentReviewerService is not None

    def test_service_instantiates_with_defaults(self):
        """ContentReviewerService should instantiate with no arguments."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        assert service is not None

    def test_service_has_classify_method(self):
        """ContentReviewerService should have a classify method."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        assert hasattr(service, "classify")
        assert callable(service.classify)


class TestContentReviewerServiceClassify:
    """Tests for ContentReviewerService.classify()."""

    @pytest.mark.asyncio
    async def test_classify_produces_valid_result_with_test_model(self):
        """classify() should return ContentModerationClassificationResult."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result(confidence=0.9)
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=test_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)

    @pytest.mark.asyncio
    async def test_classify_with_similarity_evidence(self):
        """Similarity match evidence should produce a valid result."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result(
            confidence=0.88,
            category_labels={"misinformation": True},
        )
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()
        similarity_match = make_similarity_match()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[similarity_match],
            model=test_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == 0.88

    @pytest.mark.asyncio
    async def test_classify_with_moderation_evidence(self):
        """OpenAI moderation match evidence should produce a valid result."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result(
            confidence=0.92,
            category_labels={"hate/threatening": True},
            recommended_action="hide",
            action_tier="tier_1_immediate",
        )
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()
        moderation_match = make_openai_moderation_match()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[moderation_match],
            model=test_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == 0.92

    @pytest.mark.asyncio
    async def test_classify_with_no_evidence(self):
        """classify() with empty evidence list should still produce a result."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result(
            confidence=0.5,
            explanation="No external evidence available; direct content analysis only.",
        )
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=test_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0

    @pytest.mark.asyncio
    async def test_classify_timeout_returns_fail_open(self):
        """On timeout, classify() returns fail-open result with confidence=0.0."""
        import asyncio

        from pydantic_ai.messages import ModelResponse
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        async def slow_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            await asyncio.sleep(999)
            raise RuntimeError("Should not reach here")

        slow_function_model = FunctionModel(slow_model)

        service = ContentReviewerService()
        content_item = make_content_item()

        class MockSettings:
            CONTENT_REVIEWER_TIMEOUT = 0.01
            CONTENT_REVIEWER_MODEL = None

        service._settings = MockSettings()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=slow_function_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == 0.0
        assert (
            "timeout" in result.explanation.lower()
            or "classification failed" in result.explanation.lower()
        )

    @pytest.mark.asyncio
    async def test_classify_error_returns_fail_open(self):
        """On unexpected error, classify() returns fail-open result with confidence=0.0."""
        from pydantic_ai.messages import ModelResponse
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        def error_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise RuntimeError("LLM service unavailable")

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=FunctionModel(error_model),
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == 0.0
        assert "classification failed" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_classify_mixed_evidence_types(self):
        """classify() should handle mixed similarity and moderation evidence."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result(
            confidence=0.95,
            category_labels={"misinformation": True, "hate/threatening": True},
            recommended_action="hide",
            action_tier="tier_1_immediate",
            explanation="Both similarity and moderation evidence indicate harmful content",
        )
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()
        similarity_match = make_similarity_match()
        moderation_match = make_openai_moderation_match()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[similarity_match, moderation_match],
            model=test_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_classify_with_context_items(self):
        """classify() should accept and pass context_items to deps."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result()
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()
        context_items = [
            make_content_item("ctx_1", "previous message 1"),
            make_content_item("ctx_2", "previous message 2"),
        ]

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            context_items=context_items,
            model=test_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)


class TestEvidenceFormattingInInstructions:
    """Tests verifying pre-computed evidence appears in agent instructions."""

    @pytest.mark.asyncio
    async def test_similarity_evidence_in_instructions(self):
        """Similarity match claims and scores should appear in the agent instructions."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        content_item = make_content_item()
        similarity_match = make_similarity_match(
            score=0.92,
            matched_claim="Vaccines do not cause autism",
        )

        instructions = service._build_instructions(
            content_item=content_item,
            pre_computed_evidence=[similarity_match],
        )

        assert "Vaccines do not cause autism" in instructions
        assert "0.92" in instructions

    @pytest.mark.asyncio
    async def test_moderation_evidence_in_instructions(self):
        """OpenAI moderation flagged categories should appear in the agent instructions."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        content_item = make_content_item()
        moderation_match = make_openai_moderation_match(
            max_score=0.87,
            flagged_categories=["hate/threatening"],
        )

        instructions = service._build_instructions(
            content_item=content_item,
            pre_computed_evidence=[moderation_match],
        )

        assert "hate/threatening" in instructions
        assert "0.87" in instructions

    def test_empty_evidence_instructions_are_valid(self):
        """Instructions with no evidence should still be a non-empty string."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        content_item = make_content_item()

        instructions = service._build_instructions(
            content_item=content_item,
            pre_computed_evidence=[],
        )

        assert isinstance(instructions, str)
        assert len(instructions) > 0


class TestFlashpointToolIntegration:
    """Tests for flashpoint tool registration and invocation."""

    def test_detect_flashpoint_tool_name(self):
        """detect_flashpoint_tool should have the correct name."""
        from src.bulk_content_scan.content_reviewer_agent import content_reviewer_agent

        tool_names = list(content_reviewer_agent._function_toolset.tools.keys())
        assert "detect_flashpoint_tool" in tool_names

    @pytest.mark.asyncio
    async def test_flashpoint_tool_callable_with_none_service(self):
        """Flashpoint tool should return 'No flashpoint detected' when service is None."""
        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )

        expected = make_classification_result()
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        deps = ContentReviewerDeps(
            flashpoint_service=None,
            context_items=[],
        )

        result = await content_reviewer_agent.run(
            "Classify this content.",
            deps=deps,
            model=test_model,
        )

        assert isinstance(result.output, ContentModerationClassificationResult)

    @pytest.mark.asyncio
    async def test_flashpoint_tool_callable_with_mock_service(self):
        """Flashpoint tool should handle a mock flashpoint service correctly."""
        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )
        from src.bulk_content_scan.schemas import ConversationFlashpointMatch, RiskLevel

        mock_flashpoint_service = AsyncMock()
        mock_flashpoint_service.detect_flashpoint = AsyncMock(
            return_value=ConversationFlashpointMatch(
                derailment_score=80,
                risk_level=RiskLevel.HOSTILE,
                reasoning="Escalating hostility detected",
                context_messages=3,
            )
        )

        expected = make_classification_result(
            confidence=0.9,
            explanation="Flashpoint risk detected alongside content concerns",
        )
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        deps = ContentReviewerDeps(
            flashpoint_service=mock_flashpoint_service,
            context_items=[make_content_item("ctx_1")],
        )

        result = await content_reviewer_agent.run(
            "Classify this content.",
            deps=deps,
            model=test_model,
        )

        assert isinstance(result.output, ContentModerationClassificationResult)
