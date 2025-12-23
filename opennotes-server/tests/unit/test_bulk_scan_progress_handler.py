"""
Tests for bulk scan progress event emission when vibecheck_debug_mode is enabled.

Tests that the NATS handler emits progress events with scores for all messages
when the community server has vibecheck_debug_mode enabled.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.bulk_content_scan.schemas import BulkScanMessage
from src.events.schemas import BulkScanMessageBatchEvent, EventType


class TestProgressEventEmission:
    """Tests for progress event emission during batch processing."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        return MagicMock()

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return AsyncMock()

    @pytest.fixture
    def mock_nats_client(self):
        """Create a mock NATS client."""
        client = AsyncMock()
        client.publish = AsyncMock()
        return client

    @pytest.fixture
    def sample_messages(self) -> list[BulkScanMessage]:
        """Create sample messages for testing."""
        return [
            BulkScanMessage(
                message_id="msg1",
                channel_id="ch1",
                community_server_id="123456789",
                author_id="author1",
                content="This is a test message with enough content",
                timestamp="2025-01-01T00:00:00Z",
            ),
            BulkScanMessage(
                message_id="msg2",
                channel_id="ch1",
                community_server_id="123456789",
                author_id="author2",
                content="Another test message for the scan",
                timestamp="2025-01-01T00:01:00Z",
            ),
        ]

    @pytest.mark.asyncio
    async def test_progress_event_published_when_debug_mode_enabled(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_nats_client,
        sample_messages,
    ):
        """Progress event should be published when vibecheck_debug_mode is True."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.bulk_content_scan.service import BulkContentScanService

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanMessageBatchEvent(
            event_id="evt_test",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=sample_messages,
            batch_number=1,
            is_final_batch=False,
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        await handle_message_batch_with_progress(
            event=event,
            service=service,
            nats_client=mock_nats_client,
            platform_id="123456789",
            debug_mode=True,
        )

        mock_nats_client.publish.assert_called()
        call_args = mock_nats_client.publish.call_args
        assert call_args.kwargs["event_type"] == EventType.BULK_SCAN_PROGRESS

    @pytest.mark.asyncio
    async def test_progress_event_not_published_when_debug_mode_disabled(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_nats_client,
        sample_messages,
    ):
        """Progress event should NOT be published when vibecheck_debug_mode is False."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.bulk_content_scan.service import BulkContentScanService

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanMessageBatchEvent(
            event_id="evt_test",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=sample_messages,
            batch_number=1,
            is_final_batch=False,
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        await handle_message_batch_with_progress(
            event=event,
            service=service,
            nats_client=mock_nats_client,
            platform_id="123456789",
            debug_mode=False,
        )

        for call in mock_nats_client.publish.call_args_list:
            if call.kwargs.get("event_type") == EventType.BULK_SCAN_PROGRESS:
                pytest.fail("Progress event should not be published when debug_mode is False")

    @pytest.mark.asyncio
    async def test_progress_event_includes_all_message_scores(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_nats_client,
        sample_messages,
    ):
        """Progress event should include scores for ALL messages, not just flagged ones."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.bulk_content_scan.service import BulkContentScanService

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanMessageBatchEvent(
            event_id="evt_test",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=sample_messages,
            batch_number=1,
            is_final_batch=False,
        )

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        with patch.object(service, "process_messages_with_scores") as mock_process:
            mock_process.return_value = ([], [])

            await handle_message_batch_with_progress(
                event=event,
                service=service,
                nats_client=mock_nats_client,
                platform_id="123456789",
                debug_mode=True,
            )

            mock_process.assert_called_once()
