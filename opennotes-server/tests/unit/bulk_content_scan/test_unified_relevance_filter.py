"""Tests for unified LLM relevance check as final filter for all scan candidates.

Task-953: All scan paths should produce candidates, and ALL candidates should pass
through the LLM relevance check as a unified final filter before being marked as flagged.

TDD: These tests are written BEFORE implementation to define expected behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pendulum
import pytest

from src.bulk_content_scan.scan_types import ScanType


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
def mock_moderation_service():
    """Create a mock OpenAI moderation service."""
    return AsyncMock()


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service for relevance checking."""
    return AsyncMock()


class TestScanCandidateSchema:
    """Test the ScanCandidate dataclass exists and has correct structure."""

    def test_scan_candidate_schema_exists(self):
        """AC #1: ScanCandidate schema should exist for internal candidate tracking."""
        from src.bulk_content_scan.schemas import ScanCandidate

        assert ScanCandidate is not None

    def test_scan_candidate_has_required_fields(self):
        """AC #1: ScanCandidate should have message, scan_type, match_data, score, matched_content."""
        from src.bulk_content_scan.scan_types import ScanType
        from src.bulk_content_scan.schemas import BulkScanMessage, ScanCandidate, SimilarityMatch

        msg = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Test content for candidate",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        match = SimilarityMatch(
            score=0.85,
            matched_claim="Test claim",
            matched_source="https://example.com",
        )

        candidate = ScanCandidate(
            message=msg,
            scan_type=ScanType.SIMILARITY,
            match_data=match,
            score=0.85,
            matched_content="Test claim content",
            matched_source="https://example.com",
        )

        assert candidate.message == msg
        assert candidate.scan_type == ScanType.SIMILARITY
        assert candidate.match_data == match
        assert candidate.score == 0.85
        assert candidate.matched_content == "Test claim content"
        assert candidate.matched_source == "https://example.com"


class TestSimilarityScanReturnsCandidate:
    """Test that similarity scan produces candidates instead of directly flagging."""

    @pytest.mark.asyncio
    async def test_similarity_scan_returns_candidate_not_flagged_message(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #1: _similarity_scan_candidate() returns ScanCandidate instead of FlaggedMessage."""
        from src.bulk_content_scan.schemas import BulkScanMessage, ScanCandidate
        from src.bulk_content_scan.service import BulkContentScanService
        from src.fact_checking.embedding_schemas import (
            FactCheckMatch,
            SimilaritySearchResponse,
        )

        mock_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["snopes"],
            title="Test Fact Check",
            content="Original claim content",
            source_url="https://snopes.com/test",
            similarity_score=0.85,
        )
        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[mock_match],
                query_text="Test message content",
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
                score_threshold=0.1,
                total_matches=1,
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        msg = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Test message content",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        candidate = await service._similarity_scan_candidate(
            scan_id=scan_id,
            message=msg,
            community_server_platform_id="guild_123",
        )

        assert candidate is not None
        assert isinstance(candidate, ScanCandidate)
        assert candidate.scan_type == ScanType.SIMILARITY
        assert candidate.score == 0.85

    @pytest.mark.asyncio
    async def test_similarity_scan_candidate_does_not_run_relevance_check(
        self, mock_session, mock_embedding_service, mock_redis, mock_llm_service
    ):
        """AC #1: _similarity_scan_candidate() should NOT run LLM relevance check inline."""
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService
        from src.fact_checking.embedding_schemas import (
            FactCheckMatch,
            SimilaritySearchResponse,
        )

        mock_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["snopes"],
            title="Test Fact Check",
            content="Original claim content",
            source_url="https://snopes.com/test",
            similarity_score=0.85,
        )
        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[mock_match],
                query_text="Test message content",
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
                score_threshold=0.1,
                total_matches=1,
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        scan_id = uuid4()
        msg = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Test message content",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        await service._similarity_scan_candidate(
            scan_id=scan_id,
            message=msg,
            community_server_platform_id="guild_123",
        )

        mock_llm_service.complete.assert_not_called()


