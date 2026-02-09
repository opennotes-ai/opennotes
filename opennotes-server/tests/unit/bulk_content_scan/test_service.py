"""Tests for BulkContentScanService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

SAMPLE_FACT_CHECK_ID = UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()

    mock_execute_result = MagicMock()
    mock_execute_result.fetchall = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=mock_execute_result)

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


class TestParameterNaming:
    """Test that parameter naming follows project conventions (task-849.16)."""

    def test_process_messages_uses_community_server_platform_id_parameter(self):
        """Verify process_messages uses community_server_platform_id, not platform_id.

        The parameter should be named community_server_platform_id to clarify it
        corresponds to CommunityServer.platform_community_server_id (the Discord guild ID).
        """
        import inspect

        from src.bulk_content_scan.service import BulkContentScanService

        sig = inspect.signature(BulkContentScanService.process_messages)
        param_names = list(sig.parameters.keys())

        assert "community_server_platform_id" in param_names, (
            f"process_messages should have 'community_server_platform_id' parameter, "
            f"but found: {param_names}"
        )
        assert "platform_id" not in param_names, (
            "process_messages should NOT have 'platform_id' parameter "
            "(use 'community_server_platform_id' instead)"
        )


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
            timestamp=datetime.now(UTC),
        )

        result = await service.process_messages(
            scan_id=scan_id,
            messages=msg,
            community_server_platform_id="guild_123",
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
            community_server_platform_id="guild_123",
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
            community_server_platform_id="guild_123",
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
            timestamp=datetime.now(UTC),
        )

        result = await service.process_messages(
            scan_id=scan_id,
            messages=msg,
            community_server_platform_id="guild_123",
            scan_types=(ScanType.SIMILARITY,),
        )

        assert len(result) == 1
        assert len(result[0].matches) >= 1
        assert result[0].matches[0].scan_type == "similarity"

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
            community_server_platform_id="guild_123",
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
        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim text",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged_message = FlaggedMessage(
            message_id="msg_1",
            channel_id="ch_1",
            content="Test content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[similarity_match],
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
        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        scan_id = uuid4()
        similarity_match_1 = SimilarityMatch(
            score=0.85,
            matched_claim="Claim",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        similarity_match_2 = SimilarityMatch(
            score=0.75,
            matched_claim="Claim 2",
            matched_source="https://example2.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        stored_messages = [
            FlaggedMessage(
                message_id="msg_1",
                channel_id="ch_1",
                content="Test",
                author_id="user_1",
                timestamp=datetime.now(UTC),
                matches=[similarity_match_1],
            )
            .model_dump_json()
            .encode(),
            FlaggedMessage(
                message_id="msg_2",
                channel_id="ch_2",
                content="Test 2",
                author_id="user_2",
                timestamp=datetime.now(UTC),
                matches=[similarity_match_2],
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

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
        mock_session.execute = AsyncMock(return_value=mock_result)

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

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
        mock_session.execute = AsyncMock(return_value=mock_result)

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
        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged_messages = [
            FlaggedMessage(
                message_id="msg_1",
                channel_id="ch_1",
                content="Test",
                author_id="user_1",
                timestamp=datetime.now(UTC),
                matches=[similarity_match],
            )
        ]

        await service.store_flagged_results(scan_id=scan_id, flagged_messages=flagged_messages)

        mock_redis.lpush.assert_called()
        mock_redis.expire.assert_called()


class TestCompleteScanRowLocking:
    """Test row-level locking in complete_scan() - task-849.06."""

    @pytest.mark.asyncio
    async def test_complete_scan_uses_for_update_locking(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #1: complete_scan() uses with_for_update() for row-level locking."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = "in_progress"
        mock_scan_log.completed_at = None

        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=capture_execute)

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

        assert captured_stmt is not None, "session.execute() should have been called"
        assert hasattr(captured_stmt, "_for_update_arg"), (
            "Statement should be a SQLAlchemy select with for_update capability"
        )
        assert captured_stmt._for_update_arg is not None, (
            "Statement should have with_for_update() applied for row-level locking"
        )

    @pytest.mark.asyncio
    async def test_complete_scan_handles_nonexistent_scan_gracefully(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #2: Concurrent completion attempts are handled gracefully.

        When a scan is not found (e.g., already deleted or never existed),
        the method should not raise an exception and should not commit.
        """
        from src.bulk_content_scan.service import BulkContentScanService

        async def return_none_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=None)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=return_none_execute)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        await service.complete_scan(
            scan_id=uuid4(),
            messages_scanned=100,
            messages_flagged=5,
        )

        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_scan_commits_after_update_with_lock(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #3: Tests verify correct behavior - lock acquired, update made, commit called."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = "in_progress"
        mock_scan_log.completed_at = None

        async def return_scan_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=return_scan_execute)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        await service.complete_scan(
            scan_id=mock_scan_log.id,
            messages_scanned=100,
            messages_flagged=5,
            status=BulkScanStatus.COMPLETED,
        )

        assert mock_scan_log.status == BulkScanStatus.COMPLETED
        assert mock_scan_log.messages_scanned == 100
        assert mock_scan_log.messages_flagged == 5
        assert mock_scan_log.completed_at is not None
        mock_session.commit.assert_called_once()


