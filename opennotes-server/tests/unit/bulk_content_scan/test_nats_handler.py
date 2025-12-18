"""Tests for Bulk Content Scan NATS event handlers."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.bulk_content_scan.schemas import FlaggedMessage


@pytest.fixture
def mock_service():
    """Create a mock BulkContentScanService."""
    service = AsyncMock()
    service.process_messages = AsyncMock(return_value=[])
    service.append_flagged_result = AsyncMock()
    service.get_flagged_results = AsyncMock(return_value=[])
    service.complete_scan = AsyncMock()
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
        assert call_kwargs["platform_id"] == "test_platform_123"
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
    async def test_handles_missing_platform_id(self, mock_service, sample_messages):
        """Verify graceful handling when platform_id lookup fails."""
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
            new=AsyncMock(return_value=None),
        ):
            await handle_message_batch(event, mock_service)

        mock_service.process_messages.assert_not_called()
        mock_service.append_flagged_result.assert_not_called()


class TestHandleScanCompleted:
    """Test handling of BULK_SCAN_COMPLETED events with accumulated results."""

    @pytest.mark.asyncio
    async def test_gets_accumulated_flagged_results(self, mock_service, mock_publisher):
        """Verify get_flagged_results() is called to retrieve accumulated results."""
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

        await handle_scan_completed(event, mock_service, mock_publisher)

        mock_service.get_flagged_results.assert_called_once_with(scan_id)

    @pytest.mark.asyncio
    async def test_completes_scan_with_accumulated_count(
        self, mock_service, mock_publisher, sample_flagged_message
    ):
        """Verify complete_scan() receives correct flagged count from accumulated results."""
        from src.bulk_content_scan.nats_handler import handle_scan_completed
        from src.events.schemas import BulkScanCompletedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        flagged_results = [sample_flagged_message, sample_flagged_message]
        mock_service.get_flagged_results = AsyncMock(return_value=flagged_results)

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
        )

        await handle_scan_completed(event, mock_service, mock_publisher)

        mock_service.complete_scan.assert_called_once_with(
            scan_id=scan_id,
            messages_scanned=100,
            messages_flagged=2,
        )

    @pytest.mark.asyncio
    async def test_publishes_accumulated_results(
        self, mock_service, mock_publisher, sample_flagged_message
    ):
        """Verify publisher.publish() receives correct accumulated results."""
        from src.bulk_content_scan.nats_handler import handle_scan_completed
        from src.events.schemas import BulkScanCompletedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        flagged_results = [sample_flagged_message]
        mock_service.get_flagged_results = AsyncMock(return_value=flagged_results)

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=50,
        )

        await handle_scan_completed(event, mock_service, mock_publisher)

        mock_publisher.publish.assert_called_once()
        call_kwargs = mock_publisher.publish.call_args[1]
        assert call_kwargs["scan_id"] == scan_id
        assert call_kwargs["messages_scanned"] == 50
        assert call_kwargs["messages_flagged"] == 1
        assert len(call_kwargs["flagged_messages"]) == 1

    @pytest.mark.asyncio
    async def test_handles_empty_flagged_results(self, mock_service, mock_publisher):
        """Verify correct handling when no messages were flagged."""
        from src.bulk_content_scan.nats_handler import handle_scan_completed
        from src.events.schemas import BulkScanCompletedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        mock_service.get_flagged_results = AsyncMock(return_value=[])

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
        )

        await handle_scan_completed(event, mock_service, mock_publisher)

        mock_service.complete_scan.assert_called_once_with(
            scan_id=scan_id,
            messages_scanned=100,
            messages_flagged=0,
        )

        mock_publisher.publish.assert_called_once()
        call_kwargs = mock_publisher.publish.call_args[1]
        assert call_kwargs["messages_flagged"] == 0
        assert call_kwargs["flagged_messages"] == []


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
