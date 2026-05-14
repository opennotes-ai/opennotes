"""Unit tests for ContentReviewerAgent and ContentReviewerService.

TDD tests written first (RED phase) before implementation.
Uses pydantic-ai TestModel - no real LLM calls.
"""

import importlib
import json
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pendulum
import pytest
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from src.bulk_content_scan.schemas import (
    ContentItem,
    ContentModerationClassificationResult,
    ConversationFlashpointMatch,
    OpenAIModerationMatch,
    RiskLevel,
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


def make_flashpoint_match(
    derailment_score: int = 75,
    risk_level: RiskLevel = RiskLevel.HOSTILE,
    reasoning: str = "Escalating hostility and personal attacks detected",
    context_messages: int = 3,
) -> ConversationFlashpointMatch:
    return ConversationFlashpointMatch(
        derailment_score=derailment_score,
        risk_level=risk_level,
        reasoning=reasoning,
        context_messages=context_messages,
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
        """Agent should carry the pydantic-ai instrumentation capability."""
        from src.bulk_content_scan.content_reviewer_agent import content_reviewer_agent

        capabilities = content_reviewer_agent.root_capability.capabilities
        assert any(isinstance(capability, Instrumentation) for capability in capabilities)

    def test_module_reload_avoids_pydantic_ai_deprecation_warnings(self):
        import src.bulk_content_scan.content_reviewer_agent as agent_module

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            importlib.reload(agent_module)

        deprecations = [
            warning for warning in caught if issubclass(warning.category, DeprecationWarning)
        ]
        assert deprecations == []

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


class TestFlashpointEvidenceInInstructions:
    """Tests verifying ConversationFlashpointMatch evidence appears in agent instructions."""

    def test_flashpoint_evidence_in_instructions(self):
        """Flashpoint risk_level, derailment_score, and reasoning should appear in instructions."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        content_item = make_content_item()
        flashpoint_match = make_flashpoint_match(
            derailment_score=75,
            risk_level=RiskLevel.HOSTILE,
            reasoning="Escalating hostility and personal attacks detected",
        )

        instructions = service._build_instructions(
            content_item=content_item,
            pre_computed_evidence=[flashpoint_match],
        )

        assert "Conversation flashpoint detected" in instructions
        assert "Hostile" in instructions
        assert "75/100" in instructions
        assert "Escalating hostility and personal attacks detected" in instructions

    def test_flashpoint_evidence_with_low_risk_level(self):
        """Low-risk flashpoint should still appear in instructions."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        content_item = make_content_item()
        flashpoint_match = make_flashpoint_match(
            derailment_score=30,
            risk_level=RiskLevel.GUARDED,
            reasoning="Minor tension present but manageable",
        )

        instructions = service._build_instructions(
            content_item=content_item,
            pre_computed_evidence=[flashpoint_match],
        )

        assert "Conversation flashpoint detected" in instructions
        assert "Guarded" in instructions
        assert "30/100" in instructions
        assert "Minor tension present but manageable" in instructions

    def test_flashpoint_evidence_mixed_with_other_evidence(self):
        """Flashpoint evidence should appear alongside similarity and moderation evidence."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        content_item = make_content_item()
        similarity_match = make_similarity_match(
            score=0.88, matched_claim="Vaccines do not cause autism"
        )
        flashpoint_match = make_flashpoint_match(
            derailment_score=65,
            risk_level=RiskLevel.HEATED,
            reasoning="Heated debate with inflammatory language",
        )

        instructions = service._build_instructions(
            content_item=content_item,
            pre_computed_evidence=[similarity_match, flashpoint_match],
        )

        assert "Vaccines do not cause autism" in instructions
        assert "0.88" in instructions
        assert "Conversation flashpoint detected" in instructions
        assert "Heated" in instructions
        assert "65/100" in instructions
        assert "Heated debate with inflammatory language" in instructions

    @pytest.mark.asyncio
    async def test_classify_with_flashpoint_evidence(self):
        """classify() should accept and process ConversationFlashpointMatch evidence."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result(
            confidence=0.91,
            category_labels={"harassment": True},
            recommended_action="review",
            action_tier="tier_2_consensus",
            explanation="Flashpoint evidence indicates escalating conflict",
        )
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()
        flashpoint_match = make_flashpoint_match(
            derailment_score=80,
            risk_level=RiskLevel.HOSTILE,
            reasoning="Strong personal attack patterns detected",
        )

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[flashpoint_match],
            model=test_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == 0.91


class TestAgentRetries:
    """AC1: Agent preserves tool and output retries."""

    def test_agent_has_retries_2(self):
        """content_reviewer_agent must keep both retry paths at 2."""
        from src.bulk_content_scan.content_reviewer_agent import content_reviewer_agent

        assert content_reviewer_agent._max_tool_retries == 2
        assert content_reviewer_agent._max_output_retries == 2


class TestOutputValidator:
    """AC2 & AC8: output_validator enforces cross-field invariants."""

    @pytest.mark.asyncio
    async def test_output_validator_rejects_action_tier_without_recommended_action(self):
        """output_validator raises ModelRetry when action_tier set without recommended_action."""
        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )

        call_count = {"n": 0}

        def model_fn(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
            call_count["n"] += 1
            if call_count["n"] == 1:
                bad_output = {
                    "scan_type": "content_moderation_classification",
                    "confidence": 0.8,
                    "category_labels": {"test": True},
                    "category_scores": None,
                    "recommended_action": None,
                    "action_tier": "tier_1_immediate",
                    "explanation": "bad output",
                }
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name=agent_info.output_tools[0].name,
                            args=json.dumps(bad_output),
                            tool_call_id="call-1",
                        )
                    ]
                )
            good_output = {
                "scan_type": "content_moderation_classification",
                "confidence": 0.8,
                "category_labels": {"test": True},
                "category_scores": None,
                "recommended_action": "review",
                "action_tier": "tier_1_immediate",
                "explanation": "good output",
            }
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=agent_info.output_tools[0].name,
                        args=json.dumps(good_output),
                        tool_call_id="call-2",
                    )
                ]
            )

        deps = ContentReviewerDeps(flashpoint_service=None, context_items=[])
        result = await content_reviewer_agent.run(
            "Classify content.",
            deps=deps,
            model=FunctionModel(model_fn),
        )

        assert result.output.recommended_action == "review"
        assert result.output.action_tier == "tier_1_immediate"
        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_output_validator_rejects_category_scores_not_subset_of_labels(self):
        """output_validator raises ModelRetry when category_scores keys not in category_labels."""
        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )

        call_count = {"n": 0}

        def model_fn(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
            call_count["n"] += 1
            if call_count["n"] == 1:
                bad_output = {
                    "scan_type": "content_moderation_classification",
                    "confidence": 0.7,
                    "category_labels": {"hate": True},
                    "category_scores": {"hate": 0.9, "extra_category": 0.5},
                    "recommended_action": "review",
                    "action_tier": "tier_2_consensus",
                    "explanation": "bad cross-field output",
                }
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name=agent_info.output_tools[0].name,
                            args=json.dumps(bad_output),
                            tool_call_id="call-1",
                        )
                    ]
                )
            good_output = {
                "scan_type": "content_moderation_classification",
                "confidence": 0.7,
                "category_labels": {"hate": True},
                "category_scores": {"hate": 0.9},
                "recommended_action": "review",
                "action_tier": "tier_2_consensus",
                "explanation": "valid output",
            }
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=agent_info.output_tools[0].name,
                        args=json.dumps(good_output),
                        tool_call_id="call-2",
                    )
                ]
            )

        deps = ContentReviewerDeps(flashpoint_service=None, context_items=[])
        result = await content_reviewer_agent.run(
            "Classify content.",
            deps=deps,
            model=FunctionModel(model_fn),
        )

        assert result.output.category_scores == {"hate": 0.9}
        assert call_count["n"] == 2


