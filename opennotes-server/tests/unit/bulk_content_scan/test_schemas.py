"""Tests for Bulk Content Scan API Pydantic schemas."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError


class TestBulkScanCreateRequest:
    """Test BulkScanCreateRequest schema for initiating scans."""

    def test_can_create_valid_request(self):
        """AC #5: POST /bulk-content-scan/scans requires valid request body."""
        from src.bulk_content_scan.schemas import BulkScanCreateRequest

        community_server_id = uuid4()
        request = BulkScanCreateRequest(
            community_server_id=community_server_id,
            scan_window_days=7,
            channel_ids=["channel_1", "channel_2"],
        )

        assert request.community_server_id == community_server_id
        assert request.scan_window_days == 7
        assert request.channel_ids == ["channel_1", "channel_2"]

    def test_channel_ids_defaults_to_empty_list(self):
        """Channel IDs should default to empty list (all channels)."""
        from src.bulk_content_scan.schemas import BulkScanCreateRequest

        request = BulkScanCreateRequest(
            community_server_id=uuid4(),
            scan_window_days=7,
        )

        assert request.channel_ids == []

    def test_scan_window_days_minimum_is_1(self):
        """Scan window must be at least 1 day."""
        from src.bulk_content_scan.schemas import BulkScanCreateRequest

        with pytest.raises(ValidationError) as exc_info:
            BulkScanCreateRequest(
                community_server_id=uuid4(),
                scan_window_days=0,
            )

        assert "scan_window_days" in str(exc_info.value)

    def test_scan_window_days_maximum_is_30(self):
        """Scan window must not exceed 30 days."""
        from src.bulk_content_scan.schemas import BulkScanCreateRequest

        with pytest.raises(ValidationError) as exc_info:
            BulkScanCreateRequest(
                community_server_id=uuid4(),
                scan_window_days=31,
            )

        assert "scan_window_days" in str(exc_info.value)


class TestBulkScanResponse:
    """Test BulkScanResponse schema for scan status."""

    def test_can_create_response(self):
        """AC #5: POST returns scan_id in response."""
        from src.bulk_content_scan.schemas import BulkScanResponse

        scan_id = uuid4()
        now = datetime.now(UTC)

        response = BulkScanResponse(
            scan_id=scan_id,
            status="in_progress",
            initiated_at=now,
            completed_at=None,
            messages_scanned=0,
            messages_flagged=0,
        )

        assert response.scan_id == scan_id
        assert response.status == "in_progress"
        assert response.initiated_at == now
        assert response.completed_at is None

    def test_completed_at_can_be_set(self):
        """Completed timestamp should be settable."""
        from src.bulk_content_scan.schemas import BulkScanResponse

        now = datetime.now(UTC)
        response = BulkScanResponse(
            scan_id=uuid4(),
            status="completed",
            initiated_at=now,
            completed_at=now,
            messages_scanned=100,
            messages_flagged=5,
        )

        assert response.completed_at == now
        assert response.messages_scanned == 100
        assert response.messages_flagged == 5


class TestFlaggedMessage:
    """Test FlaggedMessage schema for individual flagged results."""

    def test_can_create_flagged_message(self):
        """AC #4: Results include match scores, source info, and original content."""
        from src.bulk_content_scan.schemas import FlaggedMessage

        now = datetime.now(UTC)
        flagged = FlaggedMessage(
            message_id="msg_12345",
            channel_id="ch_67890",
            content="Some potentially misleading content",
            author_id="user_54321",
            timestamp=now,
            match_score=0.85,
            matched_claim="Original fact-check claim text",
            matched_source="https://snopes.com/article",
        )

        assert flagged.message_id == "msg_12345"
        assert flagged.channel_id == "ch_67890"
        assert flagged.content == "Some potentially misleading content"
        assert flagged.author_id == "user_54321"
        assert flagged.timestamp == now
        assert flagged.match_score == 0.85
        assert flagged.matched_claim == "Original fact-check claim text"
        assert flagged.matched_source == "https://snopes.com/article"

    def test_match_score_must_be_in_range(self):
        """Match score must be between 0 and 1."""
        from src.bulk_content_scan.schemas import FlaggedMessage

        with pytest.raises(ValidationError):
            FlaggedMessage(
                message_id="msg_1",
                channel_id="ch_1",
                content="Test",
                author_id="user_1",
                timestamp=datetime.now(UTC),
                match_score=1.5,  # Invalid
                matched_claim="Claim",
                matched_source="https://example.com",
            )


