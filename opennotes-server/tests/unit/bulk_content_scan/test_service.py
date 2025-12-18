"""Tests for BulkContentScanService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


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
    """Create a mock Redis client for message collection."""
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    redis.lpush = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    redis.expire = AsyncMock()
    return redis


class TestBulkContentScanServiceInit:
    """Test service initialization."""

    def test_can_create_service(self, mock_session, mock_embedding_service, mock_redis):
        """Service should be instantiable with required dependencies."""
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        assert service.session == mock_session
        assert service.embedding_service == mock_embedding_service
        assert service.redis_client == mock_redis


class TestInitiateScan:
    """Test scan initiation."""

    @pytest.mark.asyncio
    async def test_initiate_scan_creates_log_entry(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #5: POST /bulk-content-scan/scans initiates scan and returns scan_id."""
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        community_server_id = uuid4()
        initiated_by_user_id = uuid4()

        mock_scan_log = MagicMock()
        mock_scan_log.id = uuid4()
        mock_scan_log.status = "pending"
        mock_scan_log.initiated_at = datetime.now(UTC)
        mock_scan_log.completed_at = None
        mock_scan_log.messages_scanned = 0
        mock_scan_log.messages_flagged = 0

        with patch(
            "src.bulk_content_scan.service.BulkContentScanLog",
            return_value=mock_scan_log,
        ):
            mock_session.refresh = AsyncMock(side_effect=lambda x: None)

            await service.initiate_scan(
                community_server_id=community_server_id,
                initiated_by_user_id=initiated_by_user_id,
                scan_window_days=7,
            )

        assert mock_session.add.called
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_initiate_scan_returns_scan_log(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Initiate scan should return the created scan log."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = "pending"

        with patch(
            "src.bulk_content_scan.service.BulkContentScanLog",
            return_value=mock_scan_log,
        ):
            result = await service.initiate_scan(
                community_server_id=uuid4(),
                initiated_by_user_id=uuid4(),
                scan_window_days=7,
            )

        assert result == mock_scan_log


class TestProcessMessages:
    """Test streaming message processing with process_messages()."""

    @pytest.mark.asyncio
    async def test_process_messages_single_message(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """process_messages should accept a single BulkScanMessage."""
        from src.bulk_content_scan.schemas import BulkScanMessage, FlaggedMessage
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
                rrf_score_threshold=0.1,
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
            timestamp=datetime.now(UTC),
        )

        result = await service.process_messages(
            scan_id=scan_id,
            messages=msg,
            platform_id="guild_123",
        )

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], FlaggedMessage)
        assert result[0].message_id == "msg_1"
        mock_embedding_service.similarity_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_messages_multiple_messages(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """process_messages should accept a sequence of messages."""
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
            content="Fact-check content",
            source_url="https://snopes.com/test",
            similarity_score=0.85,
        )
        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[mock_match],
                query_text="Test message",
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
                rrf_score_threshold=0.1,
                total_matches=1,
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        messages = [
            BulkScanMessage(
                message_id="msg_1",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Test message 1",
                author_id="user_1",
                timestamp=datetime.now(UTC),
            ),
            BulkScanMessage(
                message_id="msg_2",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Test message 2",
                author_id="user_2",
                timestamp=datetime.now(UTC),
            ),
        ]

        result = await service.process_messages(
            scan_id=scan_id,
            messages=messages,
            platform_id="guild_123",
        )

        assert isinstance(result, list)
        assert len(result) == 2
        assert mock_embedding_service.similarity_search.call_count == 2

    @pytest.mark.asyncio
    async def test_process_messages_skips_short_content(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Messages with content < 10 chars should be skipped."""
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService

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
            content="short",
            author_id="user_1",
            timestamp=datetime.now(UTC),
        )

        result = await service.process_messages(
            scan_id=scan_id,
            messages=msg,
            platform_id="guild_123",
        )

        assert result == []
        mock_embedding_service.similarity_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_messages_with_specific_scan_types(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """process_messages should accept scan_types parameter."""
        from src.bulk_content_scan.scan_types import ScanType
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
                rrf_score_threshold=0.1,
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
            timestamp=datetime.now(UTC),
        )

        result = await service.process_messages(
            scan_id=scan_id,
            messages=msg,
            platform_id="guild_123",
            scan_types=(ScanType.SIMILARITY,),
        )

        assert len(result) == 1
        assert result[0].scan_type == ScanType.SIMILARITY

    @pytest.mark.asyncio
    async def test_process_messages_with_empty_scan_types(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Empty scan_types should return empty results."""
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService

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
            timestamp=datetime.now(UTC),
        )

        result = await service.process_messages(
            scan_id=scan_id,
            messages=msg,
            platform_id="guild_123",
            scan_types=(),
        )

        assert result == []
        mock_embedding_service.similarity_search.assert_not_called()