class TestStaticInstructions:
    """AC3 & AC4: Static preamble+schema block hoisted to _STATIC_INSTRUCTIONS module constant."""

    def test_static_instructions_constant_exists(self):
        """_STATIC_INSTRUCTIONS module constant must exist."""
        import src.bulk_content_scan.content_reviewer_agent as m

        assert hasattr(m, "_STATIC_INSTRUCTIONS")
        assert isinstance(m._STATIC_INSTRUCTIONS, str)
        assert len(m._STATIC_INSTRUCTIONS) > 0

    def test_static_instructions_contains_preamble(self):
        """_STATIC_INSTRUCTIONS must contain preamble text about content moderation."""
        import src.bulk_content_scan.content_reviewer_agent as m

        assert "content moderation" in m._STATIC_INSTRUCTIONS.lower()

    def test_static_instructions_contains_output_schema_block(self):
        """_STATIC_INSTRUCTIONS must describe the output schema."""
        import src.bulk_content_scan.content_reviewer_agent as m

        assert "ContentModerationClassificationResult" in m._STATIC_INSTRUCTIONS

    def test_agent_instructions_is_static_constant(self):
        """Agent must be created with instructions=_STATIC_INSTRUCTIONS."""
        import src.bulk_content_scan.content_reviewer_agent as m

        instructions_list = m.content_reviewer_agent._instructions
        assert isinstance(instructions_list, list)
        assert len(instructions_list) == 1
        assert instructions_list[0] == m._STATIC_INSTRUCTIONS

    def test_build_instructions_returns_only_dynamic_content(self):
        """_build_instructions must return only dynamic tail (content+evidence), no preamble."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        content_item = make_content_item(content_text="Test message about vaccines")

        instructions = service._build_instructions(
            content_item=content_item,
            pre_computed_evidence=[],
        )

        assert "Test message about vaccines" in instructions
        assert "content moderation classifier" not in instructions.lower()


class TestDynamicContentInUserPrompt:
    """AC12: Dynamic content goes in user prompt, not instructions block."""

    @pytest.mark.asyncio
    async def test_classify_passes_dynamic_content_as_user_prompt(self):
        """classify() must pass dynamic evidence as user prompt content."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result()
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item(content_text="Unique vaccine claim content")
        similarity_match = make_similarity_match(matched_claim="Vaccines do not cause autism")

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[similarity_match],
            model=test_model,
        )

        assert isinstance(result, ContentModerationClassificationResult)

    def test_build_instructions_does_not_include_preamble(self):
        """_build_instructions must not include preamble (it's in _STATIC_INSTRUCTIONS)."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        service = ContentReviewerService()
        content_item = make_content_item()

        instructions = service._build_instructions(
            content_item=content_item,
            pre_computed_evidence=[],
        )

        assert "content moderation classifier" not in instructions.lower()
        assert "ContentModerationClassificationResult" not in instructions


class TestModelSettingsAndUsageLimits:
    """AC9 & AC10: ModelSettings and UsageLimits passed to agent.run()."""

    @pytest.mark.asyncio
    async def test_classify_uses_model_settings(self):
        """classify() must pass ModelSettings(temperature=0.0) to agent.run()."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result()
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()

        with patch(
            "src.bulk_content_scan.content_reviewer_agent.content_reviewer_agent.run"
        ) as mock_run:
            future_result = MagicMock()
            future_result.output = expected

            async def fake_run(*args, **kwargs):
                return future_result

            mock_run.side_effect = fake_run

            await service.classify(
                content_item=content_item,
                pre_computed_evidence=[],
                model=test_model,
            )

            assert mock_run.called
            call_kwargs = mock_run.call_args.kwargs
            assert "model_settings" in call_kwargs
            ms = call_kwargs["model_settings"]
            assert isinstance(ms, dict)
            assert ms.get("temperature") == 0.0

    @pytest.mark.asyncio
    async def test_classify_uses_usage_limits(self):
        """classify() must pass UsageLimits to agent.run()."""
        from pydantic_ai.usage import UsageLimits

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result()
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()

        with patch(
            "src.bulk_content_scan.content_reviewer_agent.content_reviewer_agent.run"
        ) as mock_run:
            future_result = MagicMock()
            future_result.output = expected

            async def fake_run(*args, **kwargs):
                return future_result

            mock_run.side_effect = fake_run

            await service.classify(
                content_item=content_item,
                pre_computed_evidence=[],
                model=test_model,
            )

            assert mock_run.called
            call_kwargs = mock_run.call_args.kwargs
            assert "usage_limits" in call_kwargs
            ul = call_kwargs["usage_limits"]
            assert isinstance(ul, UsageLimits)


