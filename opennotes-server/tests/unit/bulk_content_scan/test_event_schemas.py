"""Tests for Bulk Content Scan NATS event types and schemas."""

from datetime import UTC, datetime
from uuid import uuid4


class TestBulkScanEventTypes:
    """Test that bulk scan event types are defined in EventType enum."""

    def test_bulk_scan_initiated_event_type_exists(self):
        """AC #1: NATS subject bulk-content-scan.initiate must be defined."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_INITIATED")
        assert EventType.BULK_SCAN_INITIATED.value == "bulk_scan.initiated"

    def test_bulk_scan_message_batch_event_type_exists(self):
        """AC #1: NATS subject bulk-content-scan.message-batch must be defined."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_MESSAGE_BATCH")
        assert EventType.BULK_SCAN_MESSAGE_BATCH.value == "bulk_scan.message_batch"

    def test_bulk_scan_completed_event_type_exists(self):
        """AC #1: NATS subject bulk-content-scan.completion must be defined."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_COMPLETED")
        assert EventType.BULK_SCAN_COMPLETED.value == "bulk_scan.completed"

    def test_bulk_scan_results_event_type_exists(self):
        """AC #1: NATS subject bulk-content-scan.results must be defined."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_RESULTS")
        assert EventType.BULK_SCAN_RESULTS.value == "bulk_scan.results"


class TestBulkScanInitiatedEvent:
    """Test BulkScanInitiatedEvent schema."""

    def test_can_create_valid_event(self):
        """BulkScanInitiatedEvent should validate with correct fields."""
        from src.events.schemas import BulkScanInitiatedEvent

        scan_id = uuid4()
        community_server_id = uuid4()
        initiated_by_user_id = uuid4()

        event = BulkScanInitiatedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            initiated_by_user_id=initiated_by_user_id,
            scan_window_days=7,
            channel_ids=["channel_1", "channel_2"],
        )

        assert event.scan_id == scan_id
        assert event.community_server_id == community_server_id
        assert event.initiated_by_user_id == initiated_by_user_id
        assert event.scan_window_days == 7
        assert event.channel_ids == ["channel_1", "channel_2"]

    def test_event_type_is_correct(self):
        """BulkScanInitiatedEvent should have correct event_type."""
        from src.events.schemas import BulkScanInitiatedEvent, EventType

        event = BulkScanInitiatedEvent(
            event_id="evt_123",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            initiated_by_user_id=uuid4(),
            scan_window_days=7,
            channel_ids=[],
        )

        assert event.event_type == EventType.BULK_SCAN_INITIATED


class TestBulkScanMessageBatchEvent:
    """Test BulkScanMessageBatchEvent schema."""

    def test_can_create_valid_event(self):
        """BulkScanMessageBatchEvent should validate with correct fields."""
        from src.events.schemas import BulkScanMessageBatchEvent

        scan_id = uuid4()
        community_server_id = uuid4()
        messages = [
            {
                "message_id": "msg_1",
                "channel_id": "ch_1",
                "content": "Test message",
                "author_id": "user_1",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ]

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages=messages,
            batch_number=1,
            is_final_batch=False,
        )

        assert event.scan_id == scan_id
        assert event.community_server_id == community_server_id
        assert len(event.messages) == 1
        assert event.batch_number == 1
        assert event.is_final_batch is False

    def test_event_type_is_correct(self):
        """BulkScanMessageBatchEvent should have correct event_type."""
        from src.events.schemas import BulkScanMessageBatchEvent, EventType

        event = BulkScanMessageBatchEvent(
            event_id="evt_123",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            messages=[],
            batch_number=1,
            is_final_batch=True,
        )

        assert event.event_type == EventType.BULK_SCAN_MESSAGE_BATCH


class TestBulkScanCompletedEvent:
    """Test BulkScanCompletedEvent schema."""

    def test_can_create_valid_event(self):
        """BulkScanCompletedEvent should validate with correct fields."""
        from src.events.schemas import BulkScanCompletedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
        )

        assert event.scan_id == scan_id
        assert event.community_server_id == community_server_id
        assert event.messages_scanned == 100

    def test_event_type_is_correct(self):
        """BulkScanCompletedEvent should have correct event_type."""
        from src.events.schemas import BulkScanCompletedEvent, EventType

        event = BulkScanCompletedEvent(
            event_id="evt_123",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            messages_scanned=50,
        )

        assert event.event_type == EventType.BULK_SCAN_COMPLETED


class TestBulkScanResultsEvent:
    """Test BulkScanResultsEvent schema."""

    def test_can_create_valid_event(self):
        """BulkScanResultsEvent should validate with correct fields."""
        from src.events.schemas import BulkScanResultsEvent

        scan_id = uuid4()
        flagged_messages = [
            {
                "message_id": "msg_1",
                "channel_id": "ch_1",
                "content": "Suspicious content",
                "author_id": "user_1",
                "timestamp": datetime.now(UTC).isoformat(),
                "match_score": 0.85,
                "matched_claim": "Test claim",
                "matched_source": "https://example.com",
            }
        ]

        event = BulkScanResultsEvent(
            event_id="evt_123",
            scan_id=scan_id,
            messages_scanned=100,
            messages_flagged=1,
            flagged_messages=flagged_messages,
        )

        assert event.scan_id == scan_id
        assert event.messages_scanned == 100
        assert event.messages_flagged == 1
        assert len(event.flagged_messages) == 1

    def test_event_type_is_correct(self):
        """BulkScanResultsEvent should have correct event_type."""
        from src.events.schemas import BulkScanResultsEvent, EventType

        event = BulkScanResultsEvent(
            event_id="evt_123",
            scan_id=uuid4(),
            messages_scanned=50,
            messages_flagged=0,
            flagged_messages=[],
        )

        assert event.event_type == EventType.BULK_SCAN_RESULTS
