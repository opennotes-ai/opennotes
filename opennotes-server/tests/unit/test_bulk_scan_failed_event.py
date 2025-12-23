"""
Tests for BulkScanFailedEvent schema.

Tests for the failure event published when critical errors occur during bulk scan.
"""

from uuid import uuid4

import pytest


class TestBulkScanFailedEvent:
    """Tests for BulkScanFailedEvent schema."""

    def test_bulk_scan_failed_event_type_exists(self):
        """BULK_SCAN_FAILED event type should exist."""
        from src.events.schemas import EventType

        assert hasattr(EventType, "BULK_SCAN_FAILED")
        assert EventType.BULK_SCAN_FAILED.value == "bulk_scan.failed"

    def test_bulk_scan_failed_event_exists(self):
        """BulkScanFailedEvent schema should exist."""
        from src.events.schemas import BulkScanFailedEvent

        assert BulkScanFailedEvent is not None

    def test_bulk_scan_failed_event_basic_creation(self):
        """BulkScanFailedEvent should be creatable with required fields."""
        from src.events.schemas import BulkScanFailedEvent

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanFailedEvent(
            event_id="evt_test123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            error_message="Database connection failed",
        )

        assert event.scan_id == scan_id
        assert event.community_server_id == community_server_id
        assert event.error_message == "Database connection failed"

    def test_bulk_scan_failed_event_has_correct_event_type(self):
        """BulkScanFailedEvent should have BULK_SCAN_FAILED event type."""
        from src.events.schemas import BulkScanFailedEvent, EventType

        scan_id = uuid4()
        community_server_id = uuid4()

        event = BulkScanFailedEvent(
            event_id="evt_test123",
            scan_id=scan_id,
            community_server_id=community_server_id,
            error_message="Test error",
        )

        assert event.event_type == EventType.BULK_SCAN_FAILED

    def test_bulk_scan_failed_event_in_event_union(self):
        """BulkScanFailedEvent should be part of EventUnion."""
        from src.events.schemas import BulkScanFailedEvent, EventUnion

        assert BulkScanFailedEvent in EventUnion.__args__

    def test_bulk_scan_failed_event_error_message_required(self):
        """error_message should be required."""
        from pydantic import ValidationError

        from src.events.schemas import BulkScanFailedEvent

        with pytest.raises(ValidationError):
            BulkScanFailedEvent(
                event_id="evt_test123",
                scan_id=uuid4(),
                community_server_id=uuid4(),
            )

    def test_bulk_scan_failed_event_error_message_cannot_be_empty(self):
        """error_message should not be empty."""
        from pydantic import ValidationError

        from src.events.schemas import BulkScanFailedEvent

        with pytest.raises(ValidationError):
            BulkScanFailedEvent(
                event_id="evt_test123",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                error_message="",
            )