class TestInitiateScanWithZeroMessages:
    """Test immediate completion when expected_messages=0 (task-855 AC#6)."""

    @pytest.mark.asyncio
    async def test_initiate_scan_with_zero_expected_messages_is_immediately_completed(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #6: When expected_messages=0, scan should be immediately marked as completed.

        This handles the case where Discord finds 0 scannable messages (all filtered
        out as bots/empty). The scan should not be left in "pending" status waiting
        for batch processing that will never happen.
        """
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        captured_kwargs = {}

        def capture_scan_log(*args, **kwargs):
            captured_kwargs.update(kwargs)
            mock_log = MagicMock()
            mock_log.id = uuid4()
            return mock_log

        with patch(
            "src.bulk_content_scan.service.BulkContentScanLog",
            side_effect=capture_scan_log,
        ):
            service = BulkContentScanService(
                session=mock_session,
                embedding_service=mock_embedding_service,
                redis_client=mock_redis,
            )

            await service.initiate_scan(
                community_server_id=uuid4(),
                initiated_by_user_id=uuid4(),
                scan_window_days=7,
                expected_messages=0,
            )

        assert "status" in captured_kwargs, "status should be passed to BulkContentScanLog"
        assert captured_kwargs["status"] == BulkScanStatus.COMPLETED, (
            f"status should be COMPLETED when expected_messages=0, got {captured_kwargs['status']}"
        )
        assert "completed_at" in captured_kwargs, (
            "completed_at should be set when expected_messages=0"
        )
        assert captured_kwargs["completed_at"] is not None, (
            "completed_at should not be None when expected_messages=0"
        )
        assert captured_kwargs.get("messages_scanned") == 0, (
            "messages_scanned should be 0 when expected_messages=0"
        )
        assert captured_kwargs.get("messages_flagged") == 0, (
            "messages_flagged should be 0 when expected_messages=0"
        )

    @pytest.mark.asyncio
    async def test_initiate_scan_with_nonzero_expected_messages_stays_pending(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """When expected_messages > 0, scan should remain in PENDING status."""
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        captured_kwargs = {}

        def capture_scan_log(*args, **kwargs):
            captured_kwargs.update(kwargs)
            mock_log = MagicMock()
            mock_log.id = uuid4()
            return mock_log

        with patch(
            "src.bulk_content_scan.service.BulkContentScanLog",
            side_effect=capture_scan_log,
        ):
            service = BulkContentScanService(
                session=mock_session,
                embedding_service=mock_embedding_service,
                redis_client=mock_redis,
            )

            await service.initiate_scan(
                community_server_id=uuid4(),
                initiated_by_user_id=uuid4(),
                scan_window_days=7,
                expected_messages=100,
            )

        assert captured_kwargs["status"] == BulkScanStatus.PENDING, (
            f"status should be PENDING when expected_messages > 0, got {captured_kwargs['status']}"
        )
        assert captured_kwargs.get("completed_at") is None, (
            "completed_at should be None when expected_messages > 0"
        )

    @pytest.mark.asyncio
    async def test_initiate_scan_without_expected_messages_stays_pending(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """When expected_messages is not provided (None), scan should remain PENDING."""
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        captured_kwargs = {}

        def capture_scan_log(*args, **kwargs):
            captured_kwargs.update(kwargs)
            mock_log = MagicMock()
            mock_log.id = uuid4()
            return mock_log

        with patch(
            "src.bulk_content_scan.service.BulkContentScanLog",
            side_effect=capture_scan_log,
        ):
            service = BulkContentScanService(
                session=mock_session,
                embedding_service=mock_embedding_service,
                redis_client=mock_redis,
            )

            await service.initiate_scan(
                community_server_id=uuid4(),
                initiated_by_user_id=uuid4(),
                scan_window_days=7,
            )

        assert captured_kwargs["status"] == BulkScanStatus.PENDING, (
            f"status should be PENDING when expected_messages not provided, got {captured_kwargs['status']}"
        )


class TestBulkScanStatusEnumUsage:
    """Test that BulkScanStatus enum is used consistently instead of string literals."""

    @pytest.mark.asyncio
    async def test_initiate_scan_uses_enum_for_status(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """initiate_scan should pass BulkScanStatus enum value, not string literal."""
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        captured_kwargs = {}

        def capture_scan_log(*args, **kwargs):
            captured_kwargs.update(kwargs)
            mock_log = MagicMock()
            mock_log.id = uuid4()
            return mock_log

        with patch(
            "src.bulk_content_scan.service.BulkContentScanLog",
            side_effect=capture_scan_log,
        ):
            service = BulkContentScanService(
                session=mock_session,
                embedding_service=mock_embedding_service,
                redis_client=mock_redis,
            )

            await service.initiate_scan(
                community_server_id=uuid4(),
                initiated_by_user_id=uuid4(),
                scan_window_days=7,
            )

        assert "status" in captured_kwargs, "status should be passed to BulkContentScanLog"
        assert isinstance(captured_kwargs["status"], BulkScanStatus), (
            f"status should be BulkScanStatus enum, got {type(captured_kwargs['status'])}"
        )
        assert captured_kwargs["status"] == BulkScanStatus.PENDING

    @pytest.mark.asyncio
    async def test_complete_scan_accepts_enum_status(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """complete_scan should accept BulkScanStatus enum for status parameter."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = BulkScanStatus.IN_PROGRESS

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        await service.complete_scan(
            scan_id=mock_scan_log.id,
            messages_scanned=100,
            messages_flagged=5,
            status=BulkScanStatus.COMPLETED,
        )

        assert mock_scan_log.status == BulkScanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_complete_scan_accepts_failed_status(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """complete_scan should accept BulkScanStatus.FAILED for error cases."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = BulkScanStatus.IN_PROGRESS

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        await service.complete_scan(
            scan_id=mock_scan_log.id,
            messages_scanned=50,
            messages_flagged=0,
            status=BulkScanStatus.FAILED,
        )

        assert mock_scan_log.status == BulkScanStatus.FAILED

    @pytest.mark.asyncio
    async def test_complete_scan_default_status_is_completed_enum(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """complete_scan default status should be BulkScanStatus.COMPLETED enum value."""
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = BulkScanStatus.IN_PROGRESS

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
        mock_session.execute = AsyncMock(return_value=mock_result)

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

        assert mock_scan_log.status == BulkScanStatus.COMPLETED
        assert isinstance(mock_scan_log.status, BulkScanStatus)


class TestRedisKeyEnvironmentPrefix:
    """Test Redis key prefixing for environment isolation - task-849.14."""

    @pytest.mark.asyncio
    async def test_redis_key_includes_environment_prefix(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #1: Redis keys include environment prefix (e.g., prod:bulk_scan:, staging:bulk_scan:)."""
        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim text",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged_message = FlaggedMessage(
            message_id="msg_1",
            channel_id="ch_1",
            content="Test content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[similarity_match],
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            await service.append_flagged_result(scan_id=scan_id, flagged_message=flagged_message)

        redis_key_used = mock_redis.lpush.call_args[0][0]
        assert redis_key_used.startswith("production:"), (
            f"Redis key should start with environment prefix 'production:', got: {redis_key_used}"
        )
        assert "bulk_scan" in redis_key_used, (
            f"Redis key should contain 'bulk_scan', got: {redis_key_used}"
        )

    @pytest.mark.asyncio
    async def test_redis_key_prefix_changes_with_environment(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #2: Prefix is configurable via environment variable."""
        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim text",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged_message = FlaggedMessage(
            message_id="msg_1",
            channel_id="ch_1",
            content="Test content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[similarity_match],
        )

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "staging"
            await service.append_flagged_result(scan_id=scan_id, flagged_message=flagged_message)

        redis_key_used = mock_redis.lpush.call_args[0][0]
        assert redis_key_used.startswith("staging:"), (
            f"Redis key should start with 'staging:' when ENVIRONMENT=staging, got: {redis_key_used}"
        )

    @pytest.mark.asyncio
    async def test_get_flagged_results_uses_environment_prefix(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """get_flagged_results should use environment-prefixed key."""
        from src.bulk_content_scan.service import BulkContentScanService

        mock_redis.lrange = AsyncMock(return_value=[])

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "test"
            await service.get_flagged_results(scan_id=scan_id)

        redis_key_used = mock_redis.lrange.call_args[0][0]
        assert redis_key_used.startswith("test:"), (
            f"Redis key should start with 'test:' when ENVIRONMENT=test, got: {redis_key_used}"
        )

    @pytest.mark.asyncio
    async def test_store_flagged_results_uses_environment_prefix(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """store_flagged_results should use environment-prefixed key."""
        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged_messages = [
            FlaggedMessage(
                message_id="msg_1",
                channel_id="ch_1",
                content="Test",
                author_id="user_1",
                timestamp=datetime.now(UTC),
                matches=[similarity_match],
            )
        ]

        with patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "development"
            await service.store_flagged_results(scan_id=scan_id, flagged_messages=flagged_messages)

        redis_key_used = mock_redis.lpush.call_args[0][0]
        assert redis_key_used.startswith("development:"), (
            f"Redis key should start with 'development:', got: {redis_key_used}"
        )


class TestRedisErrorPropagation:
    """Test that Redis errors propagate correctly for caller handling - task-849.19."""

    @pytest.mark.asyncio
    async def test_append_flagged_result_propagates_redis_connection_error(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #4: Redis connection errors should propagate for caller handling.

        When Redis is unavailable, the exception should propagate up so that
        the NATS handler can NAK the message for retry.
        """
        from redis.exceptions import ConnectionError as RedisConnectionError

        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        mock_redis.lpush = AsyncMock(side_effect=RedisConnectionError("Connection refused"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim text",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged_message = FlaggedMessage(
            message_id="msg_1",
            channel_id="ch_1",
            content="Test content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[similarity_match],
        )

        with pytest.raises(RedisConnectionError):
            await service.append_flagged_result(scan_id=scan_id, flagged_message=flagged_message)

    @pytest.mark.asyncio
    async def test_get_flagged_results_propagates_redis_connection_error(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #4: Redis connection errors should propagate for caller handling."""
        from redis.exceptions import ConnectionError as RedisConnectionError

        from src.bulk_content_scan.service import BulkContentScanService

        mock_redis.lrange = AsyncMock(side_effect=RedisConnectionError("Connection refused"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        with pytest.raises(RedisConnectionError):
            await service.get_flagged_results(scan_id=uuid4())

    @pytest.mark.asyncio
    async def test_store_flagged_results_propagates_redis_connection_error(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #4: Redis connection errors should propagate for caller handling."""
        from redis.exceptions import ConnectionError as RedisConnectionError

        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        mock_redis.lpush = AsyncMock(side_effect=RedisConnectionError("Connection refused"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged_messages = [
            FlaggedMessage(
                message_id="msg_1",
                channel_id="ch_1",
                content="Test",
                author_id="user_1",
                timestamp=datetime.now(UTC),
                matches=[similarity_match],
            )
        ]

        with pytest.raises(RedisConnectionError):
            await service.store_flagged_results(scan_id=uuid4(), flagged_messages=flagged_messages)

    @pytest.mark.asyncio
    async def test_redis_timeout_error_propagates(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #4: Redis timeout errors should propagate for caller handling."""
        from redis.exceptions import TimeoutError as RedisTimeoutError

        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import BulkContentScanService

        mock_redis.lpush = AsyncMock(side_effect=RedisTimeoutError("Operation timed out"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim text",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged_message = FlaggedMessage(
            message_id="msg_1",
            channel_id="ch_1",
            content="Test content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[similarity_match],
        )

        with pytest.raises(RedisTimeoutError):
            await service.append_flagged_result(scan_id=uuid4(), flagged_message=flagged_message)


class TestEmbeddingServiceErrorHandling:
    """Test embedding service error handling in similarity scan - task-849.19."""

    @pytest.mark.asyncio
    async def test_similarity_scan_handles_embedding_error_gracefully(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #3: Embedding service errors should be caught and logged, message skipped.

        The _similarity_scan method should catch exceptions from the embedding
        service, log them, and return None (skip the message) rather than
        propagating the error and failing the entire scan.
        """
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService

        mock_embedding_service.similarity_search = AsyncMock(
            side_effect=Exception("Embedding service unavailable")
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
            content="Test message content that should trigger embedding search",
            author_id="user_1",
            timestamp=datetime.now(UTC),
        )

        result = await service.process_messages(
            scan_id=scan_id,
            messages=msg,
            community_server_platform_id="guild_123",
        )

        assert result == [], "Message should be skipped when embedding service fails"
        mock_embedding_service.similarity_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_embedding_error_doesnt_stop_batch_processing(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #3: Embedding errors on one message shouldn't stop processing others.

        When the embedding service fails for one message, subsequent messages
        should still be processed.
        """
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService
        from src.fact_checking.embedding_schemas import (
            FactCheckMatch,
            SimilaritySearchResponse,
        )

        call_count = 0

        async def conditional_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First message fails")

            mock_match = FactCheckMatch(
                id=uuid4(),
                dataset_name="snopes",
                dataset_tags=["snopes"],
                title="Test Fact Check",
                content="Claim content",
                source_url="https://snopes.com/test",
                similarity_score=0.85,
            )
            return SimilaritySearchResponse(
                matches=[mock_match],
                query_text="Test message",
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
                score_threshold=0.1,
                total_matches=1,
            )

        mock_embedding_service.similarity_search = AsyncMock(side_effect=conditional_failure)

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
                content="First message that will fail embedding",
                author_id="user_1",
                timestamp=datetime.now(UTC),
            ),
            BulkScanMessage(
                message_id="msg_2",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Second message that should succeed",
                author_id="user_2",
                timestamp=datetime.now(UTC),
            ),
        ]

        result = await service.process_messages(
            scan_id=scan_id,
            messages=messages,
            community_server_platform_id="guild_123",
        )

        assert len(result) == 1, "Second message should still be processed"
        assert result[0].message_id == "msg_2"
        assert mock_embedding_service.similarity_search.call_count == 2


class TestConcurrentCompleteScanBehavior:
    """Test concurrent complete_scan() behavior - task-849.19."""

    @pytest.mark.asyncio
    async def test_complete_scan_already_completed_returns_gracefully(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #5: Second complete_scan() call on already-completed scan should be safe.

        If a scan is already completed (e.g., by a concurrent call), subsequent
        calls should handle this gracefully without errors.
        """
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = BulkScanStatus.COMPLETED
        mock_scan_log.completed_at = datetime.now(UTC)
        mock_scan_log.messages_scanned = 100
        mock_scan_log.messages_flagged = 5

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
        mock_session.execute = AsyncMock(return_value=mock_result)

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

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_scan_lock_prevents_concurrent_modification(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #5: The FOR UPDATE lock ensures only one concurrent completion succeeds.

        This test verifies the behavior when two complete_scan calls would
        happen concurrently: the second should wait for the lock and then
        find the record already updated.
        """
        from src.bulk_content_scan.models import BulkContentScanLog
        from src.bulk_content_scan.schemas import BulkScanStatus
        from src.bulk_content_scan.service import BulkContentScanService

        original_status = BulkScanStatus.IN_PROGRESS
        mock_scan_log = MagicMock(spec=BulkContentScanLog)
        mock_scan_log.id = uuid4()
        mock_scan_log.status = original_status
        mock_scan_log.completed_at = None

        call_count = 0

        async def execute_with_lock(stmt):
            nonlocal call_count
            call_count += 1

            assert stmt._for_update_arg is not None, "Query must use FOR UPDATE locking"

            mock_result = MagicMock()
            if call_count == 1:
                mock_scan_log.status = original_status
                mock_scan_log.completed_at = None
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
            else:
                mock_scan_log.status = BulkScanStatus.COMPLETED
                mock_scan_log.completed_at = datetime.now(UTC)
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_scan_log)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=execute_with_lock)

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

        await service.complete_scan(
            scan_id=mock_scan_log.id,
            messages_scanned=100,
            messages_flagged=5,
        )

        assert mock_session.execute.call_count == 2
        assert mock_session.commit.call_count == 2


class TestIsFlaggedConsistencyWithFlaggedMessage:
    """Test that is_flagged in score_info is consistent with flagged_msg - task-864.

    Bug: In production, progress events showed is_flagged=True but final results
    showed no flagged content. Root cause: is_flagged was set BEFORE flagged_msg
    was built, so if _build_flagged_message threw an exception, is_flagged would
    be True but flagged_msg would be None.
    """

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Task-953.01: This test is obsolete. The new unified candidate flow "
        "builds FlaggedMessage directly in _filter_candidates_with_relevance(), "
        "not via _build_flagged_message(). Error handling exists in the new flow."
    )
    async def test_is_flagged_false_when_build_flagged_message_fails(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """AC #3: is_flagged should remain False if _build_flagged_message fails.

        If building the FlaggedMessage raises an exception, is_flagged in score_info
        must remain False to prevent inconsistency between progress events and
        final results.
        """
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService
        from src.fact_checking.embedding_schemas import (
            FactCheckMatch,
            SimilaritySearchResponse,
        )

        high_score_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["misinformation"],
            title="Fake claim",
            content="This is a fake claim",
            source_url="https://snopes.com/fake",
            similarity_score=0.85,
            cc_score=0.5,
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                query_text="test",
                matches=[high_score_match],
                dataset_tags=["misinformation"],
                similarity_threshold=0.35,
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
            content="Test message content that should match",
            author_id="user_1",
            timestamp=datetime.now(UTC),
        )

        with patch.object(
            service, "_build_flagged_message", side_effect=ValueError("Build failed")
        ):
            flagged, scores = await service.process_messages_with_scores(
                scan_id=scan_id,
                messages=msg,
                community_server_platform_id="guild_123",
            )

        assert len(flagged) == 0, "No flagged messages when build fails"
        assert len(scores) == 1, "Should have one score entry"
        assert scores[0]["is_flagged"] is False, (
            "is_flagged must be False when _build_flagged_message fails"
        )
        assert scores[0]["similarity_score"] == 0.85, "Similarity score should be set"

    @pytest.mark.asyncio
    async def test_is_flagged_true_when_build_succeeds(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """is_flagged should be True when _build_flagged_message succeeds."""
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService
        from src.fact_checking.embedding_schemas import (
            FactCheckMatch,
            SimilaritySearchResponse,
        )

        high_score_match = FactCheckMatch(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["misinformation"],
            title="Fake claim",
            content="This is a fake claim",
            source_url="https://snopes.com/fake",
            similarity_score=0.85,
            cc_score=0.5,
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                query_text="test",
                matches=[high_score_match],
                dataset_tags=["misinformation"],
                similarity_threshold=0.35,
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
            content="Test message content that should match",
            author_id="user_1",
            timestamp=datetime.now(UTC),
        )

        flagged, scores = await service.process_messages_with_scores(
            scan_id=scan_id,
            messages=msg,
            community_server_platform_id="guild_123",
        )

        assert len(flagged) == 1, "Should have one flagged message"
        assert len(scores) == 1, "Should have one score entry"
        assert scores[0]["is_flagged"] is True, (
            "is_flagged must be True when message exceeds threshold"
        )
        assert scores[0]["similarity_score"] == 0.85


class TestSkippedCountTracking:
    """Test skipped message count tracking via Redis - task-867."""

    @pytest.mark.asyncio
    async def test_increment_skipped_count(self, mock_session, mock_embedding_service, mock_redis):
        """increment_skipped_count should increment Redis counter."""
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        await service.increment_skipped_count(scan_id, 5)

        mock_redis.incrby.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_skipped_count_returns_zero_when_not_set(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """get_skipped_count should return 0 when key doesn't exist."""
        from src.bulk_content_scan.service import BulkContentScanService

        mock_redis.get = AsyncMock(return_value=None)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        count = await service.get_skipped_count(scan_id)

        assert count == 0

    @pytest.mark.asyncio
    async def test_get_skipped_count_returns_stored_value(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """get_skipped_count should return the stored count."""
        from src.bulk_content_scan.service import BulkContentScanService

        mock_redis.get = AsyncMock(return_value=b"42")

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        scan_id = uuid4()
        count = await service.get_skipped_count(scan_id)

        assert count == 42


class TestGetExistingRequestMessageIds:
    """Test batch lookup of existing request message IDs - task-867."""

    @pytest.mark.asyncio
    async def test_returns_empty_set_for_empty_input(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Should return empty set when no message IDs provided."""
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        result = await service.get_existing_request_message_ids([])

        assert result == set()
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_existing_ids(self, mock_session, mock_embedding_service, mock_redis):
        """Should return set of message IDs that have existing requests."""
        from src.bulk_content_scan.service import BulkContentScanService

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[("msg_1",), ("msg_3",)])
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        result = await service.get_existing_request_message_ids(
            ["msg_1", "msg_2", "msg_3", "msg_4"]
        )

        assert result == {"msg_1", "msg_3"}

    @pytest.mark.asyncio
    async def test_handles_no_existing_requests(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Should return empty set when no messages have existing requests."""
        from src.bulk_content_scan.service import BulkContentScanService

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[])
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        result = await service.get_existing_request_message_ids(["msg_1", "msg_2"])

        assert result == set()

    @pytest.mark.asyncio
    async def test_filters_null_values(self, mock_session, mock_embedding_service, mock_redis):
        """Should filter out null values from results - task-867.02."""
        from src.bulk_content_scan.service import BulkContentScanService

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[("msg_1",), (None,), ("msg_3",), (None,)])
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        result = await service.get_existing_request_message_ids(["msg_1", "msg_2", "msg_3"])

        assert result == {"msg_1", "msg_3"}
        assert None not in result

    @pytest.mark.asyncio
    async def test_returns_empty_set_on_database_error(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Should return empty set on database error (fail-open) - task-867.01."""
        from src.bulk_content_scan.service import BulkContentScanService

        mock_session.execute = AsyncMock(side_effect=Exception("Database connection error"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        result = await service.get_existing_request_message_ids(["msg_1", "msg_2"])

        assert result == set()


class TestProcessMessagesSkipsExistingRequests:
    """Test that process_messages skips messages with existing note requests - task-867."""

    @pytest.mark.asyncio
    async def test_skips_messages_with_existing_requests(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Messages with existing note requests should be skipped."""
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
            content="Claim content",
            source_url="https://snopes.com/test",
            similarity_score=0.85,
        )
        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[mock_match],
                query_text="Test message",
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
                score_threshold=0.1,
                total_matches=1,
            )
        )

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[("msg_2",)])
        mock_session.execute = AsyncMock(return_value=mock_result)

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
                content="Test message content 1",
                author_id="user_1",
                timestamp=datetime.now(UTC),
            ),
            BulkScanMessage(
                message_id="msg_2",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Test message content 2 - has existing request",
                author_id="user_2",
                timestamp=datetime.now(UTC),
            ),
        ]

        await service.process_messages(
            scan_id=scan_id,
            messages=messages,
            community_server_platform_id="guild_123",
        )

        assert mock_embedding_service.similarity_search.call_count == 1
        call_args = mock_embedding_service.similarity_search.call_args
        processed_text = call_args[1]["query_text"]
        assert "Test message content 1" in processed_text
        assert "Test message content 2" not in processed_text
        mock_redis.incrby.assert_called()

    @pytest.mark.asyncio
    async def test_processes_all_when_no_existing_requests(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """All messages should be processed when none have existing requests."""
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
            content="Claim content",
            source_url="https://snopes.com/test",
            similarity_score=0.85,
        )
        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[mock_match],
                query_text="Test message",
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
                score_threshold=0.1,
                total_matches=1,
            )
        )

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[])
        mock_session.execute = AsyncMock(return_value=mock_result)

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
                content="Test message content 1",
                author_id="user_1",
                timestamp=datetime.now(UTC),
            ),
            BulkScanMessage(
                message_id="msg_2",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Test message content 2",
                author_id="user_2",
                timestamp=datetime.now(UTC),
            ),
        ]

        await service.process_messages(
            scan_id=scan_id,
            messages=messages,
            community_server_platform_id="guild_123",
        )

        assert mock_embedding_service.similarity_search.call_count == 2
        mock_redis.incrby.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_all_when_all_have_existing_requests(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """All messages should be skipped when all have existing requests - task-867.04."""
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[("msg_1",), ("msg_2",), ("msg_3",)])
        mock_session.execute = AsyncMock(return_value=mock_result)

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
                content="Test message content 1",
                author_id="user_1",
                timestamp=datetime.now(UTC),
            ),
            BulkScanMessage(
                message_id="msg_2",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Test message content 2",
                author_id="user_2",
                timestamp=datetime.now(UTC),
            ),
            BulkScanMessage(
                message_id="msg_3",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Test message content 3",
                author_id="user_3",
                timestamp=datetime.now(UTC),
            ),
        ]

        await service.process_messages(
            scan_id=scan_id,
            messages=messages,
            community_server_platform_id="guild_123",
        )

        mock_embedding_service.similarity_search.assert_not_called()
        mock_redis.incrby.assert_called_once()
        call_args = mock_redis.incrby.call_args
        assert call_args[0][1] == 3
        assert str(scan_id) in call_args[0][0]