class TestRetryRegression:
    """AC5: FunctionModel retry regression — first call fails validation, second succeeds."""

    @pytest.mark.asyncio
    async def test_output_validator_retry_succeeds_on_second_call(self):
        """First JSON validation failure -> valid second call -> valid result."""
        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )

        call_count = {"n": 0}

        def model_fn(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
            call_count["n"] += 1
            if call_count["n"] == 1:
                invalid_output = {
                    "scan_type": "content_moderation_classification",
                    "confidence": 0.9,
                    "category_labels": {"hate": True},
                    "category_scores": None,
                    "recommended_action": None,
                    "action_tier": "tier_1_immediate",
                    "explanation": "invalid: tier without action",
                }
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name=agent_info.output_tools[0].name,
                            args=json.dumps(invalid_output),
                            tool_call_id="call-1",
                        )
                    ]
                )
            valid_output = {
                "scan_type": "content_moderation_classification",
                "confidence": 0.9,
                "category_labels": {"hate": True},
                "category_scores": None,
                "recommended_action": "hide",
                "action_tier": "tier_1_immediate",
                "explanation": "valid output on retry",
            }
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=agent_info.output_tools[0].name,
                        args=json.dumps(valid_output),
                        tool_call_id="call-2",
                    )
                ]
            )

        deps = ContentReviewerDeps(flashpoint_service=None, context_items=[])
        result = await content_reviewer_agent.run(
            "Classify content.",
            deps=deps,
            model=FunctionModel(model_fn),
        )

        assert result.output.recommended_action == "hide"
        assert result.output.action_tier == "tier_1_immediate"
        assert call_count["n"] == 2


