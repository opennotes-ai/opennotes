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
            status="completed",
        )

        assert mock_scan_log.status == "completed"
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