class TestFlashpointRelevanceBypass:
    """Test that flashpoint candidates bypass the LLM relevance check (TASK-1067.73)."""

    @pytest.mark.asyncio
    async def test_flashpoint_candidates_always_have_should_flag_true(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Flashpoint candidates must always set should_flag=True, bypassing relevance check."""
        from src.bulk_content_scan.scan_types import ScanType
        from src.bulk_content_scan.schemas import (
            BulkScanMessage,
            ConversationFlashpointMatch,
            FlaggedMessage,
            RiskLevel,
            ScanCandidate,
        )
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        msg = BulkScanMessage(
            message_id="msg_fp_1",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="You are completely wrong and don't know what you are talking about",
            author_id="user_1",
            timestamp=datetime.now(UTC),
        )

        fp_match = ConversationFlashpointMatch(
            derailment_score=85,
            risk_level=RiskLevel.HOSTILE,
            reasoning="Detected hostile language patterns",
            context_messages=3,
        )

        candidate = ScanCandidate(
            message=msg,
            scan_type=ScanType.CONVERSATION_FLASHPOINT.value,
            match_data=fp_match,
            score=0.85,
            matched_content="Detected hostile language patterns",
            matched_source=None,
        )

        scan_id = uuid4()
        flagged = await service._filter_candidates_with_relevance([candidate], scan_id)

        assert len(flagged) == 1
        assert isinstance(flagged[0], FlaggedMessage)
        assert flagged[0].message_id == "msg_fp_1"
        assert flagged[0].matches[0].scan_type == "conversation_flashpoint"

    @pytest.mark.asyncio
    async def test_flashpoint_bypass_does_not_call_llm(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Flashpoint candidates must NOT trigger the LLM relevance check."""
        from unittest.mock import patch as mock_patch

        from src.bulk_content_scan.scan_types import ScanType
        from src.bulk_content_scan.schemas import (
            BulkScanMessage,
            ConversationFlashpointMatch,
            RiskLevel,
            ScanCandidate,
        )
        from src.bulk_content_scan.service import BulkContentScanService

        mock_llm = AsyncMock()
        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            llm_service=mock_llm,
        )

        msg = BulkScanMessage(
            message_id="msg_fp_2",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="This is aggressive content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
        )

        fp_match = ConversationFlashpointMatch(
            derailment_score=90,
            risk_level=RiskLevel.DANGEROUS,
            reasoning="Escalating hostility",
            context_messages=5,
        )

        candidate = ScanCandidate(
            message=msg,
            scan_type=ScanType.CONVERSATION_FLASHPOINT.value,
            match_data=fp_match,
            score=0.9,
            matched_content="Escalating hostility",
            matched_source=None,
        )

        scan_id = uuid4()
        with mock_patch.object(service, "_check_relevance_with_llm") as mock_check:
            await service._filter_candidates_with_relevance([candidate], scan_id)
            mock_check.assert_not_called()


