from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.events.publisher import event_publisher
from src.events.scoring_events import ScoringEventPublisher


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_score_update_succeeds_with_mock():
    """Test that publishing succeeds when using the global mock from conftest.py"""
    # The conftest.py mock_external_services fixture mocks NATS, so this should succeed
    await ScoringEventPublisher.publish_note_score_updated(
        note_id=uuid4(),
        score=0.75,
        confidence="standard",
        algorithm="bayesian",
        rating_count=10,
        tier=1,
        tier_name="Basic",
    )
    # No exception = success with mock


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_score_update_with_context():
    """Test publishing with optional message context fields"""
    await ScoringEventPublisher.publish_note_score_updated(
        note_id=uuid4(),
        score=0.5,
        confidence="provisional",
        algorithm="simple",
        rating_count=3,
        tier=1,
        tier_name="Minimal",
        original_message_id="msg123",
        channel_id="ch456",
        community_server_id="guild789",
    )
    # No exception = success with mock


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_calls_event_publisher():
    """Test that ScoringEventPublisher calls the underlying event_publisher"""
    note_id = uuid4()
    with patch.object(
        event_publisher, "publish_note_score_updated", new_callable=AsyncMock
    ) as mock_publish:
        await ScoringEventPublisher.publish_note_score_updated(
            note_id=note_id,
            score=0.75,
            confidence="standard",
            algorithm="bayesian",
            rating_count=10,
            tier=1,
            tier_name="Basic",
            original_message_id="msg123",
            channel_id="ch456",
            community_server_id="guild789",
        )

        # Verify the event_publisher method was called with correct arguments
        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["note_id"] == note_id
        assert call_kwargs["score"] == 0.75
        assert call_kwargs["confidence"] == "standard"
        assert call_kwargs["algorithm"] == "bayesian"
        assert call_kwargs["rating_count"] == 10
        assert call_kwargs["tier"] == 1
        assert call_kwargs["tier_name"] == "Basic"
        assert call_kwargs["original_message_id"] == "msg123"
        assert call_kwargs["channel_id"] == "ch456"
        assert call_kwargs["community_server_id"] == "guild789"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_without_optional_params():
    """Test publishing without optional parameters"""
    note_id = uuid4()
    with patch.object(
        event_publisher, "publish_note_score_updated", new_callable=AsyncMock
    ) as mock_publish:
        await ScoringEventPublisher.publish_note_score_updated(
            note_id=note_id,
            score=0.5,
            confidence="provisional",
            algorithm="simple",
            rating_count=3,
            tier=1,
            tier_name="Minimal",
        )

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["note_id"] == note_id
        assert call_kwargs.get("original_message_id") is None
        assert call_kwargs.get("channel_id") is None
        assert call_kwargs.get("community_server_id") is None
