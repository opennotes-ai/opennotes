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

    def test_bulk_scan_all_batches_transmitted_event_type_exists(self):
        """AC #1: NATS subject for all batches transmitted must be defined."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_ALL_BATCHES_TRANSMITTED")
        assert (
            EventType.BULK_SCAN_ALL_BATCHES_TRANSMITTED.value == "bulk_scan.all_batches_transmitted"
        )

    def test_bulk_scan_processing_finished_event_type_exists(self):
        """AC #2: NATS subject for processing finished must be defined."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_PROCESSING_FINISHED")
        assert EventType.BULK_SCAN_PROCESSING_FINISHED.value == "bulk_scan.processing_finished"

    def test_bulk_scan_results_event_type_exists(self):
        """AC #1: NATS subject bulk-content-scan.results must be defined."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_RESULTS")
        assert EventType.BULK_SCAN_RESULTS.value == "bulk_scan.results"

    def test_bulk_scan_progress_event_type_exists(self):
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_PROGRESS")
        assert EventType.BULK_SCAN_PROGRESS.value == "bulk_scan.progress"

    def test_bulk_scan_failed_event_type_exists(self):
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_FAILED")
        assert EventType.BULK_SCAN_FAILED.value == "bulk_scan.failed"


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
                "community_server_id": "guild_123",
                "content": "Test message",
                "author_id": "user_1",
                "timestamp": datetime.now(UTC),
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


class TestBulkScanAllBatchesTransmittedEvent:
    """Test BulkScanAllBatchesTransmittedEvent schema."""

    def test_can_create_valid_event(self):
        """BulkScanAllBatchesTransmittedEvent should validate with correct fields."""
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
        )

        assert event.scan_id == scan_id
        assert event.community_server_id == community_server_id
        assert event.messages_scanned == 100

    def test_event_type_is_correct(self):
        """BulkScanAllBatchesTransmittedEvent should have correct event_type."""
        from src.events.schemas import BulkScanAllBatchesTransmittedEvent, EventType

        event = BulkScanAllBatchesTransmittedEvent(
            event_id="evt_123",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            messages_scanned=50,
        )

        assert event.event_type == EventType.BULK_SCAN_ALL_BATCHES_TRANSMITTED


class TestBulkScanProcessingFinishedEvent:
    """Test BulkScanProcessingFinishedEvent schema."""

    def test_can_create_valid_event(self):
        """BulkScanProcessingFinishedEvent should validate with correct fields."""
        from src.events.schemas import BulkScanProcessingFinishedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanProcessingFinishedEvent(
            event_id="evt_123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            messages_scanned=100,
            messages_flagged=5,
        )

        assert event.scan_id == scan_id
        assert event.community_server_id == community_server_id
        assert event.messages_scanned == 100
        assert event.messages_flagged == 5

    def test_event_type_is_correct(self):
        """BulkScanProcessingFinishedEvent should have correct event_type."""
        from src.events.schemas import BulkScanProcessingFinishedEvent, EventType

        event = BulkScanProcessingFinishedEvent(
            event_id="evt_123",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            messages_scanned=50,
            messages_flagged=2,
        )

        assert event.event_type == EventType.BULK_SCAN_PROCESSING_FINISHED


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


class TestBulkScanProgressEvent:
    """Test BulkScanProgressEvent schema (replaces deleted test_bulk_scan_progress_for_all.py)."""

    def _make_event(self, **overrides):
        from src.events.schemas import BulkScanProgressEvent

        defaults = {
            "event_id": "evt_progress_1",
            "scan_id": uuid4(),
            "community_server_id": uuid4(),
            "platform_community_server_id": "guild_123456",
            "batch_number": 1,
            "messages_in_batch": 25,
            "threshold_used": 0.75,
        }
        defaults.update(overrides)
        return BulkScanProgressEvent(**defaults)

    def test_can_create_with_valid_fields(self):
        event = self._make_event()
        assert event.batch_number == 1
        assert event.messages_in_batch == 25
        assert event.platform_community_server_id == "guild_123456"
        assert event.threshold_used == 0.75

    def test_event_type_is_correct(self):
        from src.events.schemas import EventType

        event = self._make_event()
        assert event.event_type == EventType.BULK_SCAN_PROGRESS

    def test_channel_ids_defaults_to_empty_list(self):
        event = self._make_event()
        assert event.channel_ids == []

    def test_channel_ids_accepts_list(self):
        event = self._make_event(channel_ids=["ch_1", "ch_2", "ch_3"])
        assert event.channel_ids == ["ch_1", "ch_2", "ch_3"]

    def test_messages_processed_defaults_to_zero(self):
        event = self._make_event()
        assert event.messages_processed == 0

    def test_messages_processed_accepts_value(self):
        event = self._make_event(messages_processed=42)
        assert event.messages_processed == 42

    def test_messages_skipped_defaults_to_zero(self):
        event = self._make_event()
        assert event.messages_skipped == 0

    def test_message_scores_defaults_to_empty_list(self):
        event = self._make_event()
        assert event.message_scores == []

    def test_message_scores_accepts_list(self):
        from src.events.schemas import MessageScoreInfo

        score = MessageScoreInfo(
            message_id="msg_1",
            channel_id="ch_1",
            similarity_score=0.85,
            threshold=0.75,
            is_flagged=True,
            matched_claim="Test claim",
        )
        event = self._make_event(message_scores=[score])
        assert len(event.message_scores) == 1
        assert event.message_scores[0].similarity_score == 0.85
        assert event.message_scores[0].is_flagged is True

    def test_threshold_used_is_required(self):
        import pytest
        from pydantic import ValidationError

        from src.events.schemas import BulkScanProgressEvent

        with pytest.raises(ValidationError):
            BulkScanProgressEvent(
                event_id="evt_1",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                platform_community_server_id="guild_1",
                batch_number=1,
                messages_in_batch=10,
            )

    def test_batch_number_must_be_positive(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self._make_event(batch_number=0)


class TestBulkScanFailedEvent:
    """Test BulkScanFailedEvent schema."""

    def test_can_create_valid_event(self):
        from src.events.schemas import BulkScanFailedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanFailedEvent(
            event_id="evt_fail_1",
            scan_id=scan_id,
            community_server_id=community_server_id,
            error_message="Redis connection timed out",
        )

        assert event.scan_id == scan_id
        assert event.community_server_id == community_server_id
        assert event.error_message == "Redis connection timed out"

    def test_event_type_is_correct(self):
        from src.events.schemas import BulkScanFailedEvent, EventType

        event = BulkScanFailedEvent(
            event_id="evt_fail_2",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            error_message="Scan failed",
        )

        assert event.event_type == EventType.BULK_SCAN_FAILED