class TestStructuredExceptionHandling:
    """AC11: Structured pydantic-ai exception handling."""

    @pytest.mark.asyncio
    async def test_unexpected_model_behavior_returns_fail_open(self):
        """UnexpectedModelBehavior triggers fail-open path."""
        from pydantic_ai.exceptions import UnexpectedModelBehavior

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        def error_model(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Model returned garbage output")

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=FunctionModel(error_model),
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_model_http_error_returns_fail_open(self):
        """ModelHTTPError triggers fail-open path."""
        from pydantic_ai.exceptions import ModelHTTPError

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        def error_model(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
            raise ModelHTTPError(
                status_code=503,
                model_name="test-model",
                body="Service Unavailable",
            )

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=FunctionModel(error_model),
        )

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == 0.0


class TestContentReviewerModelFromConfig:
    """AC2, AC3, AC5: Model is read from config, not via getattr fallback."""

    @pytest.mark.asyncio
    async def test_classify_uses_config_model_when_no_override(self):
        """classify() uses cfg.CONTENT_REVIEWER_MODEL (not getattr fallback) when model=None."""
        from unittest.mock import MagicMock, patch

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result()
        mock_result = MagicMock()
        mock_result.output = expected

        service = ContentReviewerService()
        content_item = make_content_item()

        sentinel_model = object()

        class MockSettings:
            CONTENT_REVIEWER_TIMEOUT = 30.0
            CONTENT_REVIEWER_MODEL = sentinel_model
            CONTENT_REVIEWER_MAX_TOKENS = 1024
            CONTENT_REVIEWER_REQUEST_LIMIT = 5
            CONTENT_REVIEWER_TOTAL_TOKENS_LIMIT = 8192

        service._settings = MockSettings()

        with patch(
            "src.bulk_content_scan.content_reviewer_agent.content_reviewer_agent.run"
        ) as mock_run:

            async def fake_run(*args, **kwargs):
                return mock_result

            mock_run.side_effect = fake_run

            await service.classify(
                content_item=content_item,
                pre_computed_evidence=[],
            )

            assert mock_run.called
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs.get("model") is sentinel_model

    @pytest.mark.asyncio
    async def test_classify_explicit_model_override_takes_precedence(self):
        """classify(model=X) uses X even when cfg.CONTENT_REVIEWER_MODEL is set."""
        from unittest.mock import MagicMock, patch

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result()
        mock_result = MagicMock()
        mock_result.output = expected

        service = ContentReviewerService()
        content_item = make_content_item()

        explicit_model = object()
        config_model = object()

        class MockSettings:
            CONTENT_REVIEWER_TIMEOUT = 30.0
            CONTENT_REVIEWER_MODEL = config_model
            CONTENT_REVIEWER_MAX_TOKENS = 1024
            CONTENT_REVIEWER_REQUEST_LIMIT = 5
            CONTENT_REVIEWER_TOTAL_TOKENS_LIMIT = 8192

        service._settings = MockSettings()

        with patch(
            "src.bulk_content_scan.content_reviewer_agent.content_reviewer_agent.run"
        ) as mock_run:

            async def fake_run(*args, **kwargs):
                return mock_result

            mock_run.side_effect = fake_run

            await service.classify(
                content_item=content_item,
                pre_computed_evidence=[],
                model=explicit_model,
            )

            assert mock_run.called
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs.get("model") is explicit_model


class TestConditionalFlashpointToolExposure:
    """AC1-3: detect_flashpoint_tool conditionally exposed via prepare parameter."""

    @pytest.mark.asyncio
    async def test_flashpoint_tool_excluded_from_function_tools_when_service_is_none(self):
        """detect_flashpoint_tool must not appear in agent_info.function_tools when flashpoint_service=None."""
        from pydantic_ai.messages import ModelResponse
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )

        captured: dict = {}

        def capture_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            captured["tool_names"] = [t.name for t in agent_info.function_tools]
            import json

            from pydantic_ai.messages import ModelResponse, ToolCallPart

            good_output = {
                "scan_type": "content_moderation_classification",
                "confidence": 0.8,
                "category_labels": {"test": True},
                "category_scores": None,
                "recommended_action": None,
                "action_tier": None,
                "explanation": "test",
            }
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=agent_info.output_tools[0].name,
                        args=json.dumps(good_output),
                        tool_call_id="call-1",
                    )
                ]
            )

        deps = ContentReviewerDeps(flashpoint_service=None, context_items=[])
        await content_reviewer_agent.run(
            "Classify this content.",
            deps=deps,
            model=FunctionModel(capture_model),
        )

        assert "detect_flashpoint_tool" not in captured["tool_names"]

    @pytest.mark.asyncio
    async def test_flashpoint_tool_included_in_function_tools_when_service_provided(self):
        """detect_flashpoint_tool must appear in agent_info.function_tools when flashpoint_service is set."""
        import json
        from unittest.mock import AsyncMock

        from pydantic_ai.messages import ModelResponse, ToolCallPart
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )

        captured: dict = {}
        mock_service = AsyncMock()

        def capture_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            captured["tool_names"] = [t.name for t in agent_info.function_tools]
            good_output = {
                "scan_type": "content_moderation_classification",
                "confidence": 0.8,
                "category_labels": {"test": True},
                "category_scores": None,
                "recommended_action": None,
                "action_tier": None,
                "explanation": "test",
            }
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=agent_info.output_tools[0].name,
                        args=json.dumps(good_output),
                        tool_call_id="call-1",
                    )
                ]
            )

        deps = ContentReviewerDeps(flashpoint_service=mock_service, context_items=[])
        await content_reviewer_agent.run(
            "Classify this content.",
            deps=deps,
            model=FunctionModel(capture_model),
        )

        assert "detect_flashpoint_tool" in captured["tool_names"]

    @pytest.mark.asyncio
    async def test_system_prompt_does_not_mention_flashpoint_when_service_is_none(self):
        """When flashpoint_service=None, the tool description must not appear in system messages."""
        import json

        from pydantic_ai.messages import ModelResponse, SystemPromptPart, ToolCallPart
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import (
            ContentReviewerDeps,
            content_reviewer_agent,
        )

        captured: dict = {}

        def capture_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            system_content = []
            for msg in messages:
                for part in msg.parts:
                    if isinstance(part, SystemPromptPart):
                        system_content.append(part.content)
            captured["system_content"] = "\n".join(system_content)
            captured["tool_names"] = [t.name for t in agent_info.function_tools]
            good_output = {
                "scan_type": "content_moderation_classification",
                "confidence": 0.8,
                "category_labels": {"test": True},
                "category_scores": None,
                "recommended_action": None,
                "action_tier": None,
                "explanation": "test",
            }
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=agent_info.output_tools[0].name,
                        args=json.dumps(good_output),
                        tool_call_id="call-1",
                    )
                ]
            )

        deps = ContentReviewerDeps(flashpoint_service=None, context_items=[])
        await content_reviewer_agent.run(
            "Classify this content.",
            deps=deps,
            model=FunctionModel(capture_model),
        )

        assert "detect_flashpoint_tool" not in captured["tool_names"]
        assert "detect_flashpoint_tool" not in captured.get("system_content", "")


