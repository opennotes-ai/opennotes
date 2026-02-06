"""Tests for create_note_requests_from_flagged_messages shared function
and RequestCreateAttributes first-class fields.

This module tests the shared note request creation logic extracted from
router.py and jsonapi_router.py (task-849.05), plus the first-class
similarity_score/dataset_name/dataset_item_id fields on RequestCreateAttributes.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.bulk_content_scan.schemas import FlaggedMessage, SimilarityMatch

SAMPLE_FACT_CHECK_ID = UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def sample_flagged_messages() -> list[FlaggedMessage]:
    """Create sample flagged messages for testing."""
    return [
        FlaggedMessage(
            message_id="msg_001",
            channel_id="ch_001",
            content="This is a test claim about vaccines",
            author_id="user_001",
            timestamp=datetime.now(UTC),
            matches=[
                SimilarityMatch(
                    score=0.85,
                    matched_claim="Vaccines cause autism",
                    matched_source="https://factcheck.org/vaccines",
                    fact_check_item_id=SAMPLE_FACT_CHECK_ID,
                )
            ],
        ),
        FlaggedMessage(
            message_id="msg_002",
            channel_id="ch_002",
            content="Another test claim about climate",
            author_id="user_002",
            timestamp=datetime.now(UTC),
            matches=[
                SimilarityMatch(
                    score=0.75,
                    matched_claim="Climate change is a hoax",
                    matched_source="https://factcheck.org/climate",
                    fact_check_item_id=SAMPLE_FACT_CHECK_ID,
                )
            ],
        ),
        FlaggedMessage(
            message_id="msg_003",
            channel_id="ch_001",
            content="Third test message",
            author_id="user_003",
            timestamp=datetime.now(UTC),
            matches=[
                SimilarityMatch(
                    score=0.90,
                    matched_claim="Election fraud claim",
                    matched_source="https://factcheck.org/election",
                    fact_check_item_id=SAMPLE_FACT_CHECK_ID,
                )
            ],
        ),
    ]


class TestCreateNoteRequestsFromFlaggedMessages:
    """Test the shared create_note_requests_from_flagged_messages function."""

    @pytest.mark.asyncio
    async def test_creates_requests_for_valid_message_ids(
        self, mock_session, sample_flagged_messages
    ):
        """Should create note requests for all valid message IDs."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001", "msg_002"]

        mock_request = MagicMock()
        mock_request.request_id = "bulkscan_test_001"

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            return_value=mock_request,
        ) as mock_create:
            result = await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert mock_create.call_count == 2
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_skips_messages_not_in_flagged_results(
        self, mock_session, sample_flagged_messages
    ):
        """Should skip message IDs that are not in flagged results."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001", "nonexistent_msg", "msg_002"]

        mock_request = MagicMock()
        mock_request.request_id = "bulkscan_test_001"

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            return_value=mock_request,
        ) as mock_create:
            result = await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert mock_create.call_count == 2
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_generates_correct_request_id_format(self, mock_session, sample_flagged_messages):
        """Request IDs should follow format: bulkscan_{scan_id_prefix}_{uuid}."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001"]

        captured_request_id = None

        async def capture_create(**kwargs):
            nonlocal captured_request_id
            captured_request_id = kwargs.get("request_id")
            mock_request = MagicMock()
            mock_request.request_id = captured_request_id
            return mock_request

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            side_effect=capture_create,
        ):
            await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert captured_request_id is not None
        assert captured_request_id.startswith("bulkscan_")
        assert scan_id.hex[:8] in captured_request_id

    @pytest.mark.asyncio
    async def test_passes_correct_metadata_to_request_service(
        self, mock_session, sample_flagged_messages
    ):
        """Should pass correct metadata including scan_id, matched_claim, etc."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001"]

        captured_kwargs = {}

        async def capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            mock_request = MagicMock()
            mock_request.request_id = kwargs.get("request_id")
            return mock_request

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            side_effect=capture_create,
        ):
            await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
                generate_ai_notes=True,
            )

        assert "request_metadata" in captured_kwargs
        metadata = captured_kwargs["request_metadata"]
        assert metadata["scan_id"] == str(scan_id)
        assert metadata["matched_claim"] == "Vaccines cause autism"
        assert metadata["matched_source"] == "https://factcheck.org/vaccines"
        assert metadata["match_score"] == 0.85
        assert metadata["generate_ai_notes"] is True

    @pytest.mark.asyncio
    async def test_passes_flagged_message_data_to_request_service(
        self, mock_session, sample_flagged_messages
    ):
        """Should pass flagged message content and metadata to RequestService."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001"]

        captured_kwargs = {}

        async def capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            mock_request = MagicMock()
            mock_request.request_id = kwargs.get("request_id")
            return mock_request

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            side_effect=capture_create,
        ):
            await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert captured_kwargs["content"] == "This is a test claim about vaccines"
        assert captured_kwargs["platform_message_id"] == "msg_001"
        assert captured_kwargs["platform_channel_id"] == "ch_001"
        assert captured_kwargs["platform_author_id"] == "user_001"
        assert captured_kwargs["similarity_score"] == 0.85
        assert captured_kwargs["community_server_id"] == community_server_id
        assert captured_kwargs["requested_by"] == str(user_id)

    @pytest.mark.asyncio
    async def test_commits_session_after_creating_requests(
        self, mock_session, sample_flagged_messages
    ):
        """Should commit the session after creating all requests."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001", "msg_002"]

        mock_request = MagicMock()
        mock_request.request_id = "bulkscan_test_001"

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            return_value=mock_request,
        ):
            await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_list_of_created_request_ids(self, mock_session, sample_flagged_messages):
        """Should return a list of created request IDs."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001", "msg_002"]

        call_count = 0

        async def create_with_id(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_request = MagicMock()
            mock_request.request_id = f"bulkscan_test_{call_count:03d}"
            return mock_request

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            side_effect=create_with_id,
        ):
            result = await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == "bulkscan_test_001"
        assert result[1] == "bulkscan_test_002"

    @pytest.mark.asyncio
    async def test_handles_request_service_error_gracefully(
        self, mock_session, sample_flagged_messages
    ):
        """Should continue processing when RequestService raises an error."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001", "msg_002", "msg_003"]

        call_count = 0

        async def create_with_error(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Database error")
            mock_request = MagicMock()
            mock_request.request_id = f"bulkscan_test_{call_count:03d}"
            return mock_request

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            side_effect=create_with_error,
        ):
            result = await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert len(result) == 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_message_ids_returns_empty_list(
        self, mock_session, sample_flagged_messages
    ):
        """Should return empty list when no message IDs are provided."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
        ) as mock_create:
            result = await create_note_requests_from_flagged_messages(
                message_ids=[],
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert result == []
        mock_create.assert_not_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_flagged_messages_returns_empty_list(self, mock_session):
        """Should return empty list when flagged_messages is empty."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
        ) as mock_create:
            result = await create_note_requests_from_flagged_messages(
                message_ids=["msg_001", "msg_002"],
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=[],
            )

        assert result == []
        mock_create.assert_not_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_correct_dataset_name_and_status(
        self, mock_session, sample_flagged_messages
    ):
        """Should set dataset_name to 'bulk_scan' and status to 'PENDING'."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001"]

        captured_kwargs = {}

        async def capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            mock_request = MagicMock()
            mock_request.request_id = kwargs.get("request_id")
            return mock_request

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            side_effect=capture_create,
        ):
            await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert captured_kwargs["dataset_name"] == "bulk_scan"
        assert captured_kwargs["status"] == "PENDING"
        assert captured_kwargs["priority"] == "normal"

    @pytest.mark.asyncio
    async def test_generates_ai_notes_flag_defaults_to_false(
        self, mock_session, sample_flagged_messages
    ):
        """generate_ai_notes should default to False."""
        from src.bulk_content_scan.service import create_note_requests_from_flagged_messages

        scan_id = uuid4()
        user_id = uuid4()
        community_server_id = uuid4()
        message_ids = ["msg_001"]

        captured_kwargs = {}

        async def capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            mock_request = MagicMock()
            mock_request.request_id = kwargs.get("request_id")
            return mock_request

        with patch(
            "src.notes.request_service.RequestService.create_from_message",
            new_callable=AsyncMock,
            side_effect=capture_create,
        ):
            await create_note_requests_from_flagged_messages(
                message_ids=message_ids,
                scan_id=scan_id,
                session=mock_session,
                user_id=user_id,
                community_server_id=community_server_id,
                flagged_messages=sample_flagged_messages,
            )

        assert captured_kwargs["request_metadata"]["generate_ai_notes"] is False