class TestDeduplicateFlaggedMessages:
    """Test deduplication of flagged messages by message_id (TASK-1067.88)."""

    @pytest.mark.asyncio
    async def test_duplicate_message_ids_are_deduplicated(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Duplicate message_ids in input should only create one note request."""
        from unittest.mock import patch as mock_patch

        from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        flagged = FlaggedMessage(
            message_id="msg_dup",
            channel_id="ch_1",
            content="Test content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[similarity_match],
        )

        mock_request = MagicMock()
        mock_request.request_id = "req_123"

        with mock_patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            return_value=mock_request,
        ) as mock_create:
            result = await create_note_requests_from_flagged_messages(
                message_ids=["msg_dup", "msg_dup", "msg_dup"],
                scan_id=uuid4(),
                session=mock_session,
                user_id=uuid4(),
                community_server_id=uuid4(),
                flagged_messages=[flagged],
            )

        assert len(result) == 1
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_dual_match_messages_merge_matches(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """When a message has both similarity and flashpoint matches, matches are merged."""
        from src.bulk_content_scan.schemas import (
            ConversationFlashpointMatch,
            FlaggedMessage,
            RiskLevel,
            SimilarityMatch,
        )
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        sim_match = SimilarityMatch(
            score=0.85,
            matched_claim="Claim",
            matched_source="https://example.com",
            fact_check_item_id=SAMPLE_FACT_CHECK_ID,
        )
        fp_match = ConversationFlashpointMatch(
            derailment_score=90,
            risk_level=RiskLevel.DANGEROUS,
            reasoning="Escalation detected",
            context_messages=3,
        )

        flagged_sim = FlaggedMessage(
            message_id="msg_dual",
            channel_id="ch_1",
            content="Dual match content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[sim_match],
        )
        flagged_fp = FlaggedMessage(
            message_id="msg_dual",
            channel_id="ch_1",
            content="Dual match content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[fp_match],
        )

        mock_request = MagicMock()
        mock_request.request_id = "req_456"

        from unittest.mock import patch as mock_patch

        with mock_patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            return_value=mock_request,
        ) as mock_create:
            result = await create_note_requests_from_flagged_messages(
                message_ids=["msg_dual"],
                scan_id=uuid4(),
                session=mock_session,
                user_id=uuid4(),
                community_server_id=uuid4(),
                flagged_messages=[flagged_sim, flagged_fp],
            )

        assert len(result) == 1
        mock_create.assert_called_once()


class TestBatchContextLimitation:
    """Test build_channel_context_map batch-scoped behavior (TASK-1067.89)."""

    def test_context_map_only_contains_batch_messages(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Context map should only contain messages from the current batch."""
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        batch_messages = [
            BulkScanMessage(
                message_id=f"msg_{i}",
                channel_id="ch_1",
                community_server_id="guild_123",
                content=f"Message {i} content for testing",
                author_id="user_1",
                timestamp=datetime(2024, 1, 1, i, 0, 0, tzinfo=UTC),
            )
            for i in range(3)
        ]

        context_map = service.build_channel_context_map(batch_messages)

        assert "ch_1" in context_map
        assert len(context_map["ch_1"]) == 3
        msg_ids = [m.message_id for m in context_map["ch_1"]]
        assert msg_ids == ["msg_0", "msg_1", "msg_2"]

    def test_first_message_in_batch_has_no_context(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """The first message in a batch should have no prior context."""
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        batch_messages = [
            BulkScanMessage(
                message_id=f"msg_{i}",
                channel_id="ch_1",
                community_server_id="guild_123",
                content=f"Message {i} content for testing",
                author_id="user_1",
                timestamp=datetime(2024, 1, 1, i, 0, 0, tzinfo=UTC),
            )
            for i in range(3)
        ]

        context_map = service.build_channel_context_map(batch_messages)
        first_msg = batch_messages[0]
        context = service._get_context_for_message(first_msg, context_map)

        assert context == []


class TestContentScanTypesHoisted:
    """Test that content_scan_types is computed once outside the loop (TASK-1067.90)."""

    @pytest.mark.asyncio
    async def test_content_scan_types_excludes_flashpoint(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """Content scan types list should exclude CONVERSATION_FLASHPOINT."""
        from src.bulk_content_scan.scan_types import ScanType
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService
        from src.fact_checking.embedding_schemas import SimilaritySearchResponse

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[],
                query_text="Test",
                dataset_tags=[],
                similarity_threshold=0.6,
                score_threshold=0.1,
                total_matches=0,
            )
        )

        mock_flashpoint_service = AsyncMock()
        mock_flashpoint_service.detect_flashpoint = AsyncMock(return_value=None)

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            flashpoint_service=mock_flashpoint_service,
        )

        scan_id = uuid4()
        messages = [
            BulkScanMessage(
                message_id=f"msg_{i}",
                channel_id="ch_1",
                community_server_id="guild_123",
                content=f"Test message content number {i} for scanning",
                author_id="user_1",
                timestamp=datetime(2024, 1, 1, i, 0, 0, tzinfo=UTC),
            )
            for i in range(3)
        ]

        await service.process_messages(
            scan_id=scan_id,
            messages=messages,
            community_server_platform_id="guild_123",
            scan_types=[ScanType.SIMILARITY, ScanType.CONVERSATION_FLASHPOINT],
        )

        assert mock_embedding_service.similarity_search.call_count == 3
        assert mock_flashpoint_service.detect_flashpoint.call_count == 3


