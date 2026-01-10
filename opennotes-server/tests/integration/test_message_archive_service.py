from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy import select

from src.database import get_session_maker
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.notes.message_archive_models import ContentType, MessageArchive
from src.notes.message_archive_schemas import MessageArchiveCreate
from src.notes.message_archive_service import MessageArchiveService


class TestMessageArchiveService:
    @pytest.mark.asyncio
    async def test_create_from_schema(self):
        async with get_session_maker()() as db:
            data = MessageArchiveCreate(
                content_type=ContentType.TEXT,
                content_text="Test message content",
                platform_message_id="123456789",
                platform_channel_id="987654321",
                platform_author_id="111222333",
                platform_timestamp=datetime.now(UTC),
            )

            archive = await MessageArchiveService.create(db, data)
            await db.commit()

            assert archive.id is not None
            assert isinstance(archive.id, UUID)
            assert archive.content_type == ContentType.TEXT
            assert archive.content_text == "Test message content"
            assert archive.platform_message_id == "123456789"
            assert archive.platform_channel_id == "987654321"
            assert archive.platform_author_id == "111222333"
            assert archive.created_at is not None
            assert archive.deleted_at is None

    @pytest.mark.asyncio
    async def test_create_from_text(self):
        async with get_session_maker()() as db:
            archive = await MessageArchiveService.create_from_text(
                db=db,
                content="Simple text message",
                platform_message_id="msg_12345",
            )
            await db.commit()

            assert archive.id is not None
            assert archive.content_type == ContentType.TEXT
            assert archive.content_text == "Simple text message"
            assert archive.platform_message_id == "msg_12345"
            assert archive.platform_channel_id is None
            assert archive.platform_author_id is None

    @pytest.mark.asyncio
    async def test_create_from_text_with_discord_metadata(self):
        async with get_session_maker()() as db:
            timestamp = datetime.now(UTC)
            archive = await MessageArchiveService.create_from_text(
                db=db,
                content="Message with full Discord metadata",
                platform_message_id="msg_discord_1",
                platform_channel_id="channel_123",
                platform_author_id="author_456",
                platform_timestamp=timestamp,
            )
            await db.commit()

            assert archive.content_text == "Message with full Discord metadata"
            assert archive.platform_message_id == "msg_discord_1"
            assert archive.platform_channel_id == "channel_123"
            assert archive.platform_author_id == "author_456"
            assert archive.platform_timestamp == timestamp

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        async with get_session_maker()() as db:
            archive = await MessageArchiveService.create_from_text(
                db=db,
                content="Test get by ID",
            )
            await db.commit()
            archive_id = archive.id

        async with get_session_maker()() as db:
            retrieved = await MessageArchiveService.get_by_id(db, archive_id)

            assert retrieved is not None
            assert retrieved.id == archive_id
            assert retrieved.content_text == "Test get by ID"

    @pytest.mark.asyncio
    async def test_get_by_id_nonexistent(self):
        async with get_session_maker()() as db:
            fake_uuid = UUID("00000000-0000-0000-0000-000000000000")
            retrieved = await MessageArchiveService.get_by_id(db, fake_uuid)

            assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_by_platform_message_id(self):
        async with get_session_maker()() as db:
            await MessageArchiveService.create_from_text(
                db=db,
                content="First message",
                platform_message_id="discord_msg_unique_123",
            )
            await db.commit()

        async with get_session_maker()() as db:
            retrieved = await MessageArchiveService.get_by_platform_message_id(
                db, "discord_msg_unique_123"
            )

            assert retrieved is not None
            assert retrieved.platform_message_id == "discord_msg_unique_123"
            assert retrieved.content_text == "First message"

    @pytest.mark.asyncio
    async def test_get_by_platform_message_id_not_found(self):
        async with get_session_maker()() as db:
            retrieved = await MessageArchiveService.get_by_platform_message_id(
                db, "nonexistent_message_id"
            )

            assert retrieved is None

    @pytest.mark.asyncio
    async def test_soft_delete(self):
        async with get_session_maker()() as db:
            archive = await MessageArchiveService.create_from_text(
                db=db,
                content="To be deleted",
            )
            await db.commit()
            archive_id = archive.id

        async with get_session_maker()() as db:
            result = await MessageArchiveService.soft_delete(db, archive_id)
            await db.commit()

            assert result is True

        async with get_session_maker()() as db:
            stmt = select(MessageArchive).where(MessageArchive.id == archive_id)
            result = await db.execute(stmt)
            deleted_archive = result.scalar_one_or_none()

            assert deleted_archive is not None
            assert deleted_archive.deleted_at is not None

    @pytest.mark.asyncio
    async def test_soft_delete_nonexistent(self):
        async with get_session_maker()() as db:
            fake_uuid = UUID("00000000-0000-0000-0000-000000000000")
            result = await MessageArchiveService.soft_delete(db, fake_uuid)

            assert result is False

    @pytest.mark.asyncio
    async def test_get_by_id_excludes_soft_deleted(self):
        async with get_session_maker()() as db:
            archive = await MessageArchiveService.create_from_text(
                db=db,
                content="Will be soft deleted",
            )
            await db.commit()
            archive_id = archive.id

        async with get_session_maker()() as db:
            await MessageArchiveService.soft_delete(db, archive_id)
            await db.commit()

        async with get_session_maker()() as db:
            retrieved = await MessageArchiveService.get_by_id(db, archive_id)

            assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_by_platform_message_id_excludes_soft_deleted(self):
        async with get_session_maker()() as db:
            archive = await MessageArchiveService.create_from_text(
                db=db,
                content="Discord message to be deleted",
                platform_message_id="discord_delete_123",
            )
            await db.commit()
            archive_id = archive.id

        async with get_session_maker()() as db:
            await MessageArchiveService.soft_delete(db, archive_id)
            await db.commit()

        async with get_session_maker()() as db:
            retrieved = await MessageArchiveService.get_by_platform_message_id(
                db, "discord_delete_123"
            )

            assert retrieved is None

    @pytest.mark.asyncio
    async def test_create_image_archive(self):
        async with get_session_maker()() as db:
            data = MessageArchiveCreate(
                content_type=ContentType.IMAGE,
                content_url="https://example.com/image.png",
                platform_message_id="img_msg_123",
            )

            archive = await MessageArchiveService.create(db, data)
            await db.commit()

            assert archive.content_type == ContentType.IMAGE
            assert archive.content_url == "https://example.com/image.png"
            assert archive.content_text is None

    @pytest.mark.asyncio
    async def test_create_video_archive(self):
        async with get_session_maker()() as db:
            data = MessageArchiveCreate(
                content_type=ContentType.VIDEO,
                content_url="https://example.com/video.mp4",
                message_metadata={"duration": 120, "format": "mp4"},
            )

            archive = await MessageArchiveService.create(db, data)
            await db.commit()

            assert archive.content_type == ContentType.VIDEO
            assert archive.content_url == "https://example.com/video.mp4"
            assert archive.message_metadata["duration"] == 120

    @pytest.mark.asyncio
    async def test_create_file_archive(self):
        async with get_session_maker()() as db:
            data = MessageArchiveCreate(
                content_type=ContentType.FILE,
                file_reference="s3://bucket/file.pdf",
                message_metadata={"filename": "document.pdf", "size": 1024000},
            )

            archive = await MessageArchiveService.create(db, data)
            await db.commit()

            assert archive.content_type == ContentType.FILE
            assert archive.file_reference == "s3://bucket/file.pdf"
            assert archive.message_metadata["filename"] == "document.pdf"

    @pytest.mark.asyncio
    async def test_get_content_method(self):
        async with get_session_maker()() as db:
            text_archive = await MessageArchiveService.create_from_text(
                db=db,
                content="Text content for get_content test",
            )
            await db.commit()

            content = text_archive.get_content()
            assert content == "Text content for get_content test"

    @pytest.mark.asyncio
    async def test_get_content_returns_url_for_image(self):
        async with get_session_maker()() as db:
            data = MessageArchiveCreate(
                content_type=ContentType.IMAGE,
                content_url="https://example.com/image.png",
            )
            archive = await MessageArchiveService.create(db, data)
            await db.commit()

            content = archive.get_content()
            assert content == "https://example.com/image.png"

    @pytest.mark.asyncio
    async def test_multiple_archives_different_discord_ids(self):
        async with get_session_maker()() as db:
            archive1 = await MessageArchiveService.create_from_text(
                db=db,
                content="First message",
                platform_message_id="msg_1",
            )
            archive2 = await MessageArchiveService.create_from_text(
                db=db,
                content="Second message",
                platform_message_id="msg_2",
            )
            await db.commit()

            assert archive1.id != archive2.id
            assert archive1.platform_message_id != archive2.platform_message_id

        async with get_session_maker()() as db:
            retrieved1 = await MessageArchiveService.get_by_platform_message_id(db, "msg_1")
            retrieved2 = await MessageArchiveService.get_by_platform_message_id(db, "msg_2")

            assert retrieved1.content_text == "First message"
            assert retrieved2.content_text == "Second message"

    @pytest.mark.asyncio
    async def test_long_content(self):
        async with get_session_maker()() as db:
            long_content = "A" * 20000
            archive = await MessageArchiveService.create_from_text(
                db=db,
                content=long_content,
            )
            await db.commit()

            assert len(archive.content_text) == 20000
            assert archive.content_text == long_content

        async with get_session_maker()() as db:
            retrieved = await MessageArchiveService.get_by_id(db, archive.id)
            assert len(retrieved.content_text) == 20000

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self):
        async with get_session_maker()() as db:
            special_content = "Test with émojis 🎉 and spëcial çhars: <>&\"'"
            archive = await MessageArchiveService.create_from_text(
                db=db,
                content=special_content,
            )
            await db.commit()

            assert archive.content_text == special_content

        async with get_session_maker()() as db:
            retrieved = await MessageArchiveService.get_by_id(db, archive.id)
            assert retrieved.content_text == special_content

    @pytest.mark.asyncio
    async def test_create_from_image_with_vision_description(self):
        """Test creating image archive with vision description."""
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id="test-guild-456",
                name="Test Community",
            )
            db.add(community_server)
            await db.flush()

            llm_config = CommunityServerLLMConfig(
                community_server_id=community_server.id,
                provider="openai",
                enabled=True,
                api_key_encrypted=b"encrypted_key",
                encryption_key_id="test_key_id",
                api_key_preview="...4o",
            )
            db.add(llm_config)
            await db.flush()

            mock_vision_service = MagicMock()
            mock_vision_service.describe_image = AsyncMock(
                return_value="A detailed description of the image showing a cat on a table"
            )

            archive = await MessageArchiveService.create_from_image(
                db=db,
                image_url="https://example.com/test-image.jpg",
                community_server_id=community_server.platform_community_server_id,
                vision_service=mock_vision_service,
                platform_message_id="img_msg_vision_1",
            )
            await db.commit()

            assert archive.content_type == ContentType.IMAGE
            assert archive.content_url == "https://example.com/test-image.jpg"
            assert (
                archive.image_description
                == "A detailed description of the image showing a cat on a table"
            )
            assert archive.platform_message_id == "img_msg_vision_1"

            mock_vision_service.describe_image.assert_called_once()
            call_args = mock_vision_service.describe_image.call_args
            assert call_args.kwargs["image_url"] == "https://example.com/test-image.jpg"
            assert (
                call_args.kwargs["community_server_id"]
                == community_server.platform_community_server_id
            )

    @pytest.mark.asyncio
    async def test_create_from_image_with_custom_vision_params(self):
        """Test creating image archive with custom vision parameters."""
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id="test-guild-789",
                name="Test Community",
            )
            db.add(community_server)
            await db.flush()

            llm_config = CommunityServerLLMConfig(
                community_server_id=community_server.id,
                provider="openai",
                enabled=True,
                api_key_encrypted=b"encrypted_key",
                encryption_key_id="test_key_id",
                api_key_preview="...4o",
            )
            db.add(llm_config)
            await db.flush()

            mock_vision_service = MagicMock()
            mock_vision_service.describe_image = AsyncMock(return_value="High detail description")

            archive = await MessageArchiveService.create_from_image(
                db=db,
                image_url="https://example.com/detailed-image.jpg",
                community_server_id=community_server.platform_community_server_id,
                vision_service=mock_vision_service,
                detail="high",
                max_tokens=500,
            )
            await db.commit()

            assert archive.image_description == "High detail description"

            call_args = mock_vision_service.describe_image.call_args
            assert call_args.kwargs["detail"] == "high"
            assert call_args.kwargs["max_tokens"] == 500

    @pytest.mark.asyncio
    async def test_create_from_image_vision_service_error(self):
        """Test creating image archive when vision service fails."""
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id="test-guild-error",
                name="Test Community",
            )
            db.add(community_server)
            await db.flush()

            llm_config = CommunityServerLLMConfig(
                community_server_id=community_server.id,
                provider="openai",
                enabled=True,
                api_key_encrypted=b"encrypted_key",
                encryption_key_id="test_key_id",
                api_key_preview="...4o",
            )
            db.add(llm_config)
            await db.flush()

            mock_vision_service = MagicMock()
            mock_vision_service.describe_image = AsyncMock(
                side_effect=Exception("Vision API failed")
            )

            archive = await MessageArchiveService.create_from_image(
                db=db,
                image_url="https://example.com/error-image.jpg",
                community_server_id=community_server.platform_community_server_id,
                vision_service=mock_vision_service,
                platform_message_id="img_msg_error",
            )
            await db.commit()

            assert archive.content_type == ContentType.IMAGE
            assert archive.content_url == "https://example.com/error-image.jpg"
            assert archive.image_description is None
            assert archive.platform_message_id == "img_msg_error"

    @pytest.mark.asyncio
    async def test_create_from_image_with_full_discord_metadata(self):
        """Test creating image archive with full Discord metadata and vision."""
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id="test-guild-metadata",
                name="Test Community",
            )
            db.add(community_server)
            await db.flush()

            llm_config = CommunityServerLLMConfig(
                community_server_id=community_server.id,
                provider="openai",
                enabled=True,
                api_key_encrypted=b"encrypted_key",
                encryption_key_id="test_key_id",
                api_key_preview="...4o",
            )
            db.add(llm_config)
            await db.flush()

            mock_vision_service = MagicMock()
            mock_vision_service.describe_image = AsyncMock(return_value="Image description")

            timestamp = datetime.now(UTC)
            archive = await MessageArchiveService.create_from_image(
                db=db,
                image_url="https://example.com/full-metadata.jpg",
                community_server_id=community_server.platform_community_server_id,
                vision_service=mock_vision_service,
                platform_message_id="img_msg_full",
                platform_channel_id="channel_999",
                platform_author_id="author_888",
                platform_timestamp=timestamp,
            )
            await db.commit()

            assert archive.platform_message_id == "img_msg_full"
            assert archive.platform_channel_id == "channel_999"
            assert archive.platform_author_id == "author_888"
            assert archive.platform_timestamp == timestamp
            assert archive.image_description == "Image description"