class TestModerationScanReturnsCandidate:
    """Test that OpenAI moderation scan produces candidates."""

    @pytest.mark.asyncio
    async def test_moderation_scan_returns_candidate(
        self, mock_session, mock_embedding_service, mock_redis, mock_moderation_service
    ):
        """AC #1, AC #3: _moderation_scan_candidate() returns ScanCandidate."""
        from src.bulk_content_scan.schemas import BulkScanMessage, ScanCandidate
        from src.bulk_content_scan.service import BulkContentScanService

        mock_moderation_result = MagicMock()
        mock_moderation_result.flagged = True
        mock_moderation_result.max_score = 0.95
        mock_moderation_result.categories = {"hate": True, "violence": False}
        mock_moderation_result.scores = {"hate": 0.95, "violence": 0.1}
        mock_moderation_result.flagged_categories = ["hate"]

        mock_moderation_service.moderate_text = AsyncMock(return_value=mock_moderation_result)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            moderation_service=mock_moderation_service,
        )

        scan_id = uuid4()
        msg = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Test message with hate speech content",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        candidate = await service._moderation_scan_candidate(
            scan_id=scan_id,
            message=msg,
        )

        assert candidate is not None
        assert isinstance(candidate, ScanCandidate)
        assert candidate.scan_type == ScanType.OPENAI_MODERATION
        assert candidate.score == 0.95


class TestUnifiedRelevanceFilter:
    """Test unified relevance check runs on ALL candidates."""

    @pytest.mark.asyncio
    async def test_filter_candidates_runs_relevance_on_all_types(
        self, mock_session, mock_embedding_service, mock_redis, mock_llm_service
    ):
        """AC #2, AC #3: _filter_candidates_with_relevance() runs on ALL candidates including moderation."""
        from src.bulk_content_scan.schemas import (
            BulkScanMessage,
            OpenAIModerationMatch,
            ScanCandidate,
            SimilarityMatch,
        )
        from src.bulk_content_scan.service import BulkContentScanService

        mock_llm_response = MagicMock()
        mock_llm_response.content = '{"is_relevant": true, "reasoning": "Contains a claim"}'
        mock_llm_service.complete = AsyncMock(return_value=mock_llm_response)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        scan_id = uuid4()

        msg1 = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Biden was a Confederate soldier",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        msg2 = BulkScanMessage(
            message_id="msg_2",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Hate speech content here",
            author_id="user_2",
            timestamp=pendulum.now("UTC"),
        )

        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Biden history claim",
            matched_source="https://factcheck.com",
        )

        moderation_match = OpenAIModerationMatch(
            max_score=0.95,
            categories={"hate": True},
            scores={"hate": 0.95},
            flagged_categories=["hate"],
        )

        candidates = [
            ScanCandidate(
                message=msg1,
                scan_type=ScanType.SIMILARITY,
                match_data=similarity_match,
                score=0.85,
                matched_content="Biden history claim",
                matched_source="https://factcheck.com",
            ),
            ScanCandidate(
                message=msg2,
                scan_type=ScanType.OPENAI_MODERATION,
                match_data=moderation_match,
                score=0.95,
                matched_content="hate",
                matched_source=None,
            ),
        ]

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 100
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 10
            mock_settings.INSTANCE_ID = "test"

            flagged = await service._filter_candidates_with_relevance(
                candidates=candidates,
                scan_id=scan_id,
            )

        assert mock_llm_service.complete.call_count == 2
        assert len(flagged) == 2


class TestUpdatedRelevancePrompt:
    """Test that the updated relevance prompt requires claims, not just topic matches."""

    @pytest.mark.asyncio
    async def test_non_claim_message_filtered_by_relevance(
        self, mock_session, mock_embedding_service, mock_redis, mock_llm_service
    ):
        """AC #8: Messages without claims should be filtered out by relevance check."""
        from src.bulk_content_scan.schemas import BulkScanMessage, ScanCandidate, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        mock_llm_response = MagicMock()
        mock_llm_response.content = (
            '{"is_relevant": false, "reasoning": "No verifiable claim, just a name mention"}'
        )
        mock_llm_service.complete = AsyncMock(return_value=mock_llm_response)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        scan_id = uuid4()

        msg = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="how about biden",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        similarity_match = SimilarityMatch(
            score=0.43,
            matched_claim="Biden fact-check about something",
            matched_source="https://factcheck.com",
        )

        candidates = [
            ScanCandidate(
                message=msg,
                scan_type=ScanType.SIMILARITY,
                match_data=similarity_match,
                score=0.43,
                matched_content="Biden fact-check about something",
                matched_source="https://factcheck.com",
            ),
        ]

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 100
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 10
            mock_settings.INSTANCE_ID = "test"

            flagged = await service._filter_candidates_with_relevance(
                candidates=candidates,
                scan_id=scan_id,
            )

        assert len(flagged) == 0

    @pytest.mark.asyncio
    async def test_claim_message_passes_relevance(
        self, mock_session, mock_embedding_service, mock_redis, mock_llm_service
    ):
        """AC #8: Messages with verifiable claims should pass relevance check."""
        from src.bulk_content_scan.schemas import BulkScanMessage, ScanCandidate, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        mock_llm_response = MagicMock()
        mock_llm_response.content = '{"is_relevant": true, "reasoning": "Contains verifiable claim about Biden being Confederate soldier"}'
        mock_llm_service.complete = AsyncMock(return_value=mock_llm_response)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        scan_id = uuid4()

        msg = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Biden was a Confederate soldier",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Biden Confederate claim fact-check",
            matched_source="https://factcheck.com",
        )

        candidates = [
            ScanCandidate(
                message=msg,
                scan_type=ScanType.SIMILARITY,
                match_data=similarity_match,
                score=0.85,
                matched_content="Biden Confederate claim fact-check",
                matched_source="https://factcheck.com",
            ),
        ]

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 100
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 10
            mock_settings.INSTANCE_ID = "test"

            flagged = await service._filter_candidates_with_relevance(
                candidates=candidates,
                scan_id=scan_id,
            )

        assert len(flagged) == 1


