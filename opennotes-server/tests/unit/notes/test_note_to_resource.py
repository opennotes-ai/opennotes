"""Unit tests for note_to_resource serializer."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.notes.notes_jsonapi_router import note_to_resource

pytestmark = pytest.mark.unit


def _make_note(*, message_archive=None, request=None, ratings=None):
    """Build a SimpleNamespace that mimics a Note model for note_to_resource."""
    if request is None and message_archive is not None:
        request = SimpleNamespace(message_archive=message_archive)
    return SimpleNamespace(
        id=uuid4(),
        author_id=uuid4(),
        channel_id="channel-1",
        summary="Test note",
        classification="NOT_MISLEADING",
        helpfulness_score=0,
        status="NEEDS_MORE_RATINGS",
        ai_generated=False,
        ai_provider=None,
        force_published=False,
        force_published_at=None,
        created_at=None,
        updated_at=None,
        request_id=uuid4(),
        ratings=ratings or [],
        community_server_id=uuid4(),
        request=request,
    )


class TestNoteToResourcePlatformChannelId:
    def test_returns_platform_channel_id_when_message_archive_has_it(self):
        archive = SimpleNamespace(
            platform_message_id="msg-123",
            platform_channel_id="chan-456",
        )
        note = _make_note(message_archive=archive)

        resource = note_to_resource(note)

        assert resource.attributes.platform_channel_id == "chan-456"
        assert resource.attributes.platform_message_id == "msg-123"

    def test_returns_none_platform_channel_id_when_no_message_archive(self):
        note = _make_note(request=None)

        resource = note_to_resource(note)

        assert resource.attributes.platform_channel_id is None
        assert resource.attributes.platform_message_id is None

    def test_returns_none_platform_channel_id_when_no_request(self):
        note = _make_note()
        note.request = None

        resource = note_to_resource(note)

        assert resource.attributes.platform_channel_id is None

    def test_returns_none_platform_channel_id_when_archive_missing_field(self):
        archive = SimpleNamespace(
            platform_message_id="msg-789",
            platform_channel_id=None,
        )
        note = _make_note(message_archive=archive)

        resource = note_to_resource(note)

        assert resource.attributes.platform_channel_id is None
        assert resource.attributes.platform_message_id == "msg-789"
