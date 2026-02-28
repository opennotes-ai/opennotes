"""Tests for NATS score event routing fields (task-1134).

Verifies that score events published from the ratings path include
community_server_id and channel_id so downstream consumers (Discord bot)
can route or ignore events from playground community servers.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.events.schemas import NoteScoreUpdatedEvent


class TestScoreEventContainsCommunityServerId:
    """Verify NoteScoreUpdatedEvent accepts community_server_id and channel_id."""

    def test_event_accepts_community_server_id(self):
        event = NoteScoreUpdatedEvent(
            event_id="evt-1",
            note_id=uuid4(),
            score=0.75,
            confidence="standard",
            algorithm="BayesianAverage",
            rating_count=5,
            tier=1,
            tier_name="Minimal",
            community_server_id="1234567890123456789",
            channel_id="987654321098765432",
            original_message_id="111222333444555666",
        )
        assert event.community_server_id == "1234567890123456789"
        assert event.channel_id == "987654321098765432"

    def test_event_accepts_none_community_server_id(self):
        event = NoteScoreUpdatedEvent(
            event_id="evt-2",
            note_id=uuid4(),
            score=0.5,
            confidence="provisional",
            algorithm="BayesianAverage",
            rating_count=3,
            tier=1,
            tier_name="Minimal",
        )
        assert event.community_server_id is None
        assert event.channel_id is None


class TestScoringEventPublisherPassesFields:
    """Verify ScoringEventPublisher.publish_note_score_updated passes all fields."""

    @pytest.mark.asyncio
    async def test_publish_passes_community_server_id_and_channel_id(self):
        with patch("src.events.scoring_events.event_publisher") as mock_pub:
            mock_pub.publish_note_score_updated = AsyncMock()

            from src.events.scoring_events import ScoringEventPublisher

            note_id = uuid4()
            await ScoringEventPublisher.publish_note_score_updated(
                note_id=note_id,
                score=0.8,
                confidence="standard",
                algorithm="BayesianAverage",
                rating_count=10,
                tier=1,
                tier_name="Minimal",
                original_message_id="msg-123",
                channel_id="ch-456",
                community_server_id="guild-789",
            )

            mock_pub.publish_note_score_updated.assert_called_once_with(
                note_id=note_id,
                score=0.8,
                confidence="standard",
                algorithm="BayesianAverage",
                rating_count=10,
                tier=1,
                tier_name="Minimal",
                original_message_id="msg-123",
                channel_id="ch-456",
                community_server_id="guild-789",
            )

    @pytest.mark.asyncio
    async def test_publish_passes_none_when_not_provided(self):
        with patch("src.events.scoring_events.event_publisher") as mock_pub:
            mock_pub.publish_note_score_updated = AsyncMock()

            from src.events.scoring_events import ScoringEventPublisher

            note_id = uuid4()
            await ScoringEventPublisher.publish_note_score_updated(
                note_id=note_id,
                score=0.5,
                confidence="provisional",
                algorithm="BayesianAverage",
                rating_count=3,
                tier=1,
                tier_name="Minimal",
            )

            mock_pub.publish_note_score_updated.assert_called_once_with(
                note_id=note_id,
                score=0.5,
                confidence="provisional",
                algorithm="BayesianAverage",
                rating_count=3,
                tier=1,
                tier_name="Minimal",
                original_message_id=None,
                channel_id=None,
                community_server_id=None,
            )
