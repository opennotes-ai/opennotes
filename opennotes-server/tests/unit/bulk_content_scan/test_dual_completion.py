"""Tests for dual-completion-trigger logic in bulk scan handlers.

This tests the race condition fix where either the batch handler OR the
transmitted handler can trigger scan completion - whichever finishes last.

Key scenarios:
1. Batch handler finishes LAST → triggers completion
2. Transmitted handler finishes LAST → triggers completion
3. Completion only happens once (idempotency)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.bulk_content_scan.schemas import FlaggedMessage


@pytest.fixture
def mock_service():
    """Create a mock BulkContentScanService with dual-completion methods."""
    service = AsyncMock()
    service.process_messages = AsyncMock(return_value=[])
    service.process_messages_with_scores = AsyncMock(return_value=([], []))
    service.append_flagged_result = AsyncMock()
    service.get_flagged_results = AsyncMock(return_value=[])
    service.complete_scan = AsyncMock()
    service.record_error = AsyncMock()
    service.increment_processed_count = AsyncMock()
    service.get_error_summary = AsyncMock(
        return_value={"total_errors": 0, "error_types": {}, "sample_errors": []}
    )
    service.get_processed_count = AsyncMock(return_value=0)
    service.set_all_batches_transmitted = AsyncMock()
    service.get_all_batches_transmitted = AsyncMock(return_value=(False, None))
    return service


@pytest.fixture
def mock_publisher():
    """Create a mock event publisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    return publisher


@pytest.fixture
def sample_flagged_message():
    """Create a sample FlaggedMessage for testing."""
    return FlaggedMessage(
        message_id="msg_1",
        channel_id="ch_1",
        content="Test flagged content",
        author_id="user_1",
        timestamp=datetime.now(UTC),
        match_score=0.85,
        matched_claim="Test claim",
        matched_source="https://example.com",
    )


class TestDualCompletionTrigger:
    """Test the dual-completion-trigger pattern for race condition fix."""

    @pytest.mark.asyncio
    async def test_batch_handler_triggers_completion_when_transmitted_flag_set(
        self, mock_service, mock_publisher
    ):
        """When batch finishes LAST (transmitted flag already set), it triggers completion."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()
        community_server_id = uuid4()
        messages_scanned = 2

        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(True, messages_scanned))
        mock_service.get_processed_count = AsyncMock(return_value=messages_scanned)

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=[
                {
                    "message_id": "msg_1",
                    "channel_id": "ch_1",
                    "community_server_id": str(community_server_id),
                    "content": "Test message with enough content here",
                    "author_id": "user_1",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
            batch_number=1,
            is_final_batch=False,
        )

        with patch("src.bulk_content_scan.nats_handler.event_publisher") as mock_event_publisher:
            mock_event_publisher.publish_event = AsyncMock()
            await handle_message_batch_with_progress(
                event=event,
                service=mock_service,
                nats_client=AsyncMock(),
                platform_id="test_platform",
                debug_mode=False,
                publisher=mock_publisher,
            )

        mock_service.get_all_batches_transmitted.assert_called()
        mock_service.complete_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_handler_does_not_trigger_when_transmitted_flag_not_set(
        self, mock_service, mock_publisher
    ):
        """When batch finishes FIRST (transmitted flag not set), don't trigger completion."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        mock_service.get_all_batches_transmitted = AsyncMock(return_value=(False, None))

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=[
                {
                    "message_id": "msg_1",
                    "channel_id": "ch_1",
                    "community_server_id": str(community_server_id),
                    "content": "Test message with enough content here",
                    "author_id": "user_1",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
            batch_number=1,
            is_final_batch=False,
        )

        with patch("src.bulk_content_scan.nats_handler.event_publisher") as mock_event_publisher:
            mock_event_publisher.publish_event = AsyncMock()
            await handle_message_batch_with_progress(
                event=event,
                service=mock_service,
                nats_client=AsyncMock(),
                platform_id="test_platform",
                debug_mode=False,
                publisher=mock_publisher,
            )

        mock_service.complete_scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_transmitted_handler_triggers_completion_when_all_processed(
        self, mock_service, mock_publisher
    ):
        """When transmitted handler finishes LAST (all batches processed), trigger completion."""
        from src.bulk_content_scan.nats_handler import handle_all_batches_transmitted
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent

        scan_id = uuid4()
        community_server_id = uuid4()
        messages_scanned = 5

        mock_service.get_processed_count = AsyncMock(return_value=messages_scanned)

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=messages_scanned,
        )

        await handle_all_batches_transmitted(event, mock_service, mock_publisher)

        mock_service.set_all_batches_transmitted.assert_called_once_with(scan_id, messages_scanned)
        mock_service.complete_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_transmitted_handler_does_not_trigger_when_batches_pending(
        self, mock_service, mock_publisher
    ):
        """When transmitted handler finishes FIRST (batches still pending), don't complete."""
        from src.bulk_content_scan.nats_handler import handle_all_batches_transmitted
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent

        scan_id = uuid4()
        community_server_id = uuid4()
        messages_scanned = 10

        mock_service.get_processed_count = AsyncMock(return_value=5)

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=messages_scanned,
        )

        await handle_all_batches_transmitted(event, mock_service, mock_publisher)

        mock_service.set_all_batches_transmitted.assert_called_once_with(scan_id, messages_scanned)
        mock_service.complete_scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_completion_publishes_processing_finished_event(
        self, mock_service, mock_publisher
    ):
        """When completion triggers, it should publish ProcessingFinished event."""
        from src.bulk_content_scan.nats_handler import handle_all_batches_transmitted
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent

        scan_id = uuid4()
        community_server_id = uuid4()
        messages_scanned = 5

        mock_service.get_processed_count = AsyncMock(return_value=messages_scanned)

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=messages_scanned,
        )

        with patch("src.bulk_content_scan.nats_handler.event_publisher") as mock_event_publisher:
            mock_event_publisher.publish_event = AsyncMock()
            await handle_all_batches_transmitted(event, mock_service, mock_publisher)

            mock_event_publisher.publish_event.assert_called()
            call_args = mock_event_publisher.publish_event.call_args[0][0]
            assert call_args.event_type.value == "bulk_scan.processing_finished"


