"""
Tests for RequestService - encapsulated MessageArchive + Request creation.

Tests verify that the service properly:
- Creates MessageArchive and Request in single operation
- Handles all optional parameters correctly
- Maintains transactional integrity
- Populates fields correctly
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.notes.message_archive_models import MessageArchive
from src.notes.models import Note, Request
from src.notes.request_service import RequestService


@pytest.fixture
async def community_server(db_session):
    """Create a test community server."""
    server = CommunityServer(
        platform="discord",
        platform_id="test_server_123",
        name="Test Server",
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    return server


@pytest.mark.asyncio
class TestRequestService:
    """Test suite for RequestService.create_from_message()"""

    async def test_create_from_message_minimal(
        self,
        community_server,
    ):
        """Test creating request with only required fields"""
        async_session_maker = get_session_maker()

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_minimal",
                content="Minimal test message",
                community_server_id=community_server.id,
                requested_by="test_user",
            )
            await db.commit()

            # Verify request created with correct fields
            assert request.request_id == "req_test_minimal"
            assert request.community_server_id == community_server.id
            assert request.requested_by == "test_user"
            assert request.status == "PENDING"  # Default value
            assert request.message_archive_id is not None

            # Verify message archive was created
            archive_stmt = select(MessageArchive).where(
                MessageArchive.id == request.message_archive_id
            )
            archive_result = await db.execute(archive_stmt)
            archive = archive_result.scalar_one()
            assert archive.content_text == "Minimal test message"
            assert archive.platform_message_id is None

    async def test_create_from_message_with_discord_metadata(
        self,
        community_server,
    ):
        """Test creating request with full Discord metadata"""
        async_session_maker = get_session_maker()
        timestamp = datetime.now(UTC)

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_discord",
                content="Message with Discord metadata",
                community_server_id=community_server.id,
                requested_by="discord_user",
                platform_message_id="msg_123",
                platform_channel_id="channel_456",
                platform_author_id="author_789",
                platform_timestamp=timestamp,
            )
            await db.commit()

            # Verify message archive has Discord metadata
            archive_stmt = select(MessageArchive).where(
                MessageArchive.id == request.message_archive_id
            )
            archive_result = await db.execute(archive_stmt)
            archive = archive_result.scalar_one()
            assert archive.platform_message_id == "msg_123"
            assert archive.platform_channel_id == "channel_456"
            assert archive.platform_author_id == "author_789"
            assert archive.platform_timestamp == timestamp

    async def test_create_from_message_with_dataset_metadata(
        self,
        community_server,
    ):
        """Test creating request with fact-check dataset metadata"""
        async_session_maker = get_session_maker()
        dataset_item_id = str(uuid4())

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_dataset",
                content="Message with dataset metadata",
                community_server_id=community_server.id,
                requested_by="test_user",
                dataset_item_id=dataset_item_id,
                similarity_score=0.85,
                dataset_name="snopes",
            )
            await db.commit()

            # Verify request has dataset metadata
            assert request.dataset_item_id == dataset_item_id
            assert request.similarity_score == 0.85
            assert request.dataset_name == "snopes"

    async def test_create_from_message_with_priority_and_reason(
        self,
        community_server,
    ):
        """Test creating request with priority and reason"""
        async_session_maker = get_session_maker()

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_priority",
                content="High priority request",
                community_server_id=community_server.id,
                requested_by="test_user",
                priority="high",
                reason="Urgent fact-check needed",
            )
            await db.commit()

            # Verify request has priority and reason
            assert request.priority == "high"
            assert request.reason == "Urgent fact-check needed"

    async def test_create_from_message_with_custom_status(
        self,
        community_server,
    ):
        """Test creating request with custom status"""
        async_session_maker = get_session_maker()

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_status",
                content="In progress request",
                community_server_id=community_server.id,
                requested_by="test_user",
                status="IN_PROGRESS",
            )
            await db.commit()

            # Verify request has custom status
            assert request.status == "IN_PROGRESS"

    async def test_create_from_message_with_metadata(
        self,
        community_server,
    ):
        """Test creating request with additional metadata"""
        async_session_maker = get_session_maker()
        metadata = {"source": "api", "version": "1.0"}

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_metadata",
                content="Request with metadata",
                community_server_id=community_server.id,
                requested_by="test_user",
                request_metadata=metadata,
            )
            await db.commit()

            # Verify request has metadata
            assert request.request_metadata == metadata

    async def test_create_from_message_with_note_id(
        self,
        community_server,
    ):
        """Test creating request linked to existing note"""
        async_session_maker = get_session_maker()
        test_note_id = uuid4()

        async with async_session_maker() as db:
            # Create a note first (must exist for FK constraint)
            note = Note(
                id=test_note_id,
                author_participant_id="test_author",
                summary="Test note",
                classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
                status="NEEDS_MORE_RATINGS",
                community_server_id=community_server.id,
            )
            db.add(note)
            await db.flush()

            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_note",
                content="Request with note",
                community_server_id=community_server.id,
                requested_by="test_user",
                note_id=test_note_id,
            )
            await db.commit()

            # Verify request has note_id
            assert request.note_id == test_note_id

    async def test_create_from_message_all_fields(
        self,
        community_server,
    ):
        """Test creating request with all possible fields populated"""
        async_session_maker = get_session_maker()
        timestamp = datetime.now(UTC)
        dataset_item_id = str(uuid4())
        test_note_id = uuid4()
        metadata = {"test": "data"}

        async with async_session_maker() as db:
            # Create a note first (must exist for FK constraint)
            note = Note(
                id=test_note_id,
                author_participant_id="test_author",
                summary="Test note for all fields",
                classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
                status="NEEDS_MORE_RATINGS",
                community_server_id=community_server.id,
            )
            db.add(note)
            await db.flush()

            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_all_fields",
                content="Complete request with all fields",
                community_server_id=community_server.id,
                requested_by="test_user",
                platform_message_id="msg_all",
                platform_channel_id="channel_all",
                platform_author_id="author_all",
                platform_timestamp=timestamp,
                dataset_item_id=dataset_item_id,
                similarity_score=0.95,
                dataset_name="politifact",
                status="COMPLETED",
                priority="high",
                reason="Full test",
                note_id=test_note_id,
                request_metadata=metadata,
            )
            await db.commit()

            # Verify all request fields
            assert request.request_id == "req_test_all_fields"
            assert request.community_server_id == community_server.id
            assert request.requested_by == "test_user"
            assert request.status == "COMPLETED"
            assert request.dataset_item_id == dataset_item_id
            assert request.similarity_score == 0.95
            assert request.dataset_name == "politifact"
            assert request.priority == "high"
            assert request.reason == "Full test"
            assert request.note_id == test_note_id
            assert request.request_metadata == metadata

            # Verify message archive has Discord metadata
            archive_stmt = select(MessageArchive).where(
                MessageArchive.id == request.message_archive_id
            )
            archive_result = await db.execute(archive_stmt)
            archive = archive_result.scalar_one()
            assert archive.content_text == "Complete request with all fields"
            assert archive.platform_message_id == "msg_all"
            assert archive.platform_channel_id == "channel_all"
            assert archive.platform_author_id == "author_all"
            assert archive.platform_timestamp == timestamp

    async def test_create_from_message_transactional_integrity(
        self,
        community_server,
    ):
        """Test that rollback removes both request and message archive"""
        async_session_maker = get_session_maker()

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_rollback",
                content="This will be rolled back",
                community_server_id=community_server.id,
                requested_by="test_user",
            )
            message_archive_id = request.message_archive_id

            # Rollback instead of commit
            await db.rollback()

        # Verify neither request nor message archive exist
        async with async_session_maker() as db:
            request_stmt = select(Request).where(Request.request_id == "req_test_rollback")
            request_result = await db.execute(request_stmt)
            assert request_result.scalar_one_or_none() is None

            archive_stmt = select(MessageArchive).where(MessageArchive.id == message_archive_id)
            archive_result = await db.execute(archive_stmt)
            assert archive_result.scalar_one_or_none() is None

    async def test_create_from_message_long_content(
        self,
        community_server,
    ):
        """Test creating request with very long content"""
        async_session_maker = get_session_maker()
        long_content = "A" * 10000  # 10k characters

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_long",
                content=long_content,
                community_server_id=community_server.id,
                requested_by="test_user",
            )
            await db.commit()

            # Verify content stored correctly
            archive_stmt = select(MessageArchive).where(
                MessageArchive.id == request.message_archive_id
            )
            archive_result = await db.execute(archive_stmt)
            archive = archive_result.scalar_one()
            assert len(archive.content_text) == 10000
            assert archive.content_text == long_content

    async def test_create_from_message_special_characters(
        self,
        community_server,
    ):
        """Test creating request with special characters in content"""
        async_session_maker = get_session_maker()
        special_content = "Test with émojis 🔥 and symbols: @#$%^&*() 日本語"

        async with async_session_maker() as db:
            request = await RequestService.create_from_message(
                db=db,
                request_id="req_test_special",
                content=special_content,
                community_server_id=community_server.id,
                requested_by="test_user",
            )
            await db.commit()

            # Verify special characters preserved
            archive_stmt = select(MessageArchive).where(
                MessageArchive.id == request.message_archive_id
            )
            archive_result = await db.execute(archive_stmt)
            archive = archive_result.scalar_one()
            assert archive.content_text == special_content