class TestBulkScanResultsResponse:
    """Test BulkScanResultsResponse schema for full scan results."""

    def test_can_create_results_response(self):
        """AC #6: GET /scans/{scan_id} returns status and flagged results."""
        from src.bulk_content_scan.schemas import BulkScanResultsResponse, FlaggedMessage

        scan_id = uuid4()
        flagged_messages = [
            FlaggedMessage(
                message_id="msg_1",
                channel_id="ch_1",
                content="Flagged content",
                author_id="user_1",
                timestamp=datetime.now(UTC),
                match_score=0.9,
                matched_claim="Claim",
                matched_source="https://example.com",
            )
        ]

        response = BulkScanResultsResponse(
            scan_id=scan_id,
            status="completed",
            messages_scanned=100,
            flagged_messages=flagged_messages,
        )

        assert response.scan_id == scan_id
        assert response.status == "completed"
        assert response.messages_scanned == 100
        assert len(response.flagged_messages) == 1

    def test_can_create_empty_results(self):
        """Results can have no flagged messages."""
        from src.bulk_content_scan.schemas import BulkScanResultsResponse

        response = BulkScanResultsResponse(
            scan_id=uuid4(),
            status="completed",
            messages_scanned=50,
            flagged_messages=[],
        )

        assert len(response.flagged_messages) == 0


class TestCreateNoteRequestsRequest:
    """Test CreateNoteRequestsRequest schema for note request creation."""

    def test_can_create_request(self):
        """AC #7: POST /scans/{scan_id}/note-requests accepts message IDs."""
        from src.bulk_content_scan.schemas import CreateNoteRequestsRequest

        request = CreateNoteRequestsRequest(
            message_ids=["msg_1", "msg_2", "msg_3"],
            generate_ai_notes=True,
        )

        assert request.message_ids == ["msg_1", "msg_2", "msg_3"]
        assert request.generate_ai_notes is True

    def test_generate_ai_notes_defaults_to_false(self):
        """AI note generation should default to false."""
        from src.bulk_content_scan.schemas import CreateNoteRequestsRequest

        request = CreateNoteRequestsRequest(
            message_ids=["msg_1"],
        )

        assert request.generate_ai_notes is False

    def test_requires_at_least_one_message(self):
        """At least one message ID must be provided."""
        from src.bulk_content_scan.schemas import CreateNoteRequestsRequest

        with pytest.raises(ValidationError):
            CreateNoteRequestsRequest(
                message_ids=[],
            )


class TestNoteRequestsResponse:
    """Test NoteRequestsResponse schema for note request creation results."""

    def test_can_create_response(self):
        """AC #7: Response includes count of created note requests."""
        from src.bulk_content_scan.schemas import NoteRequestsResponse

        response = NoteRequestsResponse(
            created_count=3,
            request_ids=["req_1", "req_2", "req_3"],
        )

        assert response.created_count == 3
        assert len(response.request_ids) == 3


class TestBulkScanStatus:
    """Test BulkScanStatus enum."""

    def test_status_enum_values(self):
        """Status enum should have expected values."""
        from src.bulk_content_scan.schemas import BulkScanStatus

        assert BulkScanStatus.PENDING == "pending"
        assert BulkScanStatus.IN_PROGRESS == "in_progress"
        assert BulkScanStatus.COMPLETED == "completed"
        assert BulkScanStatus.FAILED == "failed"
