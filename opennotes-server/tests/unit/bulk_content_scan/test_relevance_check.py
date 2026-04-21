"""Tests for LLM relevance check in bulk content scan.

These tests verify that BulkContentScanService._check_relevance_with_llm
correctly delegates to ClaimRelevanceService which uses the module-level
relevance_agent for structured output and pydantic_ai.direct.model_request
for retry paths.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pendulum
import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from src.bulk_content_scan.schemas import (
    BulkScanMessage,
    RelevanceOutcome,
)
from src.bulk_content_scan.service import BulkContentScanService
from src.claim_relevance_check.schemas import RelevanceCheckResult
from src.claim_relevance_check.service import relevance_agent
from src.fact_checking.embedding_schemas import FactCheckMatch, SimilaritySearchResponse


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def mock_embedding_service():
    return AsyncMock()


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    redis.lpush = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    redis.expire = AsyncMock()
    return redis


@pytest.fixture
def mock_llm_service():
    return MagicMock()


@pytest.fixture
def mock_bulk_settings():
    """Settings mock for bulk content scan tests.

    Patches the module-level settings in bulk_content_scan.service,
    which is passed through to ClaimRelevanceService.
    """
    with patch("src.bulk_content_scan.service.settings") as s:
        s.RELEVANCE_CHECK_ENABLED = True
        s.RELEVANCE_CHECK_MODEL = MagicMock()
        s.RELEVANCE_CHECK_MAX_TOKENS = 150
        s.RELEVANCE_CHECK_TIMEOUT = 5.0
        s.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False
        s.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
        s.INSTANCE_ID = "test"
        yield s


@pytest.fixture
def sample_message() -> BulkScanMessage:
    return BulkScanMessage(
        message_id="123456789",
        channel_id="987654321",
        community_server_id="111222333",
        content="The earth is flat and NASA is hiding the truth.",
        author_id="444555666",
        timestamp=pendulum.now("UTC"),
    )


@pytest.fixture
def sample_fact_check_match() -> FactCheckMatch:
    return FactCheckMatch(
        id=uuid4(),
        dataset_name="snopes",
        dataset_tags=["science"],
        title="Flat Earth Claim Debunked",
        content="The claim that the Earth is flat has been thoroughly debunked by science.",
        summary="Earth is not flat",
        rating="false",
        source_url="https://snopes.com/fact-check/flat-earth",
        published_date=pendulum.now("UTC"),
        author="Fact Checker",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        similarity_score=0.92,
    )


class TestCheckRelevanceWithLLM:
    """Tests for _check_relevance_with_llm method."""

    @pytest.mark.asyncio
    async def test_check_relevance_returns_relevant_for_relevant_match(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="The fact check directly addresses the flat earth claim in the message.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="The earth is flat and NASA is hiding the truth.",
                matched_content="The claim that the Earth is flat has been thoroughly debunked.",
                matched_source="https://snopes.com/fact-check/flat-earth",
            )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "flat earth" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_check_relevance_returns_not_relevant_for_irrelevant_match(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=False,
                reasoning="The fact check is about vaccine safety, not related to the weather discussion.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="It looks like it will rain tomorrow.",
                matched_content="COVID vaccines have been proven safe and effective.",
                matched_source="https://factcheck.org/vaccines",
            )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        assert len(reasoning) > 0

    @pytest.mark.asyncio
    async def test_check_relevance_fails_open_on_llm_error_returns_indeterminate(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        def raise_error(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise Exception("LLM service unavailable")

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=FunctionModel(raise_error)):
            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test matched content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "error" in reasoning.lower() or "failed" in reasoning.lower()

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.pydantic_model_request")
    async def test_check_relevance_fails_open_on_malformed_json_returns_indeterminate(
        self,
        mock_model_request,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        def raise_unexpected(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Failed to parse structured output")

        mock_response = MagicMock()
        mock_response.finish_reason = "stop"
        mock_response.text = '{"has_claims": true, "reasoning": "test"}'
        mock_model_request.return_value = mock_response

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=FunctionModel(raise_unexpected)):
            outcome, _reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test matched content",
                matched_source=None,
            )

        assert outcome == RelevanceOutcome.INDETERMINATE

    @pytest.mark.asyncio
    async def test_check_relevance_disabled_by_feature_flag(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = False

            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "disabled" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_check_relevance_handles_none_matched_source(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="Content is relevant.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, _reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test content",
                matched_source=None,
            )

        assert outcome == RelevanceOutcome.RELEVANT


class TestSimilarityScanRelevanceIntegration:
    """Tests for relevance check integration with _similarity_scan."""

    @pytest.mark.asyncio
    async def test_similarity_scan_skips_flagging_when_relevance_check_fails(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        sample_message,
        sample_fact_check_match,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=False,
                reasoning="The fact check is not related to the message.",
            )
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[sample_fact_check_match],
                total_matches=1,
                query_text=sample_message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.7,
                score_threshold=0.1,
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            relevance_agent.override(model=test_model),
        ):
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=sample_message,
                community_server_platform_id="111222333",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_similarity_scan_flags_message_when_relevance_check_passes(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        sample_message,
        sample_fact_check_match,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="The fact check directly addresses the claim.",
            )
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[sample_fact_check_match],
                total_matches=1,
                query_text=sample_message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.7,
                score_threshold=0.1,
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            relevance_agent.override(model=test_model),
        ):
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=sample_message,
                community_server_platform_id="111222333",
            )

        assert result is not None
        assert result.message_id == sample_message.message_id
        assert len(result.matches) == 1

    @pytest.mark.asyncio
    async def test_similarity_scan_flags_high_score_on_llm_error_with_tighter_threshold(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        sample_message,
        sample_fact_check_match,
    ) -> None:
        """When Agent errors, apply tighter threshold. Score 0.92 > 0.85 -> flagged."""

        def raise_error(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise Exception("LLM unavailable")

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[sample_fact_check_match],
                total_matches=1,
                query_text=sample_message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.7,
                score_threshold=0.1,
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            relevance_agent.override(model=FunctionModel(raise_error)),
        ):
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.INSTANCE_ID = "test"

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=sample_message,
                community_server_platform_id="111222333",
            )

        assert result is not None
        assert result.message_id == sample_message.message_id

    @pytest.mark.asyncio
    async def test_similarity_scan_skips_relevance_check_when_no_match(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        sample_message,
    ) -> None:
        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[],
                total_matches=0,
                query_text=sample_message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.7,
                score_threshold=0.1,
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=sample_message,
                community_server_platform_id="111222333",
            )

        assert result is None


class TestRelevanceCheckPrompt:
    """Tests for the Agent prompt structure."""

    @pytest.mark.asyncio
    async def test_prompt_includes_original_message(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        captured_messages: list = []

        def capture_prompt(messages: list, agent_info: AgentInfo) -> ModelResponse:
            captured_messages.extend(messages)
            return ModelResponse(
                parts=[
                    TextPart(
                        content=RelevanceCheckResult(
                            is_relevant=True, reasoning="Test"
                        ).model_dump_json()
                    ),
                ]
            )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        original_msg = "Unique test message content 12345"

        with relevance_agent.override(model=FunctionModel(capture_prompt)):
            await service._check_relevance_with_llm(
                original_message=original_msg,
                matched_content="Some matched content",
                matched_source="https://example.com",
            )

        all_text = ""
        for msg in captured_messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part, "content"):
                        all_text += part.content + " "
        assert original_msg in all_text

    @pytest.mark.asyncio
    async def test_prompt_includes_matched_content(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        captured_messages: list = []

        def capture_prompt(messages: list, agent_info: AgentInfo) -> ModelResponse:
            captured_messages.extend(messages)
            return ModelResponse(
                parts=[
                    TextPart(
                        content=RelevanceCheckResult(
                            is_relevant=True, reasoning="Test"
                        ).model_dump_json()
                    ),
                ]
            )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        matched = "Unique matched content ABCDE"

        with relevance_agent.override(model=FunctionModel(capture_prompt)):
            await service._check_relevance_with_llm(
                original_message="Some message",
                matched_content=matched,
                matched_source="https://example.com",
            )

        all_text = ""
        for msg in captured_messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part, "content"):
                        all_text += part.content + " "
        assert matched in all_text

    @pytest.mark.asyncio
    async def test_prompt_requests_structured_output(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        captured_agent_info: list[AgentInfo] = []

        def capture_info(messages: list, agent_info: AgentInfo) -> ModelResponse:
            captured_agent_info.append(agent_info)
            return ModelResponse(
                parts=[
                    TextPart(
                        content=RelevanceCheckResult(
                            is_relevant=True, reasoning="Test"
                        ).model_dump_json()
                    ),
                ]
            )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=FunctionModel(capture_info)):
            await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test content",
                matched_source=None,
            )

        assert len(captured_agent_info) == 1
        assert len(captured_agent_info[0].output_tools) > 0


class TestRelevanceCheckEdgeCases:
    """Tests for edge cases and error handling in relevance check."""

    @pytest.mark.asyncio
    async def test_check_relevance_handles_empty_matched_content(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=False,
                reasoning="Empty reference cannot be evaluated.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, _reasoning = await service._check_relevance_with_llm(
                original_message="The earth is flat.",
                matched_content="",
                matched_source=None,
            )

        assert outcome == RelevanceOutcome.NOT_RELEVANT

    @pytest.mark.asyncio
    async def test_check_relevance_fails_open_on_timeout_returns_indeterminate(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        import asyncio

        async def slow_response(messages: list, agent_info: AgentInfo) -> ModelResponse:
            await asyncio.sleep(10)
            return ModelResponse(parts=[TextPart(content="test")])

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            relevance_agent.override(model=FunctionModel(slow_response)),
        ):
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150

            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test matched content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "timed out" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_check_relevance_uses_configured_provider(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="Test",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            relevance_agent.override(model=test_model),
        ):
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False

            outcome, _reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test content",
                matched_source=None,
            )

        assert outcome == RelevanceOutcome.RELEVANT
        assert test_model.last_model_request_parameters is not None

    @pytest.mark.asyncio
    async def test_provider_inferred_from_vertex_ai_model_prefix(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="Relevant claim",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            relevance_agent.override(model=test_model),
        ):
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False

            outcome, _reasoning = await service._check_relevance_with_llm(
                original_message="The earth is flat.",
                matched_content="The claim that the Earth is flat has been debunked.",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.RELEVANT


class TestTopicMentionFiltering:
    """Tests for filtering topic mentions without claims (task-959)."""

    @pytest.mark.asyncio
    async def test_rejects_short_topic_mention_how_about_biden(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=False,
                reasoning="No claim present - just a topic mention.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, _ = await service._check_relevance_with_llm(
                original_message="how about biden",
                matched_content="Joe Biden's policy positions on various issues.",
                matched_source="https://factcheck.org/biden",
            )

        assert outcome == RelevanceOutcome.NOT_RELEVANT

    @pytest.mark.asyncio
    async def test_rejects_topic_mention_some_things_about_person(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=False,
                reasoning="No specific claim - just mentions wanting information about a person.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, _ = await service._check_relevance_with_llm(
                original_message="some things about kamala harris",
                matched_content="Kamala Harris background and political career.",
                matched_source="https://factcheck.org/harris",
            )

        assert outcome == RelevanceOutcome.NOT_RELEVANT

    @pytest.mark.asyncio
    async def test_rejects_or_name_pattern(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=False,
                reasoning="Just a name fragment, no verifiable claim.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, _ = await service._check_relevance_with_llm(
                original_message="or donald trump",
                matched_content="Donald Trump's statements about various topics.",
                matched_source="https://politifact.com/trump",
            )

        assert outcome == RelevanceOutcome.NOT_RELEVANT

    @pytest.mark.asyncio
    async def test_accepts_actual_claim_about_person(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=True,
                reasoning="Contains a specific verifiable claim about Biden being a Confederate soldier.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, _ = await service._check_relevance_with_llm(
                original_message="Biden was a Confederate soldier",
                matched_content="Fact check: Joe Biden was not a Confederate soldier.",
                matched_source="https://factcheck.org/biden-confederate",
            )

        assert outcome == RelevanceOutcome.RELEVANT

    @pytest.mark.asyncio
    async def test_rejects_question_about_topic(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        test_model = TestModel(
            custom_output_args=RelevanceCheckResult(
                is_relevant=False,
                reasoning="This is a question, not a claim that can be fact-checked.",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=test_model):
            outcome, _ = await service._check_relevance_with_llm(
                original_message="What about the vaccine?",
                matched_content="COVID-19 vaccine safety and efficacy information.",
                matched_source="https://factcheck.org/vaccines",
            )

        assert outcome == RelevanceOutcome.NOT_RELEVANT

    @pytest.mark.asyncio
    async def test_prompt_includes_step_by_step_instructions(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        captured_messages: list = []

        def capture_prompt(messages: list, agent_info: AgentInfo) -> ModelResponse:
            captured_messages.extend(messages)
            return ModelResponse(
                parts=[
                    TextPart(
                        content=RelevanceCheckResult(
                            is_relevant=False, reasoning="No claim"
                        ).model_dump_json()
                    ),
                ]
            )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            relevance_agent.override(model=FunctionModel(capture_prompt)),
        ):
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = True

            await service._check_relevance_with_llm(
                original_message="how about biden",
                matched_content="Biden fact check content",
                matched_source=None,
            )

        all_text = ""
        for msg in captured_messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part, "content"):
                        all_text += part.content + " "

        assert "CLAIM DETECTION" in all_text
        assert "RELEVANCE CHECK" in all_text
        assert "Step 1 is NO" in all_text


class TestContentFilterDetection:
    """Tests for content filter detection and retry logic (task-968).

    The primary relevance check uses the module-level relevance_agent. When it
    fails (e.g., content filter causes structured output parsing failure), it
    raises UnexpectedModelBehavior, which triggers a retry using
    pydantic_ai.direct.model_request.
    """

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.pydantic_model_request")
    async def test_content_filter_triggers_retry_without_fact_check(
        self,
        mock_model_request,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        def raise_unexpected(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Content filter triggered")

        mock_response = MagicMock()
        mock_response.finish_reason = "stop"
        mock_response.text = '{"has_claims": true, "reasoning": "Contains claims"}'
        mock_model_request.return_value = mock_response

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=FunctionModel(raise_unexpected)):
            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="Potentially sensitive message",
                matched_content="Fact check with sensitive content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "fact-check" in reasoning.lower() or "indeterminate" in reasoning.lower()
        mock_model_request.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.pydantic_model_request")
    async def test_retry_also_filtered_returns_content_filtered(
        self,
        mock_model_request,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        def raise_unexpected(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Content filter triggered")

        mock_response = MagicMock()
        mock_response.finish_reason = "content_filter"
        mock_response.text = ""
        mock_model_request.return_value = mock_response

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=FunctionModel(raise_unexpected)):
            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="Problematic user message content",
                matched_content="Normal fact check content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.CONTENT_FILTERED
        assert "message" in reasoning.lower()
        assert "filter" in reasoning.lower()

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.pydantic_model_request")
    async def test_retry_succeeds_returns_indeterminate(
        self,
        mock_model_request,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        def raise_unexpected(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Content filter triggered")

        mock_response = MagicMock()
        mock_response.finish_reason = "stop"
        mock_response.text = '{"has_claims": false, "reasoning": "No claims"}'
        mock_model_request.return_value = mock_response

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=FunctionModel(raise_unexpected)):
            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="Normal user message",
                matched_content="Fact check that triggers content filter",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "fact-check" in reasoning.lower()

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.pydantic_model_request")
    async def test_retry_timeout_returns_indeterminate(
        self,
        mock_model_request,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        import asyncio

        def raise_unexpected(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Content filter triggered")

        async def slow_request(*args, **kwargs):
            await asyncio.sleep(10)
            return MagicMock(finish_reason="stop", text="ok")

        mock_model_request.side_effect = slow_request

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            relevance_agent.override(model=FunctionModel(raise_unexpected)),
        ):
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1
            mock_settings.RELEVANCE_CHECK_MODEL = MagicMock()
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False

            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Fact check content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "timed out" in reasoning.lower()

    @pytest.mark.asyncio
    @patch("src.claim_relevance_check.service.pydantic_model_request")
    async def test_retry_error_returns_indeterminate(
        self,
        mock_model_request,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        mock_bulk_settings,
    ) -> None:
        def raise_unexpected(messages: list, agent_info: AgentInfo) -> ModelResponse:
            raise UnexpectedModelBehavior("Content filter triggered")

        mock_model_request.side_effect = Exception("Retry failed")

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with relevance_agent.override(model=FunctionModel(raise_unexpected)):
            outcome, _reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Fact check content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.INDETERMINATE
