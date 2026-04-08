"""Tests for BulkScanMessage -> ContentItem adapter function.

Covers bulk_scan_message_to_content_item in schemas.py and the
NATS handler's _handle_message_batch Redis storage change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_bulk_scan_message(
    message_id: str = "msg_001",
    channel_id: str = "ch_123",
    community_server_id: str = "server_abc",
    content: str = "Test message content",
    author_id: str = "author_42",
    author_username: str | None = "tester",
    embed_content: str | None = None,
    attachment_urls: list[str] | None = None,
):
    from src.bulk_content_scan.schemas import BulkScanMessage

    return BulkScanMessage(
        message_id=message_id,
        channel_id=channel_id,
        community_server_id=community_server_id,
        content=content,
        author_id=author_id,
        author_username=author_username,
        timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
        embed_content=embed_content,
        attachment_urls=attachment_urls,
    )


class TestBulkScanMessageToContentItem:
    """Tests for bulk_scan_message_to_content_item adapter."""

    def test_adapter_function_exists(self):
        """The adapter function must exist in schemas module."""
        from src.bulk_content_scan import schemas

        assert hasattr(schemas, "bulk_scan_message_to_content_item")

    def test_maps_content_id_from_message_id(self):
        """content_id must be set from message_id."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(message_id="msg_999")
        item = bulk_scan_message_to_content_item(msg)

        assert item.content_id == "msg_999"

    def test_platform_is_discord(self):
        """platform field must be set to 'discord'."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message()
        item = bulk_scan_message_to_content_item(msg)

        assert item.platform == "discord"

    def test_maps_content_text_from_content(self):
        """content_text must be set from content."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(content="Hello, world!")
        item = bulk_scan_message_to_content_item(msg)

        assert item.content_text == "Hello, world!"

    def test_preserves_author_id(self):
        """author_id must be preserved."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(author_id="author_123")
        item = bulk_scan_message_to_content_item(msg)

        assert item.author_id == "author_123"

    def test_preserves_author_username(self):
        """author_username must be preserved."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(author_username="discorduser")
        item = bulk_scan_message_to_content_item(msg)

        assert item.author_username == "discorduser"

    def test_preserves_timestamp(self):
        """timestamp must be preserved."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message()
        item = bulk_scan_message_to_content_item(msg)

        assert item.timestamp == datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_preserves_channel_id(self):
        """channel_id must be preserved."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(channel_id="ch_discord_999")
        item = bulk_scan_message_to_content_item(msg)

        assert item.channel_id == "ch_discord_999"

    def test_preserves_community_server_id(self):
        """community_server_id must be preserved."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(community_server_id="server_xyz")
        item = bulk_scan_message_to_content_item(msg)

        assert item.community_server_id == "server_xyz"

    def test_preserves_attachment_urls(self):
        """attachment_urls must be preserved."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        urls = ["https://cdn.discord.com/a.png", "https://cdn.discord.com/b.jpg"]
        msg = _make_bulk_scan_message(attachment_urls=urls)
        item = bulk_scan_message_to_content_item(msg)

        assert item.attachment_urls == urls

    def test_embed_content_stored_in_platform_metadata(self):
        """embed_content must be stored in platform_metadata dict."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(embed_content="Some embed text")
        item = bulk_scan_message_to_content_item(msg)

        assert "embed_content" in item.platform_metadata
        assert item.platform_metadata["embed_content"] == "Some embed text"

    def test_none_embed_content_stored_in_platform_metadata(self):
        """None embed_content must still be in platform_metadata with None value."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(embed_content=None)
        item = bulk_scan_message_to_content_item(msg)

        assert "embed_content" in item.platform_metadata
        assert item.platform_metadata["embed_content"] is None

    def test_returns_content_item_instance(self):
        """Return type must be ContentItem."""
        from src.bulk_content_scan.schemas import ContentItem, bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message()
        item = bulk_scan_message_to_content_item(msg)

        assert isinstance(item, ContentItem)

    def test_none_author_username_preserved(self):
        """None author_username must be preserved as None."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(author_username=None)
        item = bulk_scan_message_to_content_item(msg)

        assert item.author_username is None

    def test_none_attachment_urls_preserved(self):
        """None attachment_urls must be preserved as None."""
        from src.bulk_content_scan.schemas import bulk_scan_message_to_content_item

        msg = _make_bulk_scan_message(attachment_urls=None)
        item = bulk_scan_message_to_content_item(msg)

        assert item.attachment_urls is None


class TestNatsHandlerStoresContentItem:
    """Tests that _handle_message_batch stores ContentItem dicts in Redis."""

    def _make_handler(self):
        from src.bulk_content_scan.nats_handler import BulkScanEventHandler

        return BulkScanEventHandler(
            embedding_service=MagicMock(),
            redis_client=MagicMock(),
            nats_client=AsyncMock(),
            llm_service=MagicMock(),
        )

    def _make_event(self, message_count: int = 2):
        from uuid import uuid4

        from src.bulk_content_scan.schemas import BulkScanMessage
        from src.events.schemas import BulkScanMessageBatchEvent

        messages = [
            BulkScanMessage(
                message_id=f"msg_{i}",
                channel_id="ch_1",
                community_server_id="platform_123",
                content=f"test message {i}",
                author_id=f"author_{i}",
                author_username=f"user_{i}",
                timestamp="2025-01-01T00:00:00Z",
                embed_content=f"embed_{i}" if i % 2 == 0 else None,
            )
            for i in range(message_count)
        ]

        return BulkScanMessageBatchEvent(
            event_id="evt_test",
            scan_id=uuid4(),
            community_server_id=uuid4(),
            batch_number=1,
            messages=messages,
        )

    @pytest.mark.asyncio
    async def test_handler_stores_content_item_dicts_in_redis(self):
        """_handle_message_batch must store ContentItem dicts (with content_id) in Redis."""
        handler = self._make_handler()
        event = self._make_event(message_count=2)

        stored_data: list[list] = []

        async def capture_store(redis_client, key, messages_data):
            stored_data.append(messages_data)

        with (
            patch(
                "src.bulk_content_scan.nats_handler.enqueue_content_scan_batch",
                new_callable=AsyncMock,
                return_value="wf-123",
            ),
            patch.object(
                handler,
                "_get_scan_types_for_community",
                new_callable=AsyncMock,
                return_value=["similarity"],
            ),
            patch(
                "src.bulk_content_scan.nats_handler.store_messages_in_redis",
                new_callable=AsyncMock,
                side_effect=capture_store,
            ),
            patch(
                "src.bulk_content_scan.nats_handler.get_batch_redis_key",
                return_value="test:key",
            ),
        ):
            await handler._handle_message_batch(event)

        assert len(stored_data) == 1
        messages_data = stored_data[0]
        assert len(messages_data) == 2

        for item_dict in messages_data:
            assert "content_id" in item_dict, "Should have ContentItem field content_id"
            assert "platform" in item_dict, "Should have ContentItem field platform"
            assert item_dict["platform"] == "discord"
            assert "content_text" in item_dict, "Should have ContentItem field content_text"
            assert "message_id" not in item_dict, "Should NOT have BulkScanMessage field message_id"

    @pytest.mark.asyncio
    async def test_handler_stores_embed_content_in_platform_metadata(self):
        """embed_content must be preserved in platform_metadata of stored ContentItem dicts."""
        handler = self._make_handler()
        event = self._make_event(message_count=2)

        stored_data: list[list] = []

        async def capture_store(redis_client, key, messages_data):
            stored_data.append(messages_data)

        with (
            patch(
                "src.bulk_content_scan.nats_handler.enqueue_content_scan_batch",
                new_callable=AsyncMock,
                return_value="wf-123",
            ),
            patch.object(
                handler,
                "_get_scan_types_for_community",
                new_callable=AsyncMock,
                return_value=["similarity"],
            ),
            patch(
                "src.bulk_content_scan.nats_handler.store_messages_in_redis",
                new_callable=AsyncMock,
                side_effect=capture_store,
            ),
            patch(
                "src.bulk_content_scan.nats_handler.get_batch_redis_key",
                return_value="test:key",
            ),
        ):
            await handler._handle_message_batch(event)

        messages_data = stored_data[0]
        for item_dict in messages_data:
            assert "platform_metadata" in item_dict
            assert "embed_content" in item_dict["platform_metadata"]

    @pytest.mark.asyncio
    async def test_handler_correct_message_count_stored(self):
        """The number of ContentItem dicts stored must match the input message count."""
        handler = self._make_handler()
        event = self._make_event(message_count=5)

        stored_data: list[list] = []

        async def capture_store(redis_client, key, messages_data):
            stored_data.append(messages_data)

        with (
            patch(
                "src.bulk_content_scan.nats_handler.enqueue_content_scan_batch",
                new_callable=AsyncMock,
                return_value="wf-123",
            ),
            patch.object(
                handler,
                "_get_scan_types_for_community",
                new_callable=AsyncMock,
                return_value=["similarity"],
            ),
            patch(
                "src.bulk_content_scan.nats_handler.store_messages_in_redis",
                new_callable=AsyncMock,
                side_effect=capture_store,
            ),
            patch(
                "src.bulk_content_scan.nats_handler.get_batch_redis_key",
                return_value="test:key",
            ),
        ):
            await handler._handle_message_batch(event)

        assert len(stored_data[0]) == 5
