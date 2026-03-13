from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.notes.score_event_context import build_score_event_routing_context


@pytest.mark.asyncio
async def test_build_score_event_routing_context_prefers_message_archive_channel():
    note = SimpleNamespace(
        channel_id="note-channel",
        community_server_id=uuid4(),
        request=SimpleNamespace(
            message_archive=SimpleNamespace(
                platform_message_id="discord-msg-123",
                platform_channel_id="archive-channel-456",
            )
        ),
    )
    db = AsyncMock()
    platform_id_result = MagicMock()
    platform_id_result.scalar_one_or_none.return_value = "guild-789"
    db.execute.return_value = platform_id_result

    context = await build_score_event_routing_context(db, note)

    assert context.original_message_id == "discord-msg-123"
    assert context.channel_id == "archive-channel-456"
    assert context.community_server_id == "guild-789"


@pytest.mark.asyncio
async def test_build_score_event_routing_context_falls_back_to_note_channel():
    note = SimpleNamespace(
        channel_id="note-channel",
        community_server_id=None,
        request=None,
    )
    db = AsyncMock()

    context = await build_score_event_routing_context(db, note)

    assert context.original_message_id is None
    assert context.channel_id == "note-channel"
    assert context.community_server_id is None
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_score_event_routing_context_returns_none_when_unresolved():
    note = SimpleNamespace(
        channel_id=None,
        community_server_id=None,
        request=SimpleNamespace(message_archive=None),
    )
    db = AsyncMock()

    context = await build_score_event_routing_context(db, note)

    assert context.original_message_id is None
    assert context.channel_id is None
    assert context.community_server_id is None
    db.execute.assert_not_awaited()