class TestDebugModeUnification:
    """Test that debug mode uses same filtering logic as non-debug mode."""

    @pytest.mark.asyncio
    async def test_debug_mode_uses_same_filtering_as_non_debug(
        self, mock_session, mock_embedding_service, mock_redis, mock_llm_service
    ):
        """AC #6: Debug mode should only affect logging, not processing logic."""
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService
        from src.fact_checking.embedding_schemas import (
            FactCheckMatch,
            SimilaritySearchResponse,
        )

        mock_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["snopes"],
            title="Test Fact Check",
            content="Original claim content",
            source_url="https://snopes.com/test",
            similarity_score=0.85,
        )
        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[mock_match],
                query_text="Test message content",
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
                score_threshold=0.1,
                total_matches=1,
            )
        )

        mock_llm_response = MagicMock()
        mock_llm_response.content = '{"is_relevant": false, "reasoning": "No claim"}'
        mock_llm_service.complete = AsyncMock(return_value=mock_llm_response)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        scan_id = uuid4()
        msg = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="how about biden",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 100
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 10
            mock_settings.INSTANCE_ID = "test"
            mock_settings.SIMILARITY_SEARCH_DEFAULT_THRESHOLD = 0.6

            flagged_normal = await service.process_messages(
                scan_id=scan_id,
                messages=msg,
                community_server_platform_id="guild_123",
            )

            flagged_debug, _scores = await service.process_messages_with_scores(
                scan_id=scan_id,
                messages=msg,
                community_server_platform_id="guild_123",
            )

        assert len(flagged_normal) == len(flagged_debug)


class TestCandidateFlaggedLogging:
    """Test logging of candidates vs flagged messages."""

    @pytest.mark.asyncio
    async def test_filter_logs_candidate_and_flagged_counts(
        self, mock_session, mock_embedding_service, mock_redis, mock_llm_service
    ):
        """AC #4: Should log candidates_count vs flagged_count after filtering."""
        from src.bulk_content_scan.schemas import BulkScanMessage, ScanCandidate, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        mock_llm_response = MagicMock()
        mock_llm_response.content = '{"is_relevant": true, "reasoning": "Has claim"}'
        mock_llm_service.complete = AsyncMock(return_value=mock_llm_response)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm_service,
        )

        scan_id = uuid4()

        msg = BulkScanMessage(
            message_id="msg_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Biden was a Confederate soldier",
            author_id="user_1",
            timestamp=pendulum.now("UTC"),
        )

        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Biden fact-check",
            matched_source="https://factcheck.com",
        )

        candidates = [
            ScanCandidate(
                message=msg,
                scan_type=ScanType.SIMILARITY,
                match_data=similarity_match,
                score=0.85,
                matched_content="Biden fact-check",
                matched_source="https://factcheck.com",
            ),
        ]

        with (
            patch("src.bulk_content_scan.service.settings") as mock_settings,
            patch("src.bulk_content_scan.service.logger") as mock_logger,
        ):
            mock_settings.RELEVANCE_CHECK_ENABLED = True
            mock_settings.RELEVANCE_CHECK_PROVIDER = "openai"
            mock_settings.RELEVANCE_CHECK_MODEL = "gpt-5-mini"
            mock_settings.RELEVANCE_CHECK_MAX_TOKENS = 100
            mock_settings.RELEVANCE_CHECK_TIMEOUT = 10
            mock_settings.INSTANCE_ID = "test"

            await service._filter_candidates_with_relevance(
                candidates=candidates,
                scan_id=scan_id,
            )

            log_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any(
                "Relevance filtering complete" in call or "candidates_count" in call
                for call in log_calls
            )