class TestUnifiedFlaggedMessageConstruction:
    """Test unified FlaggedMessage construction via _build_flagged_message_from_candidate (TASK-1067.102)."""

    def test_build_flagged_message_from_candidate(
        self, mock_session, mock_embedding_service, mock_redis
    ):
        """_build_flagged_message_from_candidate should produce correct FlaggedMessage."""
        from src.bulk_content_scan.scan_types import ScanType
        from src.bulk_content_scan.schemas import (
            BulkScanMessage,
            ConversationFlashpointMatch,
            FlaggedMessage,
            RiskLevel,
            ScanCandidate,
        )
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        msg = BulkScanMessage(
            message_id="msg_unified",
            channel_id="ch_1",
            community_server_id="guild_123",
            content="Unified construction test content",
            author_id="user_1",
            timestamp=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        fp_match = ConversationFlashpointMatch(
            derailment_score=88,
            risk_level=RiskLevel.DANGEROUS,
            reasoning="Hostile escalation pattern",
            context_messages=4,
        )

        candidate = ScanCandidate(
            message=msg,
            scan_type=ScanType.CONVERSATION_FLASHPOINT.value,
            match_data=fp_match,
            score=0.88,
            matched_content="Hostile escalation pattern",
            matched_source=None,
        )

        result = service._build_flagged_message_from_candidate(candidate)

        assert isinstance(result, FlaggedMessage)
        assert result.message_id == "msg_unified"
        assert result.channel_id == "ch_1"
        assert result.content == "Unified construction test content"
        assert result.author_id == "user_1"
        assert len(result.matches) == 1
        assert result.matches[0].scan_type == "conversation_flashpoint"
        assert result.matches[0].derailment_score == 88


class TestCrossBatchContextCache:
    @pytest.fixture
    def stateful_redis(self):
        from tests.redis_mock import StatefulRedisMock

        return StatefulRedisMock()

    def _make_message(self, msg_id: str, channel_id: str, minute: int):
        from src.bulk_content_scan.schemas import BulkScanMessage

        return BulkScanMessage(
            message_id=msg_id,
            channel_id=channel_id,
            community_server_id="guild_123",
            content=f"Message {msg_id} content for testing",
            author_id="user_1",
            timestamp=datetime(2024, 1, 1, minute // 60, minute % 60, 0, tzinfo=UTC),
        )

    @pytest.mark.asyncio
    async def test_populate_writes_messages_to_sorted_set(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        messages = [
            self._make_message("msg_1", "ch_1", 1),
            self._make_message("msg_2", "ch_1", 2),
            self._make_message("msg_3", "ch_2", 3),
        ]

        await service._populate_cross_batch_cache(messages, "server_abc")

        key_ch1 = service._get_flashpoint_context_key("server_abc", "ch_1")
        key_ch2 = service._get_flashpoint_context_key("server_abc", "ch_2")

        assert await stateful_redis.zcard(key_ch1) == 2
        assert await stateful_redis.zcard(key_ch2) == 1

    @pytest.mark.asyncio
    async def test_populate_sets_ttl(self, mock_session, mock_embedding_service, stateful_redis):
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        messages = [self._make_message("msg_1", "ch_1", 1)]

        await service._populate_cross_batch_cache(messages, "server_abc")

        key = service._get_flashpoint_context_key("server_abc", "ch_1")
        remaining_ttl = await stateful_redis.ttl(key)
        assert remaining_ttl > 0

    @pytest.mark.asyncio
    async def test_populate_trims_to_max_messages(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from unittest.mock import patch as mock_patch

        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        messages = [self._make_message(f"msg_{i}", "ch_1", i) for i in range(25)]

        with mock_patch("src.bulk_content_scan.service.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "test"
            mock_settings.FLASHPOINT_CONTEXT_CACHE_TTL = 1800
            mock_settings.FLASHPOINT_CONTEXT_CACHE_MAX_MESSAGES = 10

            await service._populate_cross_batch_cache(messages, "server_abc")

            key = service._get_flashpoint_context_key("server_abc", "ch_1")

        assert await stateful_redis.zcard(key) == 10

        cached = await stateful_redis.zrange(key, 0, -1, withscores=True)
        scores = [s for _, s in cached]
        assert scores == sorted(scores)

    @pytest.mark.asyncio
    async def test_enrich_merges_cached_messages_into_context(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        batch1_msgs = [
            self._make_message("msg_1", "ch_1", 1),
            self._make_message("msg_2", "ch_1", 2),
        ]
        await service._populate_cross_batch_cache(batch1_msgs, "server_abc")

        batch2_msgs = [
            self._make_message("msg_3", "ch_1", 3),
            self._make_message("msg_4", "ch_1", 4),
        ]
        channel_context_map = BulkContentScanService.build_channel_context_map(batch2_msgs)

        enriched = await service._enrich_context_from_cache(channel_context_map, "server_abc")

        assert len(enriched["ch_1"]) == 4
        msg_ids = [m.message_id for m in enriched["ch_1"]]
        assert msg_ids == ["msg_1", "msg_2", "msg_3", "msg_4"]

    @pytest.mark.asyncio
    async def test_enrich_does_not_duplicate_messages_in_both_batch_and_cache(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        overlap_msg = self._make_message("msg_2", "ch_1", 2)
        batch1_msgs = [
            self._make_message("msg_1", "ch_1", 1),
            overlap_msg,
        ]
        await service._populate_cross_batch_cache(batch1_msgs, "server_abc")

        batch2_msgs = [
            self._make_message("msg_2", "ch_1", 2),
            self._make_message("msg_3", "ch_1", 3),
        ]
        channel_context_map = BulkContentScanService.build_channel_context_map(batch2_msgs)

        enriched = await service._enrich_context_from_cache(channel_context_map, "server_abc")

        assert len(enriched["ch_1"]) == 3
        msg_ids = [m.message_id for m in enriched["ch_1"]]
        assert msg_ids == ["msg_1", "msg_2", "msg_3"]

    @pytest.mark.asyncio
    async def test_enrich_maintains_time_order(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        batch1_msgs = [
            self._make_message("msg_1", "ch_1", 1),
            self._make_message("msg_3", "ch_1", 3),
        ]
        await service._populate_cross_batch_cache(batch1_msgs, "server_abc")

        batch2_msgs = [
            self._make_message("msg_2", "ch_1", 2),
            self._make_message("msg_4", "ch_1", 4),
        ]
        channel_context_map = BulkContentScanService.build_channel_context_map(batch2_msgs)

        enriched = await service._enrich_context_from_cache(channel_context_map, "server_abc")

        msg_ids = [m.message_id for m in enriched["ch_1"]]
        assert msg_ids == ["msg_1", "msg_2", "msg_3", "msg_4"]

    @pytest.mark.asyncio
    async def test_cross_batch_context_full_flow(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        batch1 = [
            self._make_message("msg_1", "ch_1", 1),
            self._make_message("msg_2", "ch_1", 2),
        ]
        await service._populate_cross_batch_cache(batch1, "server_abc")

        batch2 = [
            self._make_message("msg_3", "ch_1", 3),
            self._make_message("msg_4", "ch_1", 4),
        ]
        context_map = BulkContentScanService.build_channel_context_map(batch2)
        enriched = await service._enrich_context_from_cache(context_map, "server_abc")
        await service._populate_cross_batch_cache(batch2, "server_abc")

        assert len(enriched["ch_1"]) == 4

        batch3 = [
            self._make_message("msg_5", "ch_1", 5),
        ]
        context_map3 = BulkContentScanService.build_channel_context_map(batch3)
        enriched3 = await service._enrich_context_from_cache(context_map3, "server_abc")
        await service._populate_cross_batch_cache(batch3, "server_abc")

        assert len(enriched3["ch_1"]) == 5
        msg_ids = [m.message_id for m in enriched3["ch_1"]]
        assert set(msg_ids) == {"msg_1", "msg_2", "msg_3", "msg_4", "msg_5"}
        timestamps = [m.timestamp for m in enriched3["ch_1"]]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_populate_graceful_on_redis_error(self, mock_session, mock_embedding_service):
        from src.bulk_content_scan.service import BulkContentScanService

        broken_redis = AsyncMock()
        broken_redis.zadd = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=broken_redis,
        )

        messages = [self._make_message("msg_1", "ch_1", 1)]
        await service._populate_cross_batch_cache(messages, "server_abc")

    @pytest.mark.asyncio
    async def test_enrich_graceful_on_redis_error(self, mock_session, mock_embedding_service):
        from src.bulk_content_scan.service import BulkContentScanService

        broken_redis = AsyncMock()
        broken_redis.zrange = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=broken_redis,
        )

        batch_msgs = [self._make_message("msg_1", "ch_1", 1)]
        context_map = BulkContentScanService.build_channel_context_map(batch_msgs)

        result = await service._enrich_context_from_cache(context_map, "server_abc")

        assert len(result["ch_1"]) == 1
        assert result["ch_1"][0].message_id == "msg_1"

    @pytest.mark.asyncio
    async def test_enrich_returns_original_on_empty_cache(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        batch_msgs = [
            self._make_message("msg_1", "ch_1", 1),
            self._make_message("msg_2", "ch_1", 2),
        ]
        context_map = BulkContentScanService.build_channel_context_map(batch_msgs)

        enriched = await service._enrich_context_from_cache(context_map, "server_abc")

        assert len(enriched["ch_1"]) == 2
        msg_ids = [m.message_id for m in enriched["ch_1"]]
        assert msg_ids == ["msg_1", "msg_2"]

    @pytest.mark.asyncio
    async def test_populate_handles_multiple_channels(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        messages = [
            self._make_message("msg_1", "ch_1", 1),
            self._make_message("msg_2", "ch_2", 2),
            self._make_message("msg_3", "ch_1", 3),
            self._make_message("msg_4", "ch_3", 4),
        ]

        await service._populate_cross_batch_cache(messages, "server_abc")

        key_ch1 = service._get_flashpoint_context_key("server_abc", "ch_1")
        key_ch2 = service._get_flashpoint_context_key("server_abc", "ch_2")
        key_ch3 = service._get_flashpoint_context_key("server_abc", "ch_3")

        assert await stateful_redis.zcard(key_ch1) == 2
        assert await stateful_redis.zcard(key_ch2) == 1
        assert await stateful_redis.zcard(key_ch3) == 1

    @pytest.mark.asyncio
    async def test_process_messages_calls_cache_methods_for_flashpoint(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.scan_types import ScanType
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        service.get_existing_request_message_ids = AsyncMock(return_value=set())
        service._populate_cross_batch_cache = AsyncMock()
        service._enrich_context_from_cache = AsyncMock(side_effect=lambda ctx_map, _cs_id: ctx_map)
        service._generate_candidate = AsyncMock(return_value=None)
        service._filter_candidates_with_relevance = AsyncMock(return_value=[])

        scan_id = uuid4()
        messages = [
            BulkScanMessage(
                message_id="msg_1",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Test message content that is long enough",
                author_id="user_1",
                timestamp=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            ),
        ]

        await service.process_messages(
            scan_id=scan_id,
            messages=messages,
            community_server_platform_id="guild_123",
            scan_types=[ScanType.CONVERSATION_FLASHPOINT],
        )

        service._populate_cross_batch_cache.assert_awaited_once()
        service._enrich_context_from_cache.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_messages_skips_cache_methods_without_flashpoint(
        self, mock_session, mock_embedding_service, stateful_redis
    ):
        from src.bulk_content_scan.scan_types import ScanType
        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.bulk_content_scan.service import BulkContentScanService
        from src.fact_checking.embedding_schemas import (
            SimilaritySearchResponse,
        )

        mock_embedding_service.similarity_search = AsyncMock(
            return_value=SimilaritySearchResponse(
                matches=[],
                query_text="Test message",
                dataset_tags=["snopes"],
                similarity_threshold=0.6,
                score_threshold=0.1,
                total_matches=0,
            )
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=stateful_redis,
        )

        service.get_existing_request_message_ids = AsyncMock(return_value=set())
        service._populate_cross_batch_cache = AsyncMock()
        service._enrich_context_from_cache = AsyncMock()

        scan_id = uuid4()
        messages = [
            BulkScanMessage(
                message_id="msg_1",
                channel_id="ch_1",
                community_server_id="guild_123",
                content="Test message content that is long enough",
                author_id="user_1",
                timestamp=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            ),
        ]

        await service.process_messages(
            scan_id=scan_id,
            messages=messages,
            community_server_platform_id="guild_123",
            scan_types=[ScanType.SIMILARITY],
        )

        service._populate_cross_batch_cache.assert_not_awaited()
        service._enrich_context_from_cache.assert_not_awaited()
