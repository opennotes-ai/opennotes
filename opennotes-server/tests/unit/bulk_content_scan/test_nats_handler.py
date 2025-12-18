"""Tests for Bulk Content Scan NATS event handlers."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_service():
    """Create a mock BulkContentScanService."""
    service = AsyncMock()
    service.collect_messages = AsyncMock()
    service.process_collected_messages = AsyncMock(return_value=[])
    service.complete_scan = AsyncMock()
    service.store_flagged_results = AsyncMock()
    return service


@pytest.fixture
def mock_publisher():
    """Create a mock event publisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    return publisher


class TestHandleMessageBatch:
    """Test handling of BULK_SCAN_MESSAGE_BATCH events."""

    @pytest.mark.asyncio
    async def test_collects_messages_to_service(self, mock_service):
        """AC #2: Server NATS handlers receive and temporarily store messages."""
        from src.bulk_content_scan.nats_handler import handle_message_batch
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()
        messages = [
            {
                "message_id": "msg_1",
                "channel_id": "ch_1",
                "content": "Test message 1",
                "author_id": "user_1",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            {
                "message_id": "msg_2",
                "channel_id": "ch_1",
                "content": "Test message 2",
                "author_id": "user_2",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ]

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=scan_id,
            messages=messages,
            batch_number=1,
            is_final_batch=False,
        )

        await handle_message_batch(event, mock_service)

        mock_service.collect_messages.assert_called_once_with(
            scan_id=scan_id,
            messages=messages,
        )

    @pytest.mark.asyncio
    async def test_handles_multiple_batches(self, mock_service):
        """Should handle multiple batches for the same scan."""
        from src.bulk_content_scan.nats_handler import handle_message_batch
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()

        event1 = BulkScanMessageBatchEvent(
            event_id="evt_1",
            scan_id=scan_id,
            messages=[{"message_id": "msg_1", "content": "Test 1"}],
            batch_number=1,
            is_final_batch=False,
        )

        event2 = BulkScanMessageBatchEvent(
            event_id="evt_2",
            scan_id=scan_id,
            messages=[{"message_id": "msg_2", "content": "Test 2"}],
            batch_number=2,
            is_final_batch=True,
        )

        await handle_message_batch(event1, mock_service)
        await handle_message_batch(event2, mock_service)

        assert mock_service.collect_messages.call_count == 2


class TestHandleScanCompleted:
    """Test handling of BULK_SCAN_COMPLETED events."""

    @pytest.mark.asyncio
    async def test_processes_collected_messages(self, mock_service, mock_publisher):
        """AC #3: Similarity search runs on collected messages."""
        from src.bulk_content_scan.nats_handler import handle_scan_completed
        from src.events.schemas import BulkScanCompletedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
        )

        with patch(
            "src.bulk_content_scan.nats_handler.get_platform_id",
            new=AsyncMock(return_value="test_platform_123"),
        ):
            await handle_scan_completed(event, mock_service, mock_publisher)

        mock_service.process_collected_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_completes_scan_with_results(self, mock_service, mock_publisher):
        """AC #8: Scan completion logs entry to bulk_content_scan_log table."""
        from src.bulk_content_scan.nats_handler import handle_scan_completed
        from src.bulk_content_scan.schemas import FlaggedMessage
        from src.events.schemas import BulkScanCompletedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        mock_flagged = [
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
        mock_service.process_collected_messages = AsyncMock(return_value=mock_flagged)

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
        )

        with patch(
            "src.bulk_content_scan.nats_handler.get_platform_id",
            new=AsyncMock(return_value="test_platform_123"),
        ):
            await handle_scan_completed(event, mock_service, mock_publisher)

        mock_service.complete_scan.assert_called_once_with(
            scan_id=scan_id,
            messages_scanned=100,
            messages_flagged=1,
        )

    @pytest.mark.asyncio
    async def test_stores_flagged_results(self, mock_service, mock_publisher):
        """Results should be stored for later retrieval."""
        from src.bulk_content_scan.nats_handler import handle_scan_completed
        from src.bulk_content_scan.schemas import FlaggedMessage
        from src.events.schemas import BulkScanCompletedEvent

        scan_id = uuid4()
        mock_flagged = [
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
        mock_service.process_collected_messages = AsyncMock(return_value=mock_flagged)

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=uuid4(),
            messages_scanned=50,
        )

        with patch(
            "src.bulk_content_scan.nats_handler.get_platform_id",
            new=AsyncMock(return_value="test_platform_123"),
        ):
            await handle_scan_completed(event, mock_service, mock_publisher)

        mock_service.store_flagged_results.assert_called_once_with(
            scan_id=scan_id,
            flagged_messages=mock_flagged,
        )

    @pytest.mark.asyncio
    async def test_publishes_results_event(self, mock_service, mock_publisher):
        """AC #1: Results should be published via NATS for Discord bot."""
        from src.bulk_content_scan.nats_handler import handle_scan_completed
        from src.bulk_content_scan.schemas import FlaggedMessage
        from src.events.schemas import BulkScanCompletedEvent

        scan_id = uuid4()
        mock_flagged = [
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
        mock_service.process_collected_messages = AsyncMock(return_value=mock_flagged)

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=uuid4(),
            messages_scanned=50,
        )

        with patch(
            "src.bulk_content_scan.nats_handler.get_platform_id",
            new=AsyncMock(return_value="test_platform_123"),
        ):
            await handle_scan_completed(event, mock_service, mock_publisher)

        mock_publisher.publish.assert_called_once()
        call_args = mock_publisher.publish.call_args

        assert call_args[1]["scan_id"] == scan_id
        assert call_args[1]["messages_scanned"] == 50
        assert call_args[1]["messages_flagged"] == 1


class TestBulkScanHandlerRegistration:
    """Test that handlers can be registered with EventSubscriber."""

    def test_handler_functions_are_async(self):
        """All handlers must be async functions."""
        import asyncio

        from src.bulk_content_scan.nats_handler import (
            handle_message_batch,
            handle_scan_completed,
        )

        assert asyncio.iscoroutinefunction(handle_message_batch)
        assert asyncio.iscoroutinefunction(handle_scan_completed)
