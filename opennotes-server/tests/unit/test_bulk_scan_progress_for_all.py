"""
Tests for bulk scan progress events for ALL scans (not just debug mode).

AC #1: Server publishes BULK_SCAN_PROGRESS event every 5 seconds during
processing (with channel_ids and messages_processed)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.bulk_content_scan.schemas import BulkScanMessage
from src.events.schemas import BulkScanMessageBatchEvent


class TestProgressEventSchema:
    """Tests for BulkScanProgressEvent schema modifications."""

    def test_progress_event_has_channel_ids_field(self):
        """Progress event should have channel_ids field."""
        from src.events.schemas import BulkScanProgressEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanProgressEvent(
            event_id="evt_test",
            scan_id=scan_id,
            community_server_id=community_server_id,
            platform_community_server_id="123456789",
            batch_number=1,
            messages_in_batch=50,
            threshold_used=0.60,
            channel_ids=["ch1", "ch2", "ch3"],
        )

        assert hasattr(event, "channel_ids")
        assert event.channel_ids == ["ch1", "ch2", "ch3"]

    def test_progress_event_has_messages_processed_field(self):
        """Progress event should have messages_processed field."""
        from src.events.schemas import BulkScanProgressEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanProgressEvent(
            event_id="evt_test",
            scan_id=scan_id,
            community_server_id=community_server_id,
            platform_community_server_id="123456789",
            batch_number=1,
            messages_in_batch=50,
            threshold_used=0.60,
            messages_processed=150,
        )

        assert hasattr(event, "messages_processed")
        assert event.messages_processed == 150

    def test_progress_event_message_scores_optional_defaults_empty(self):
        """message_scores should be optional and default to empty list."""
        from src.events.schemas import BulkScanProgressEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanProgressEvent(
            event_id="evt_test",
            scan_id=scan_id,
            community_server_id=community_server_id,
            platform_community_server_id="123456789",
            batch_number=1,
            messages_in_batch=50,
            threshold_used=0.60,
        )

        assert event.message_scores == []


class TestProgressEventForAllScans:
    """Tests for progress event emission for all scans (not just debug mode)."""

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
                channel_id="ch2",
                community_server_id="123456789",
                author_id="author2",
                content="Another test message for the scan",
                timestamp="2025-01-01T00:01:00Z",
            ),
        ]

    @pytest.mark.asyncio
    async def test_progress_event_published_for_non_debug_mode(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_nats_client,
        sample_messages,
    ):
        """Progress event should be published even when debug_mode is False."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.bulk_content_scan.service import BulkContentScanService
        from src.events.schemas import BulkScanProgressEvent

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

        with patch("src.bulk_content_scan.nats_handler.event_publisher") as mock_publisher:
            mock_publisher.publish_event = AsyncMock()

            await handle_message_batch_with_progress(
                event=event,
                service=service,
                nats_client=mock_nats_client,
                platform_id="123456789",
                debug_mode=False,
            )

            mock_publisher.publish_event.assert_called_once()
            published_event = mock_publisher.publish_event.call_args[0][0]
            assert isinstance(published_event, BulkScanProgressEvent)

    @pytest.mark.asyncio
    async def test_progress_event_includes_channel_ids(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_nats_client,
        sample_messages,
    ):
        """Progress event should include channel_ids from processed messages."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.bulk_content_scan.service import BulkContentScanService
        from src.events.schemas import BulkScanProgressEvent

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

        with patch("src.bulk_content_scan.nats_handler.event_publisher") as mock_publisher:
            mock_publisher.publish_event = AsyncMock()

            await handle_message_batch_with_progress(
                event=event,
                service=service,
                nats_client=mock_nats_client,
                platform_id="123456789",
                debug_mode=False,
            )

            published_event = mock_publisher.publish_event.call_args[0][0]
            assert isinstance(published_event, BulkScanProgressEvent)
            assert set(published_event.channel_ids) == {"ch1", "ch2"}

    @pytest.mark.asyncio
    async def test_progress_event_includes_messages_processed(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_nats_client,
        sample_messages,
    ):
        """Progress event should include messages_processed count."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.bulk_content_scan.service import BulkContentScanService
        from src.events.schemas import BulkScanProgressEvent

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

        with (
            patch.object(service, "get_processed_count", return_value=150),
            patch("src.bulk_content_scan.nats_handler.event_publisher") as mock_publisher,
        ):
            mock_publisher.publish_event = AsyncMock()

            await handle_message_batch_with_progress(
                event=event,
                service=service,
                nats_client=mock_nats_client,
                platform_id="123456789",
                debug_mode=False,
            )

            published_event = mock_publisher.publish_event.call_args[0][0]
            assert isinstance(published_event, BulkScanProgressEvent)
            assert published_event.messages_processed == 150

    @pytest.mark.asyncio
    async def test_progress_event_has_empty_scores_in_non_debug_mode(
        self,
        mock_session,
        mock_embedding_service,
        mock_redis,
        mock_nats_client,
        sample_messages,
    ):
        """Progress event should have empty message_scores when not in debug mode."""
        from src.bulk_content_scan.nats_handler import handle_message_batch_with_progress
        from src.bulk_content_scan.service import BulkContentScanService
        from src.events.schemas import BulkScanProgressEvent

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

        with patch("src.bulk_content_scan.nats_handler.event_publisher") as mock_publisher:
            mock_publisher.publish_event = AsyncMock()

            await handle_message_batch_with_progress(
                event=event,
                service=service,
                nats_client=mock_nats_client,
                platform_id="123456789",
                debug_mode=False,
            )

            published_event = mock_publisher.publish_event.call_args[0][0]
            assert isinstance(published_event, BulkScanProgressEvent)
            assert published_event.message_scores == []