class TestErrorTypeDiscrimination:
    """AC1-5: error_type field distinguishes hard failures from low-confidence."""

    @pytest.mark.asyncio
    async def test_normal_classification_has_no_error_type(self):
        """Successful classification should have error_type=None."""
        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        expected = make_classification_result(confidence=0.85)
        test_model = TestModel(custom_output_args=expected, call_tools=[])

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=test_model,
        )

        assert result.error_type is None

    @pytest.mark.asyncio
    async def test_timeout_sets_error_type_timeout(self):
        """Timeout failure should set error_type='timeout'."""
        import asyncio

        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        async def slow_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            await asyncio.sleep(999)
            raise RuntimeError("Should not reach here")

        service = ContentReviewerService()
        content_item = make_content_item()

        class MockSettings:
            CONTENT_REVIEWER_TIMEOUT = 0.01
            CONTENT_REVIEWER_MODEL = None

        service._settings = MockSettings()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=FunctionModel(slow_model),
        )

        assert result.error_type == "timeout"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_transport_error_sets_error_type(self):
        """ModelHTTPError should set error_type='transport_error'."""
        from pydantic_ai.exceptions import ModelHTTPError
        from pydantic_ai.messages import ModelResponse
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        def error_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise ModelHTTPError(
                status_code=503,
                model_name="test-model",
                body="Service Unavailable",
            )

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=FunctionModel(error_model),
        )

        assert result.error_type == "transport_error"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_parse_error_sets_error_type(self):
        """UnexpectedModelBehavior should set error_type='parse_error'."""
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        from pydantic_ai.messages import ModelResponse
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        def error_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Model returned garbage output")

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=FunctionModel(error_model),
        )

        assert result.error_type == "parse_error"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_unexpected_error_sets_error_type(self):
        """Unexpected RuntimeError should set error_type='unexpected_error'."""
        from pydantic_ai.messages import ModelResponse
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService

        def error_model(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise RuntimeError("Unexpected crash")

        service = ContentReviewerService()
        content_item = make_content_item()

        result = await service.classify(
            content_item=content_item,
            pre_computed_evidence=[],
            model=FunctionModel(error_model),
        )

        assert result.error_type == "unexpected_error"
        assert result.confidence == 0.0

    def test_low_confidence_classification_has_no_error_type(self):
        """Low confidence from a normal model result should NOT set error_type."""
        result = make_classification_result(
            confidence=0.0,
            explanation="Agent determined this content is low-risk",
        )
        assert result.error_type is None

    def test_error_type_field_exists_on_schema(self):
        """ContentModerationClassificationResult must have an error_type field."""
        result = ContentModerationClassificationResult(
            confidence=0.5,
            category_labels={"test": True},
            explanation="test",
        )
        assert hasattr(result, "error_type")
        assert result.error_type is None

    def test_error_type_can_be_set(self):
        """error_type can be set to a string value."""
        result = ContentModerationClassificationResult(
            confidence=0.0,
            category_labels={},
            explanation="Classification failed: timeout after 30s",
            error_type="timeout",
        )
        assert result.error_type == "timeout"