class TestEventTypeRename:
    """Test that event types are renamed correctly."""

    def test_all_batches_transmitted_event_type_exists(self):
        """Verify BULK_SCAN_ALL_BATCHES_TRANSMITTED exists in EventType."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_ALL_BATCHES_TRANSMITTED")
        assert (
            EventType.BULK_SCAN_ALL_BATCHES_TRANSMITTED.value == "bulk_scan.all_batches_transmitted"
        )

    def test_processing_finished_event_type_exists(self):
        """Verify BULK_SCAN_PROCESSING_FINISHED exists in EventType."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_PROCESSING_FINISHED")
        assert EventType.BULK_SCAN_PROCESSING_FINISHED.value == "bulk_scan.processing_finished"

    def test_all_batches_transmitted_event_class_exists(self):
        """Verify BulkScanAllBatchesTransmittedEvent class exists."""
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            messages_scanned=10,
        )
        assert event.event_type.value == "bulk_scan.all_batches_transmitted"

    def test_processing_finished_event_class_exists(self):
        """Verify BulkScanProcessingFinishedEvent class exists."""
        from src.events.schemas import BulkScanProcessingFinishedEvent

        event = BulkScanProcessingFinishedEvent(
            event_id="evt_123",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            messages_scanned=10,
            messages_flagged=2,
        )
        assert event.event_type.value == "bulk_scan.processing_finished"


class TestRedisTransmittedFlag:
    """Test Redis helpers for all_batches_transmitted flag."""

    @pytest.mark.asyncio
    async def test_set_all_batches_transmitted_sets_flag(self, mock_service):
        """Verify set_all_batches_transmitted sets flag in Redis with messages_scanned."""
        from src.bulk_content_scan.service import BulkContentScanService

        scan_id = uuid4()
        messages_scanned = 10
        mock_redis = AsyncMock()

        service = BulkContentScanService.__new__(BulkContentScanService)
        service.redis_client = mock_redis
        service.session = AsyncMock()
        service.embedding_service = AsyncMock()

        await service.set_all_batches_transmitted(scan_id, messages_scanned)

        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args
        assert "all_batches_transmitted" in call_args[0][0]
        assert str(scan_id) in call_args[0][0]
        assert call_args[0][1] == str(messages_scanned)

    @pytest.mark.asyncio
    async def test_get_all_batches_transmitted_returns_true_when_set(self, mock_service):
        """Verify get_all_batches_transmitted returns (True, messages_scanned) when flag is set."""
        from src.bulk_content_scan.service import BulkContentScanService

        scan_id = uuid4()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"10")

        service = BulkContentScanService.__new__(BulkContentScanService)
        service.redis_client = mock_redis
        service.session = AsyncMock()
        service.embedding_service = AsyncMock()

        result = await service.get_all_batches_transmitted(scan_id)

        assert result == (True, 10)

    @pytest.mark.asyncio
    async def test_get_all_batches_transmitted_returns_false_when_not_set(self, mock_service):
        """Verify get_all_batches_transmitted returns (False, None) when flag not set."""
        from src.bulk_content_scan.service import BulkContentScanService

        scan_id = uuid4()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        service = BulkContentScanService.__new__(BulkContentScanService)
        service.redis_client = mock_redis
        service.session = AsyncMock()
        service.embedding_service = AsyncMock()

        result = await service.get_all_batches_transmitted(scan_id)

        assert result == (False, None)
