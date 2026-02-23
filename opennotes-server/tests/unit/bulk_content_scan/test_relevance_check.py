"""Tests for LLM relevance check in bulk content scan.

These tests are written TDD-style before implementation exists.
They will initially fail until the relevance check feature is implemented.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pendulum
import pytest

from src.bulk_content_scan.schemas import (
    BulkScanMessage,
    RelevanceOutcome,
    ScanCandidate,
    SimilarityMatch,
)
from src.bulk_content_scan.service import BulkContentScanService
from src.fact_checking.embedding_schemas import FactCheckMatch, SimilaritySearchResponse
from src.llm_config.providers.base import LLMResponse


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    return AsyncMock()


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
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
    """Create a mock LLM service."""
    return MagicMock()


@pytest.fixture
def sample_message() -> BulkScanMessage:
    """Create a sample message for testing."""
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
    """Create a sample fact check match for testing."""
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
    ) -> None:
        """When LLM determines match is relevant, should return (RELEVANT, reasoning)."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": True,
                        "reasoning": "The fact check directly addresses the flat earth claim in the message.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=50,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, reasoning = await service._check_relevance_with_llm(
            original_message="The earth is flat and NASA is hiding the truth.",
            matched_content="The claim that the Earth is flat has been thoroughly debunked.",
            matched_source="https://snopes.com/fact-check/flat-earth",
        )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "flat earth" in reasoning.lower()
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_relevance_returns_not_relevant_for_irrelevant_match(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When LLM determines match is NOT relevant, should return (NOT_RELEVANT, reasoning)."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": False,
                        "reasoning": "The fact check is about vaccine safety, not related to the weather discussion.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=45,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, reasoning = await service._check_relevance_with_llm(
            original_message="It looks like it will rain tomorrow.",
            matched_content="COVID vaccines have been proven safe and effective.",
            matched_source="https://factcheck.org/vaccines",
        )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        assert len(reasoning) > 0
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_relevance_fails_open_on_llm_error_returns_indeterminate(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When LLM call fails, should return INDETERMINATE to apply tighter threshold."""
        mock_llm_service.complete = AsyncMock(side_effect=Exception("LLM service unavailable"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, reasoning = await service._check_relevance_with_llm(
            original_message="Test message",
            matched_content="Test matched content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "error" in reasoning.lower() or "failed" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_check_relevance_fails_open_on_malformed_json_returns_indeterminate(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When LLM returns malformed JSON, should return INDETERMINATE (apply tighter threshold)."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content="This is not valid JSON",
                model="openai/gpt-5-mini",
                tokens_used=10,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

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
        """When RELEVANCE_CHECK_ENABLED=False, skip check and return RELEVANT without calling LLM."""
        mock_llm_service.complete = AsyncMock()

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
        mock_llm_service.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_relevance_handles_none_matched_source(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Should handle None matched_source gracefully."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": True,
                        "reasoning": "Content is relevant.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, _reasoning = await service._check_relevance_with_llm(
            original_message="Test message",
            matched_content="Test content",
            matched_source=None,
        )

        assert outcome == RelevanceOutcome.RELEVANT
        mock_llm_service.complete.assert_called_once()


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
        """When relevance check returns False, _similarity_scan should return None."""
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

        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": False,
                        "reasoning": "The fact check is not related to the message.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=30,
                finish_reason="stop",
                provider="openai",
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
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=sample_message,
                community_server_platform_id="111222333",
            )

        assert result is None
        mock_llm_service.complete.assert_called_once()

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
        """When relevance check returns True, _similarity_scan should return FlaggedMessage."""
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

        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": True,
                        "reasoning": "The fact check directly addresses the claim.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=30,
                finish_reason="stop",
                provider="openai",
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
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
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
        """When LLM errors, apply tighter threshold. Score 0.92 > 0.85 → flagged.

        With base threshold 0.7, indeterminate threshold = 0.7 + (1-0.7)/2 = 0.85.
        The sample_fact_check_match has similarity_score=0.92, which exceeds 0.85.
        """
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

        mock_llm_service.complete = AsyncMock(side_effect=Exception("LLM unavailable"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
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
        """When no similarity match found, should not call relevance check."""
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
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=sample_message,
                community_server_platform_id="111222333",
            )

        assert result is None
        mock_llm_service.complete.assert_not_called()


class TestRelevanceCheckPrompt:
    """Tests for the LLM prompt structure."""

    @pytest.mark.asyncio
    async def test_prompt_includes_original_message(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """The LLM prompt should include the original message content."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        original_msg = "Unique test message content 12345"

        await service._check_relevance_with_llm(
            original_message=original_msg,
            matched_content="Some matched content",
            matched_source="https://example.com",
        )

        call_args = mock_llm_service.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        all_content = " ".join(m.content for m in messages)

        assert original_msg in all_content

    @pytest.mark.asyncio
    async def test_prompt_includes_matched_content(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """The LLM prompt should include the matched content."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        matched = "Unique matched content ABCDE"

        await service._check_relevance_with_llm(
            original_message="Some message",
            matched_content=matched,
            matched_source="https://example.com",
        )

        call_args = mock_llm_service.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        all_content = " ".join(m.content for m in messages)

        assert matched in all_content

    @pytest.mark.asyncio
    async def test_prompt_requests_json_response(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """The LLM call should request JSON response format."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        await service._check_relevance_with_llm(
            original_message="Test message",
            matched_content="Test content",
            matched_source=None,
        )

        call_args = mock_llm_service.complete.call_args
        kwargs = call_args.kwargs if call_args.kwargs else {}

        assert "response_format" in kwargs or any(
            "json" in str(m.content).lower() for m in (kwargs.get("messages") or [])
        )


class TestRelevanceCheckEdgeCases:
    """Tests for edge cases and error handling in relevance check."""

    @pytest.mark.asyncio
    async def test_check_relevance_handles_empty_matched_content(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Should handle empty matched_content gracefully."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": False,
                        "reasoning": "Empty reference cannot be evaluated.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=15,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, _reasoning = await service._check_relevance_with_llm(
            original_message="The earth is flat.",
            matched_content="",
            matched_source=None,
        )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_relevance_fails_open_on_timeout_returns_indeterminate(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When LLM call times out, should return INDETERMINATE to apply tighter threshold."""
        import asyncio

        async def slow_complete(*args, **kwargs):
            await asyncio.sleep(10)
            return LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = slow_complete

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
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
        """Should use RELEVANCE_CHECK_MODEL with provider prefix from settings."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="anthropic/claude-3-haiku",
                tokens_used=20,
                finish_reason="stop",
                provider="anthropic",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "anthropic/claude-3-haiku"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

            await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test content",
                matched_source=None,
            )

        call_args = mock_llm_service.complete.call_args
        assert call_args.kwargs.get("model") == "anthropic/claude-3-haiku"

    @pytest.mark.asyncio
    async def test_provider_inferred_from_vertex_ai_model_prefix(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Provider should be inferred from model prefix (vertex_ai/gemini-2.5-flash)."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Relevant claim"}),
                model="vertex_ai/gemini-2.5-flash",
                tokens_used=30,
                finish_reason="stop",
                provider="vertex_ai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "vertex_ai/gemini-2.5-flash"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

            outcome, _reasoning = await service._check_relevance_with_llm(
                original_message="The earth is flat.",
                matched_content="The claim that the Earth is flat has been debunked.",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.RELEVANT
        call_args = mock_llm_service.complete.call_args
        assert call_args.kwargs.get("model") == "vertex_ai/gemini-2.5-flash"


class TestTopicMentionFiltering:
    """Tests for filtering topic mentions without claims (task-959)."""

    @pytest.mark.asyncio
    async def test_rejects_short_topic_mention_how_about_biden(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """'how about biden' should be rejected - no claim, just a name mention."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": False,
                        "reasoning": "No claim present - just a topic mention.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=25,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, _ = await service._check_relevance_with_llm(
            original_message="how about biden",
            matched_content="Joe Biden's policy positions on various issues.",
            matched_source="https://factcheck.org/biden",
        )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_topic_mention_some_things_about_person(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """'some things about kamala harris' should be rejected - vague topic, no claim."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": False,
                        "reasoning": "No specific claim - just mentions wanting information about a person.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=30,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, _ = await service._check_relevance_with_llm(
            original_message="some things about kamala harris",
            matched_content="Kamala Harris background and political career.",
            matched_source="https://factcheck.org/harris",
        )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_or_name_pattern(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """'or donald trump' should be rejected - fragment with no claim."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": False,
                        "reasoning": "Just a name fragment, no verifiable claim.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, _ = await service._check_relevance_with_llm(
            original_message="or donald trump",
            matched_content="Donald Trump's statements about various topics.",
            matched_source="https://politifact.com/trump",
        )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_actual_claim_about_person(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """'Biden was a Confederate soldier' should be accepted - specific false claim."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": True,
                        "reasoning": "Contains a specific verifiable claim about Biden being a Confederate soldier.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=35,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, _ = await service._check_relevance_with_llm(
            original_message="Biden was a Confederate soldier",
            matched_content="Fact check: Joe Biden was not a Confederate soldier.",
            matched_source="https://factcheck.org/biden-confederate",
        )

        assert outcome == RelevanceOutcome.RELEVANT
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_question_about_topic(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """'What about the vaccine?' should be rejected - question, not a claim."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "is_relevant": False,
                        "reasoning": "This is a question, not a claim that can be fact-checked.",
                    }
                ),
                model="openai/gpt-5-mini",
                tokens_used=25,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, _ = await service._check_relevance_with_llm(
            original_message="What about the vaccine?",
            matched_content="COVID-19 vaccine safety and efficacy information.",
            matched_source="https://factcheck.org/vaccines",
        )

        assert outcome == RelevanceOutcome.NOT_RELEVANT
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_prompt_includes_step_by_step_instructions(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """The prompt should include step-by-step claim-first instructions."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": False, "reasoning": "No claim"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        await service._check_relevance_with_llm(
            original_message="how about biden",
            matched_content="Biden fact check content",
            matched_source=None,
        )

        call_args = mock_llm_service.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_prompt = next(m.content for m in messages if m.role == "user")

        assert "CLAIM DETECTION" in user_prompt
        assert "RELEVANCE CHECK" in user_prompt
        assert "Step 1 is NO" in user_prompt


class TestContentFilterDetection:
    """Tests for content filter detection and retry logic (task-968)."""

    @pytest.mark.asyncio
    async def test_content_filter_triggers_retry_without_fact_check(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When content_filter is returned, should retry without fact-check content."""
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="openai/gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            return LLMResponse(
                content=json.dumps({"has_claims": True, "reasoning": "Contains claims"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, reasoning = await service._check_relevance_with_llm(
            original_message="Potentially sensitive message",
            matched_content="Fact check with sensitive content",
            matched_source="https://example.com",
        )

        assert call_count == 2
        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "fact-check" in reasoning.lower() or "indeterminate" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_retry_also_filtered_returns_content_filtered(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When retry also triggers content_filter, should return CONTENT_FILTERED."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content="",
                model="openai/gpt-5-mini",
                tokens_used=0,
                finish_reason="content_filter",
                provider="openai",
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, reasoning = await service._check_relevance_with_llm(
            original_message="Problematic user message content",
            matched_content="Normal fact check content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.CONTENT_FILTERED
        assert "message" in reasoning.lower()
        assert "filter" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_retry_succeeds_returns_indeterminate(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When retry succeeds (no filter), should return INDETERMINATE."""
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="openai/gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            return LLMResponse(
                content=json.dumps({"has_claims": False, "reasoning": "No claims"}),
                model="openai/gpt-5-mini",
                tokens_used=15,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, reasoning = await service._check_relevance_with_llm(
            original_message="Normal user message",
            matched_content="Fact check that triggers content filter",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "fact-check" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_retry_timeout_returns_indeterminate(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When retry times out, should return INDETERMINATE."""
        import asyncio

        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="openai/gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            await asyncio.sleep(10)
            return LLMResponse(
                content=json.dumps({"has_claims": True}),
                model="openai/gpt-5-mini",
                tokens_used=15,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
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
    async def test_retry_error_returns_indeterminate(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When retry fails with an error, should return INDETERMINATE."""
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="openai/gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            raise Exception("Retry failed")

        mock_llm_service.complete = mock_complete

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        outcome, reasoning = await service._check_relevance_with_llm(
            original_message="Test message",
            matched_content="Fact check content",
            matched_source="https://example.com",
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "failed" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_indeterminate_outcome_below_threshold_does_not_flag(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        sample_message,
    ) -> None:
        """When INDETERMINATE and score below tighter threshold, should not flag.

        With base threshold 0.7, indeterminate threshold = 0.7 + (1-0.7)/2 = 0.85.
        Score 0.80 < 0.85, so message should not be flagged.
        """
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="openai/gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            return LLMResponse(
                content=json.dumps({"has_claims": True}),
                model="openai/gpt-5-mini",
                tokens_used=15,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete

        low_score_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["science"],
            title="Flat Earth Claim Debunked",
            content="The claim that the Earth is flat has been thoroughly debunked.",
            summary="Earth is not flat",
            rating="false",
            source_url="https://snopes.com/fact-check/flat-earth",
            published_date=pendulum.now("UTC"),
            author="Fact Checker",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.80,
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[low_score_match],
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

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=sample_message,
                community_server_platform_id="111222333",
            )

        assert result is None


class TestCalculateIndeterminateThreshold:
    """Tests for calculate_indeterminate_threshold() pure function."""

    def test_calculate_indeterminate_threshold_low_base_0_35_to_0_675(self) -> None:
        """Input 0.35 → 0.675 using formula threshold + ((1-threshold)/2)."""
        from src.bulk_content_scan.service import calculate_indeterminate_threshold

        result = calculate_indeterminate_threshold(0.35)
        assert result == pytest.approx(0.675)

    def test_calculate_indeterminate_threshold_medium_base_0_60_to_0_80(self) -> None:
        """Input 0.60 → 0.80 using formula threshold + ((1-threshold)/2)."""
        from src.bulk_content_scan.service import calculate_indeterminate_threshold

        result = calculate_indeterminate_threshold(0.60)
        assert result == pytest.approx(0.80)

    def test_calculate_indeterminate_threshold_high_base_0_80_to_0_90(self) -> None:
        """Input 0.80 → 0.90 using formula threshold + ((1-threshold)/2)."""
        from src.bulk_content_scan.service import calculate_indeterminate_threshold

        result = calculate_indeterminate_threshold(0.80)
        assert result == pytest.approx(0.90)

    def test_calculate_indeterminate_threshold_boundary_zero_to_0_5(self) -> None:
        """Input 0.0 → 0.5 (edge case: minimum threshold)."""
        from src.bulk_content_scan.service import calculate_indeterminate_threshold

        result = calculate_indeterminate_threshold(0.0)
        assert result == pytest.approx(0.5)

    def test_calculate_indeterminate_threshold_boundary_one_unchanged(self) -> None:
        """Input 1.0 → 1.0 (edge case: maximum threshold stays at 1.0)."""
        from src.bulk_content_scan.service import calculate_indeterminate_threshold

        result = calculate_indeterminate_threshold(1.0)
        assert result == pytest.approx(1.0)


class TestFilterCandidatesWithRelevanceIndeterminate:
    """Tests for INDETERMINATE handling in _filter_candidates_with_relevance()."""

    @pytest.mark.asyncio
    async def test_indeterminate_high_score_above_tighter_threshold_is_flagged(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Score 0.90 with threshold 0.7 (indeterminate threshold 0.85) → flagged."""
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="openai/gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            return LLMResponse(
                content=json.dumps({"has_claims": True, "reasoning": "Contains claims"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        message = BulkScanMessage(
            message_id="test_msg_1",
            channel_id="test_channel",
            community_server_id="test_server",
            content="Test message content",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        similarity_match = SimilarityMatch(
            score=0.90,
            matched_claim="Test fact check",
            matched_source="https://example.com/fact-check",
            fact_check_item_id=uuid4(),
        )

        candidate = ScanCandidate(
            message=message,
            scan_type="similarity",
            match_data=similarity_match,
            score=0.90,
            matched_content="Test fact check content",
            matched_source="https://example.com/fact-check",
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False
            mock_settings.INSTANCE_ID = "test"

            flagged = await service._filter_candidates_with_relevance([candidate], uuid4())

        assert len(flagged) == 1
        assert flagged[0].message_id == "test_msg_1"

    @pytest.mark.asyncio
    async def test_indeterminate_low_score_below_tighter_threshold_not_flagged(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Score 0.75 with threshold 0.7 (indeterminate threshold 0.85) → not flagged."""
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="openai/gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            return LLMResponse(
                content=json.dumps({"has_claims": True, "reasoning": "Contains claims"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        message = BulkScanMessage(
            message_id="test_msg_2",
            channel_id="test_channel",
            community_server_id="test_server",
            content="Test message content",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        similarity_match = SimilarityMatch(
            score=0.75,
            matched_claim="Test fact check",
            matched_source="https://example.com/fact-check",
            fact_check_item_id=uuid4(),
        )

        candidate = ScanCandidate(
            message=message,
            scan_type="similarity",
            match_data=similarity_match,
            score=0.75,
            matched_content="Test fact check content",
            matched_source="https://example.com/fact-check",
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False
            mock_settings.INSTANCE_ID = "test"

            flagged = await service._filter_candidates_with_relevance([candidate], uuid4())

        assert len(flagged) == 0

    @pytest.mark.asyncio
    async def test_indeterminate_score_exactly_at_tighter_threshold_is_flagged(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Score 0.85 exactly at tighter threshold → flagged (>= comparison)."""
        call_count = 0

        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="",
                    model="openai/gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            return LLMResponse(
                content=json.dumps({"has_claims": True, "reasoning": "Contains claims"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        message = BulkScanMessage(
            message_id="test_msg_3",
            channel_id="test_channel",
            community_server_id="test_server",
            content="Test message content",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Test fact check",
            matched_source="https://example.com/fact-check",
            fact_check_item_id=uuid4(),
        )

        candidate = ScanCandidate(
            message=message,
            scan_type="similarity",
            match_data=similarity_match,
            score=0.85,
            matched_content="Test fact check content",
            matched_source="https://example.com/fact-check",
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False
            mock_settings.INSTANCE_ID = "test"

            flagged = await service._filter_candidates_with_relevance([candidate], uuid4())

        assert len(flagged) == 1
        assert flagged[0].message_id == "test_msg_3"


class TestRetryWithoutFactCheckEdgeCases:
    """Tests for _retry_without_fact_check edge cases."""

    @pytest.mark.asyncio
    async def test_retry_without_fact_check_returns_indeterminate_when_llm_service_none(
        self,
        mock_session,
    ) -> None:
        """When llm_service is None, should return INDETERMINATE."""
        import time

        from src.claim_relevance_check.service import ClaimRelevanceService

        service = ClaimRelevanceService(llm_service=None)

        outcome, reasoning = await service._retry_without_fact_check(
            db=mock_session,
            original_message="Test message",
            start_time=time.monotonic(),
        )

        assert outcome == RelevanceOutcome.INDETERMINATE
        assert "not configured" in reasoning.lower()


class TestFailOpenWithTighterThreshold:
    """Tests for fail-open behavior applying tighter threshold (task-973).

    When LLM fails (timeout, validation error, general error), the system now returns
    INDETERMINATE instead of RELEVANT. This ensures the tighter threshold formula
    (base_threshold + (1-base_threshold)/2) is applied, filtering low-confidence matches.

    For base threshold 0.6:
    - Tighter threshold = 0.6 + (1-0.6)/2 = 0.6 + 0.2 = 0.8
    - A 30% confidence message (0.3) is filtered (0.3 < 0.8)
    - A 90% confidence message (0.9) is flagged (0.9 >= 0.8)
    """

    @pytest.mark.asyncio
    async def test_fail_open_filters_low_confidence_message_on_timeout(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Timeout with 30% confidence → filtered (0.3 < 0.8 tighter threshold)."""
        import asyncio

        async def slow_complete(*args, **kwargs):
            await asyncio.sleep(10)
            return LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = slow_complete

        low_score_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["science"],
            title="Test Fact Check",
            content="Test content",
            summary="Test summary",
            rating="false",
            source_url="https://example.com",
            published_date=pendulum.now("UTC"),
            author="Tester",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.30,
        )

        message = BulkScanMessage(
            message_id="low_confidence_msg",
            channel_id="test_channel",
            community_server_id="test_server",
            content="Low confidence test message",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[low_score_match],
                total_matches=1,
                query_text=message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
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
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.6
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.INSTANCE_ID = "test"

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=message,
                community_server_platform_id="test_server",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_fail_open_filters_low_confidence_message_on_llm_error(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """LLM error with 30% confidence → filtered (0.3 < 0.8 tighter threshold)."""
        mock_llm_service.complete = AsyncMock(side_effect=Exception("LLM service unavailable"))

        low_score_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["science"],
            title="Test Fact Check",
            content="Test content",
            summary="Test summary",
            rating="false",
            source_url="https://example.com",
            published_date=pendulum.now("UTC"),
            author="Tester",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.30,
        )

        message = BulkScanMessage(
            message_id="low_confidence_msg",
            channel_id="test_channel",
            community_server_id="test_server",
            content="Low confidence test message",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[low_score_match],
                total_matches=1,
                query_text=message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
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
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.6
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.INSTANCE_ID = "test"

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=message,
                community_server_platform_id="test_server",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_fail_open_filters_low_confidence_message_on_validation_error(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Validation error with 30% confidence → filtered (0.3 < 0.8 tighter threshold)."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content="This is not valid JSON",
                model="openai/gpt-5-mini",
                tokens_used=10,
                finish_reason="stop",
                provider="openai",
            )
        )

        low_score_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["science"],
            title="Test Fact Check",
            content="Test content",
            summary="Test summary",
            rating="false",
            source_url="https://example.com",
            published_date=pendulum.now("UTC"),
            author="Tester",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.30,
        )

        message = BulkScanMessage(
            message_id="low_confidence_msg",
            channel_id="test_channel",
            community_server_id="test_server",
            content="Low confidence test message",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[low_score_match],
                total_matches=1,
                query_text=message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
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
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.6
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.INSTANCE_ID = "test"

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=message,
                community_server_platform_id="test_server",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_fail_open_flags_high_confidence_message_on_timeout(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Timeout with 90% confidence → flagged (0.9 >= 0.8 tighter threshold)."""
        import asyncio

        async def slow_complete(*args, **kwargs):
            await asyncio.sleep(10)
            return LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="openai/gpt-5-mini",
                tokens_used=20,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = slow_complete

        high_score_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["science"],
            title="Test Fact Check",
            content="Test content",
            summary="Test summary",
            rating="false",
            source_url="https://example.com",
            published_date=pendulum.now("UTC"),
            author="Tester",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.90,
        )

        message = BulkScanMessage(
            message_id="high_confidence_msg",
            channel_id="test_channel",
            community_server_id="test_server",
            content="High confidence test message",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[high_score_match],
                total_matches=1,
                query_text=message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
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
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.6
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.INSTANCE_ID = "test"

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=message,
                community_server_platform_id="test_server",
            )

        assert result is not None
        assert result.message_id == "high_confidence_msg"

    @pytest.mark.asyncio
    async def test_fail_open_uses_correct_tighter_threshold_formula(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Verify threshold math: 0.6 base → 0.8 tighter. Score 0.79 < 0.8 → filtered."""
        mock_llm_service.complete = AsyncMock(side_effect=Exception("LLM unavailable"))

        borderline_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["science"],
            title="Test Fact Check",
            content="Test content",
            summary="Test summary",
            rating="false",
            source_url="https://example.com",
            published_date=pendulum.now("UTC"),
            author="Tester",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.79,
        )

        message = BulkScanMessage(
            message_id="borderline_msg",
            channel_id="test_channel",
            community_server_id="test_server",
            content="Borderline confidence test message",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[borderline_match],
                total_matches=1,
                query_text=message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
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
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.6
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.INSTANCE_ID = "test"

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=message,
                community_server_platform_id="test_server",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_fail_open_flags_at_exact_tighter_threshold(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Score exactly at tighter threshold (0.8) → flagged (>= comparison)."""
        mock_llm_service.complete = AsyncMock(side_effect=Exception("LLM unavailable"))

        exact_threshold_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["science"],
            title="Test Fact Check",
            content="Test content",
            summary="Test summary",
            rating="false",
            source_url="https://example.com",
            published_date=pendulum.now("UTC"),
            author="Tester",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.80,
        )

        message = BulkScanMessage(
            message_id="exact_threshold_msg",
            channel_id="test_channel",
            community_server_id="test_server",
            content="Exact threshold test message",
            author_id="test_author",
            timestamp=pendulum.now("UTC"),
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[exact_threshold_match],
                total_matches=1,
                query_text=message.content,
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
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
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.6
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_MODEL = "openai/gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.INSTANCE_ID = "test"

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=message,
                community_server_platform_id="test_server",
            )

        assert result is not None
        assert result.message_id == "exact_threshold_msg"
