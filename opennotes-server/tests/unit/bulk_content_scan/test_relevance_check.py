"""Tests for LLM relevance check in bulk content scan.

These tests are written TDD-style before implementation exists.
They will initially fail until the relevance check feature is implemented.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.bulk_content_scan.schemas import BulkScanMessage, RelevanceOutcome
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
        timestamp=datetime.now(UTC),
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
        published_date=datetime.now(UTC),
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
    async def test_check_relevance_fails_open_on_llm_error(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When LLM call fails, should return RELEVANT (fail-open for safety)."""
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

        assert outcome == RelevanceOutcome.RELEVANT
        assert "error" in reasoning.lower() or "failed" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_check_relevance_fails_open_on_malformed_json(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When LLM returns malformed JSON, should return RELEVANT (fail-open)."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content="This is not valid JSON",
                model="gpt-5-mini",
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

        assert outcome == RelevanceOutcome.RELEVANT

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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
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
                model="gpt-5-mini",
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
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
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
    async def test_similarity_scan_flags_on_llm_error_fail_open(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        sample_message,
        sample_fact_check_match,
    ) -> None:
        """When LLM errors during relevance check, should still flag (fail-open)."""
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
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

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
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
    async def test_check_relevance_fails_open_on_timeout(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """When LLM call times out, should return RELEVANT (fail-open for safety)."""
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

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 0.1
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150

            outcome, reasoning = await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test matched content",
                matched_source="https://example.com",
            )

        assert outcome == RelevanceOutcome.RELEVANT
        assert "timed out" in reasoning.lower()

    @pytest.mark.asyncio
    async def test_check_relevance_uses_configured_provider(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
    ) -> None:
        """Should use RELEVANCE_CHECK_PROVIDER from settings."""
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({"is_relevant": True, "reasoning": "Test"}),
                model="gpt-5-mini",
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
            mock_settings.RELEVANCE_CHECK_PROVIDER = "anthropic"
            mock_settings.RELEVANCE_CHECK_MODEL = "claude-3-haiku"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0

            await service._check_relevance_with_llm(
                original_message="Test message",
                matched_content="Test content",
                matched_source=None,
            )

        call_args = mock_llm_service.complete.call_args
        assert call_args.kwargs.get("provider") == "anthropic"
        assert call_args.kwargs.get("model") == "claude-3-haiku"


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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
                model="gpt-5-mini",
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
                    model="gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            return LLMResponse(
                content=json.dumps({"has_claims": False, "reasoning": "No claims"}),
                model="gpt-5-mini",
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
                    model="gpt-5-mini",
                    tokens_used=0,
                    finish_reason="content_filter",
                    provider="openai",
                )
            await asyncio.sleep(10)
            return LLMResponse(
                content=json.dumps({"has_claims": True}),
                model="gpt-5-mini",
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
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
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
                    model="gpt-5-mini",
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
    async def test_indeterminate_outcome_does_not_flag(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_llm_service,
        sample_message,
        sample_fact_check_match,
    ) -> None:
        """When relevance check returns INDETERMINATE, should not flag the message."""
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
                content=json.dumps({"has_claims": True}),
                model="gpt-5-mini",
                tokens_used=15,
                finish_reason="stop",
                provider="openai",
            )

        mock_llm_service.complete = mock_complete
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

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.7
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 150
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 5.0
            mock_settings.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT = False

            result = await service._similarity_scan(
                scan_id=uuid4(),
                message=sample_message,
                community_server_platform_id="111222333",
            )

        assert result is None
