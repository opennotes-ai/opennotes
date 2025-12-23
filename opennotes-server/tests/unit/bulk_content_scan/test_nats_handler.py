"""Tests for Bulk Content Scan NATS event handlers."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.bulk_content_scan.schemas import BulkScanStatus, FlaggedMessage


@pytest.fixture
def mock_service():
    """Create a mock BulkContentScanService."""
    service = AsyncMock()
    service.process_messages = AsyncMock(return_value=[])
    service.append_flagged_result = AsyncMock()
    service.get_flagged_results = AsyncMock(return_value=[])
    service.complete_scan = AsyncMock()
    service.record_error = AsyncMock()
    service.increment_processed_count = AsyncMock()
    service.get_error_summary = AsyncMock(
        return_value={"total_errors": 0, "error_types": {}, "sample_errors": []}
    )
    service.get_processed_count = AsyncMock(return_value=0)
    return service


@pytest.fixture
def mock_publisher():
    """Create a mock event publisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    return publisher


@pytest.fixture
def sample_messages():
    """Create sample message dicts for testing."""
    return [
        {
            "message_id": "msg_1",
            "channel_id": "ch_1",
            "community_server_id": "srv_1",
            "content": "Test message 1 with enough content",
            "author_id": "user_1",
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "message_id": "msg_2",
            "channel_id": "ch_1",
            "community_server_id": "srv_1",
            "content": "Test message 2 with enough content",
            "author_id": "user_2",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    ]


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


class TestHandleMessageBatch:
    """Test handling of BULK_SCAN_MESSAGE_BATCH events with streaming behavior."""

    @pytest.mark.asyncio
    async def test_processes_messages_immediately(self, mock_service, sample_messages):
        """Verify process_messages() is called for each batch (not collect_messages)."""
        from src.bulk_content_scan.nats_handler import handle_message_batch
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=sample_messages,
            batch_number=1,
            is_final_batch=False,
        )

        with patch(
            "src.bulk_content_scan.nats_handler.get_platform_id",
            new=AsyncMock(return_value="test_platform_123"),
        ):
            await handle_message_batch(event, mock_service)

        mock_service.process_messages.assert_called_once()
        call_kwargs = mock_service.process_messages.call_args[1]
        assert call_kwargs["scan_id"] == scan_id
        assert call_kwargs["community_server_platform_id"] == "test_platform_123"
        assert len(call_kwargs["messages"]) == 2

    @pytest.mark.asyncio
    async def test_stores_flagged_results_per_batch(
        self, mock_service, sample_messages, sample_flagged_message
    ):
        """Verify append_flagged_result() is called for each flagged message."""
        from src.bulk_content_scan.nats_handler import handle_message_batch
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        flagged_messages = [sample_flagged_message]
        mock_service.process_messages = AsyncMock(return_value=flagged_messages)

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=sample_messages,
            batch_number=1,
            is_final_batch=False,
        )

        with patch(
            "src.bulk_content_scan.nats_handler.get_platform_id",
            new=AsyncMock(return_value="test_platform_123"),
        ):
            await handle_message_batch(event, mock_service)

        assert mock_service.append_flagged_result.call_count == 1
        mock_service.append_flagged_result.assert_called_once_with(scan_id, sample_flagged_message)

    @pytest.mark.asyncio
    async def test_raises_error_when_platform_id_not_found(self, mock_service, sample_messages):
        """Verify BatchProcessingError is raised when platform_id lookup fails.

        This ensures the message is NAKed for retry instead of being silently dropped.
        """
        from src.bulk_content_scan.nats_handler import (
            BatchProcessingError,
            handle_message_batch,
        )
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=sample_messages,
            batch_number=1,
            is_final_batch=False,
        )

        with (
            patch(
                "src.bulk_content_scan.nats_handler.get_platform_id",
                new=AsyncMock(return_value=None),
            ),
            pytest.raises(BatchProcessingError) as exc_info,
        ):
            await handle_message_batch(event, mock_service)

        assert "Platform ID not found" in str(exc_info.value)
        assert str(community_server_id) in str(exc_info.value)
        mock_service.process_messages.assert_not_called()
        mock_service.append_flagged_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_error_when_process_messages_fails(self, mock_service, sample_messages):
        """Verify exceptions from process_messages propagate to cause NAK.

        This ensures failed batch processing doesn't silently drop batches.
        """
        from src.bulk_content_scan.nats_handler import handle_message_batch
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        mock_service.process_messages = AsyncMock(
            side_effect=RuntimeError("Embedding service unavailable")
        )

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=sample_messages,
            batch_number=1,
            is_final_batch=False,
        )

        with (
            patch(
                "src.bulk_content_scan.nats_handler.get_platform_id",
                new=AsyncMock(return_value="test_platform_123"),
            ),
            pytest.raises(RuntimeError) as exc_info,
        ):
            await handle_message_batch(event, mock_service)

        assert "Embedding service unavailable" in str(exc_info.value)