class TestAppendFlaggedResult:
    """Test incremental result storage with append_flagged_result()."""

    @pytest.mark.asyncio
    async def test_append_flagged_result_stores_in_redis(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """append_flagged_result should use lpush to store in Redis."""
        from src.bulk_content_scan.schemas import FlaggedMessage
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        flagged_message = FlaggedMessage(
            message_id="msg_1",
            channel_id="ch_1",
            content="Test content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            match_score=0.85,
            matched_claim="Claim text",
            matched_source="https://example.com",
        )

        await service.append_flagged_result(scan_id=scan_id, flagged_message=flagged_message)

        mock_redis.lpush.assert_called_once()
        mock_redis.expire.assert_called_once()


class TestGetFlaggedResultsFromList:
    """Test retrieval of flagged results from Redis list format."""

    @pytest.mark.asyncio
    async def test_get_flagged_results_from_list(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """get_flagged_results should retrieve from lpush list format."""
        from src.bulk_content_scan.schemas import FlaggedMessage
        from src.bulk_content_scan.service import BulkContentScanService

        scan_id = uuid4()
        stored_messages = [
            FlaggedMessage(
                message_id="msg_1",
                channel_id="ch_1",
                content="Test",
                author_id="user_1",
                timestamp=datetime.now(UTC),
                match_score=0.85,
                matched_claim="Claim",
                matched_source="https://example.com",
            )
            .model_dump_json()
            .encode(),
            FlaggedMessage(
                message_id="msg_2",
                channel_id="ch_2",
                content="Test 2",
                author_id="user_2",
                timestamp=datetime.now(UTC),
                match_score=0.75,
                matched_claim="Claim 2",
                matched_source="https://example2.com",
            )
            .model_dump_json()
            .encode(),
        ]
        mock_redis.lrange = AsyncMock(return_value=stored_messages)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        results = await service.get_flagged_results(scan_id=scan_id)

        assert len(results) == 2
        assert isinstance(results[0], FlaggedMessage)
        assert results[0].message_id == "msg_1"
        assert results[1].message_id == "msg_2"
        mock_redis.lrange.assert_called_once()


class TestCompleteScan:
    """Test scan completion and logging."""

    @pytest.mark.asyncio
    async def test_complete_scan_updates_log(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #8: Scan completion logs entry to bulk_content_scan_log table."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = "in_progress"
        mock_scan_log.completed_at = None
        mock_session.get = AsyncMock(return_value=mock_scan_log)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        await service.complete_scan(
            scan_id=mock_scan_log.id,
            messages_scanned=100,
            messages_flagged=5,
        )

        assert mock_scan_log.status == "completed"
        assert mock_scan_log.completed_at is not None
        assert mock_scan_log.messages_scanned == 100
        assert mock_scan_log.messages_flagged == 5
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_complete_scan_does_not_clean_up_messages_key(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Completion should not clean up messages key (we no longer store raw messages)."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_session.get = AsyncMock(return_value=mock_scan_log)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        await service.complete_scan(
            scan_id=scan_id,
            messages_scanned=50,
            messages_flagged=2,
        )

        mock_redis.delete.assert_not_called()


class TestGetScanResults:
    """Test retrieving scan results."""

    @pytest.mark.asyncio
    async def test_get_scan_results_returns_scan_log(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #6: GET /bulk-content-scan/scans/{scan_id} returns status."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = "completed"
        mock_scan_log.messages_scanned = 100
        mock_scan_log.messages_flagged = 5
        mock_session.get = AsyncMock(return_value=mock_scan_log)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        result = await service.get_scan(scan_id=mock_scan_log.id)

        assert result == mock_scan_log
        mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_scan_returns_none_for_missing(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Get scan should return None if scan not found."""
        from src.bulk_content_scan.service import BulkContentScanService

        mock_session.get = AsyncMock(return_value=None)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        result = await service.get_scan(scan_id=uuid4())

        assert result is None


class TestStoreFlaggedResults:
    """Test storing flagged results in Redis list for retrieval."""

    @pytest.mark.asyncio
    async def test_store_flagged_results_in_redis_list(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Flagged results should be stored in Redis list for later retrieval."""
        from src.bulk_content_scan.schemas import FlaggedMessage
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        flagged_messages = [
            FlaggedMessage(
                message_id="msg_1",
                channel_id="ch_1",
                content="Test",
                author_id="user_1",
                timestamp=datetime.now(UTC),
                match_score=0.85,
                matched_claim="Claim",
                matched_source="https://example.com",
            )
        ]

        await service.store_flagged_results(scan_id=scan_id, flagged_messages=flagged_messages)

        mock_redis.lpush.assert_called()
        mock_redis.expire.assert_called()
