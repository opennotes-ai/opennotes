"""
Tests for BulkScanProgressEvent schema.

Tests for the progress event that streams message scores and thresholds
when vibecheck_debug_mode is enabled.
"""

from uuid import uuid4


class TestMessageScoreInfo:
    """Tests for MessageScoreInfo schema."""

    def test_message_score_info_exists(self):
        """MessageScoreInfo schema should exist."""
        from src.events.schemas import MessageScoreInfo

        assert MessageScoreInfo is not None

    def test_message_score_info_basic_fields(self):
        """MessageScoreInfo should have required fields."""
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="123456789",
            channel_id="987654321",
            similarity_score=0.72,
            threshold=0.60,
            is_flagged=True,
        )
        assert info.message_id == "123456789"
        assert info.channel_id == "987654321"
        assert info.similarity_score == 0.72
        assert info.threshold == 0.60
        assert info.is_flagged is True

    def test_message_score_info_optional_matched_claim(self):
        """matched_claim should be optional."""
        from src.events.schemas import MessageScoreInfo

        info_without = MessageScoreInfo(
            message_id="123",
            channel_id="456",
            similarity_score=0.45,
            threshold=0.60,
            is_flagged=False,
        )
        assert info_without.matched_claim is None

        info_with = MessageScoreInfo(
            message_id="123",
            channel_id="456",
            similarity_score=0.72,
            threshold=0.60,
            is_flagged=True,
            matched_claim="This is the matched claim",
        )
        assert info_with.matched_claim == "This is the matched claim"


class TestBulkScanProgressEvent:
    """Tests for BulkScanProgressEvent schema."""

    def test_bulk_scan_progress_event_type_exists(self):
        """BULK_SCAN_PROGRESS event type should exist."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_PROGRESS")
        assert EventType.BULK_SCAN_PROGRESS.value == "bulk_scan.progress"

    def test_bulk_scan_progress_event_exists(self):
        """BulkScanProgressEvent schema should exist."""
        from src.events.schemas import BulkScanProgressEvent

        assert BulkScanProgressEvent is not None

    def test_bulk_scan_progress_event_basic_creation(self):
        """BulkScanProgressEvent should be creatable with required fields."""
        from src.events.schemas import BulkScanProgressEvent, MessageScoreInfo

        scan_id = uuid4()
        community_server_id = uuid4()
        platform_id = "1234567890123456789"

        event = BulkScanProgressEvent(
            event_id="evt_test123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            platform_id=platform_id,
            batch_number=1,
            messages_in_batch=50,
            message_scores=[
                MessageScoreInfo(
                    message_id="msg1",
                    channel_id="ch1",
                    similarity_score=0.72,
                    threshold=0.60,
                    is_flagged=True,
                    matched_claim="Claim text",
                ),
                MessageScoreInfo(
                    message_id="msg2",
                    channel_id="ch1",
                    similarity_score=0.45,
                    threshold=0.60,
                    is_flagged=False,
                ),
            ],
            threshold_used=0.60,
        )

        assert event.scan_id == scan_id
        assert event.community_server_id == community_server_id
        assert event.platform_id == platform_id
        assert event.batch_number == 1
        assert event.messages_in_batch == 50
        assert len(event.message_scores) == 2
        assert event.threshold_used == 0.60

    def test_bulk_scan_progress_event_in_event_union(self):
        """BulkScanProgressEvent should be part of EventUnion."""
        from src.events.schemas import BulkScanProgressEvent, EventUnion

        assert BulkScanProgressEvent in EventUnion.__args__