class TestHandleAllBatchesTransmitted:
    """Test handling of BULK_SCAN_ALL_BATCHES_TRANSMITTED events."""

    @pytest.mark.asyncio
    async def test_sets_transmitted_flag(self, mock_service, mock_publisher):
        """Verify set_all_batches_transmitted is called."""
        from src.bulk_content_scan.nats_handler import handle_all_batches_transmitted
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        mock_service.set_all_batches_transmitted = AsyncMock()
        mock_service.get_processed_count = AsyncMock(return_value=0)

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
        )

        await handle_all_batches_transmitted(event, mock_service, mock_publisher)

        mock_service.set_all_batches_transmitted.assert_called_once_with(scan_id, 100)

    @pytest.mark.asyncio
    async def test_triggers_completion_when_all_processed(
        self, mock_service, mock_publisher, sample_flagged_message
    ):
        """Verify completion triggers when all messages already processed."""
        from unittest.mock import patch

        from src.bulk_content_scan.nats_handler import handle_all_batches_transmitted
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent

        scan_id = uuid4()
        community_server_id = uuid4()
        messages_scanned = 100

        mock_service.set_all_batches_transmitted = AsyncMock()
        mock_service.get_processed_count = AsyncMock(return_value=messages_scanned)
        mock_service.get_flagged_results = AsyncMock(return_value=[sample_flagged_message])
        mock_service.get_error_summary = AsyncMock(
            return_value={"total_errors": 0, "error_types": {}, "sample_errors": []}
        )

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=messages_scanned,
        )

        with patch("src.bulk_content_scan.nats_handler.event_publisher") as mock_event_publisher:
            mock_event_publisher.publish_event = AsyncMock()
            await handle_all_batches_transmitted(event, mock_service, mock_publisher)

        mock_service.complete_scan.assert_called_once_with(
            scan_id=scan_id,
            messages_scanned=messages_scanned,
            messages_flagged=1,
            status=BulkScanStatus.COMPLETED,
        )

    @pytest.mark.asyncio
    async def test_does_not_trigger_when_processing_pending(self, mock_service, mock_publisher):
        """Verify no completion when batches still processing."""
        from src.bulk_content_scan.nats_handler import handle_all_batches_transmitted
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        mock_service.set_all_batches_transmitted = AsyncMock()
        mock_service.get_processed_count = AsyncMock(return_value=50)

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
        )

        await handle_all_batches_transmitted(event, mock_service, mock_publisher)

        mock_service.set_all_batches_transmitted.assert_called_once()
        mock_service.complete_scan.assert_not_called()
        mock_publisher.publish.assert_not_called()


class TestBulkScanHandlerRegistration:
    """Test that handlers can be registered with EventSubscriber."""

    def test_handler_functions_are_async(self):
        """All handlers must be async functions."""
        import asyncio

        from src.bulk_content_scan.nats_handler import (
            handle_all_batches_transmitted,
            handle_message_batch,
        )

        assert asyncio.iscoroutinefunction(handle_message_batch)
        assert asyncio.iscoroutinefunction(handle_all_batches_transmitted)
