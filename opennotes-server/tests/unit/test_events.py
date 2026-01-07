import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from nats.errors import Error as NATSError
from nats.js.api import PubAck
from pydantic import ValidationError

from src.events.nats_client import nats_client
from src.events.publisher import event_publisher
from src.events.schemas import EventType, NoteCreatedEvent, NoteScoreUpdatedEvent
from src.events.scoring_events import ScoringEventPublisher
from src.events.subscriber import event_subscriber


@pytest.fixture(autouse=True)
async def clear_event_handlers():
    """Clear event handlers and subscriptions before each test to prevent accumulation."""
    # Clear all handlers and subscriptions
    for event_type in EventType:
        event_subscriber.handlers[event_type] = []
    event_subscriber.subscriptions = []
    yield
    # Clear again after test
    for event_type in EventType:
        event_subscriber.handlers[event_type] = []
    event_subscriber.subscriptions = []


@pytest.fixture
async def setup_nats():
    # Mock NATS client methods with proper PubAck return value
    mock_ack = PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch.object(nats_client, "connect", new_callable=AsyncMock) as mock_connect,
        patch.object(nats_client, "disconnect", new_callable=AsyncMock) as mock_disconnect,
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "ping", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock, return_value=mock_ack),
        patch.object(nats_client, "subscribe", new_callable=AsyncMock),
    ):
        mock_connect.return_value = None
        mock_disconnect.return_value = None
        yield


@pytest.mark.asyncio
async def test_nats_connection(setup_nats):
    assert await nats_client.is_connected() is True
    assert await nats_client.ping() is True


@pytest.mark.asyncio
async def test_publish_note_created(setup_nats):
    event_id = await event_publisher.publish_note_created(
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note summary",
        classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
    )
    assert event_id is not None
    assert len(event_id) > 0


@pytest.mark.asyncio
async def test_publish_user_registered(setup_nats):
    event_id = await event_publisher.publish_user_registered(
        user_id=uuid4(),
        username="testuser",
        email="test@example.com",
        registration_source="discord",
    )
    assert event_id is not None


@pytest.mark.asyncio
async def test_event_subscription():
    received_events = []

    async def test_handler(event: NoteCreatedEvent) -> None:
        received_events.append(event)

    # Create a mock that simulates message delivery
    subscription_handler = None

    async def mock_subscribe(subject: str, queue: str = "", callback=None, **kwargs) -> None:
        nonlocal subscription_handler
        subscription_handler = callback

    async def mock_publish(subject: str, message: str, **kwargs) -> PubAck:
        # Simulate message delivery to subscriber
        if subscription_handler:
            # Create a mock message object with async methods
            mock_msg = MagicMock()
            mock_msg.data = message.encode() if isinstance(message, str) else message
            mock_msg.ack = AsyncMock()
            mock_msg.nak = AsyncMock()
            await subscription_handler(mock_msg)
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "ping", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock, side_effect=mock_publish),
        patch.object(nats_client, "subscribe", new_callable=AsyncMock, side_effect=mock_subscribe),
    ):
        event_subscriber.register_handler(EventType.NOTE_CREATED, test_handler)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        test_note_id = uuid4()
        await event_publisher.publish_note_created(
            note_id=test_note_id,
            author_id="test_author",
            platform_message_id="888",
            summary="Test subscription",
            classification="NOT_MISLEADING",
        )

        await asyncio.sleep(0.1)  # Shorter sleep for test

        assert len(received_events) == 1
        assert received_events[0].note_id == test_note_id
        assert received_events[0].author_id == "test_author"


@pytest.mark.asyncio
async def test_event_schema_validation():
    test_note_id = uuid4()
    event = NoteCreatedEvent(
        event_id="test_123",
        note_id=test_note_id,
        author_id="author_1",
        platform_message_id="100",
        summary="Test",
        classification="NOT_MISLEADING",
    )

    assert event.event_type == EventType.NOTE_CREATED
    assert event.note_id == test_note_id


@pytest.mark.asyncio
async def test_multiple_event_types(setup_nats):
    note_event_id = await event_publisher.publish_note_created(
        note_id=uuid4(),
        author_id="author_1",
        platform_message_id="100",
        summary="Note",
        classification="NOT_MISLEADING",
    )

    user_event_id = await event_publisher.publish_user_registered(
        user_id=uuid4(),
        username="user1",
        email=None,
        registration_source="web",
    )

    assert note_event_id != user_event_id
    assert note_event_id is not None
    assert user_event_id is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_message_nak_on_handler_failure():
    handler_called = False
    handler_failed = False

    async def failing_handler(event: NoteCreatedEvent) -> None:
        nonlocal handler_called, handler_failed
        handler_called = True
        handler_failed = True
        raise ValueError("Simulated handler failure")

    subscription_handler = None
    delivered_msg = None

    async def mock_subscribe(subject: str, queue: str = "", callback=None, **kwargs):
        nonlocal subscription_handler
        subscription_handler = callback

    async def mock_publish(subject: str, message: str, **kwargs) -> PubAck:
        nonlocal delivered_msg
        if subscription_handler:
            mock_msg = MagicMock()
            mock_msg.data = message.encode() if isinstance(message, str) else message
            mock_msg.ack = AsyncMock()
            mock_msg.nak = AsyncMock()
            delivered_msg = mock_msg
            await subscription_handler(mock_msg)
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "ping", new_callable=AsyncMock, return_value=True),
        patch.object(
            nats_client, "publish", new_callable=AsyncMock, side_effect=mock_publish
        ) as _mock_pub,
        patch.object(nats_client, "subscribe", new_callable=AsyncMock, side_effect=mock_subscribe),
    ):
        event_subscriber.register_handler(EventType.NOTE_CREATED, failing_handler)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        _result = await event_publisher.publish_note_created(
            note_id=uuid4(),
            author_id="test_author",
            platform_message_id="222",
            summary="Test nak",
            classification="NOT_MISLEADING",
        )

        await asyncio.sleep(0.1)

        assert handler_called
        assert handler_failed
        assert delivered_msg is not None
        delivered_msg.nak.assert_called_once()
        delivered_msg.ack.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_message_ack_on_all_handlers_success():
    handler1_called = False
    handler2_called = False

    async def handler1(event: NoteCreatedEvent) -> None:
        nonlocal handler1_called
        handler1_called = True

    async def handler2(event: NoteCreatedEvent) -> None:
        nonlocal handler2_called
        handler2_called = True

    subscription_handler = None
    delivered_msg = None

    async def mock_subscribe(subject: str, queue: str = "", callback=None, **kwargs):
        nonlocal subscription_handler
        subscription_handler = callback

    async def mock_publish(subject: str, message: str, **kwargs) -> PubAck:
        nonlocal delivered_msg
        if subscription_handler:
            mock_msg = MagicMock()
            mock_msg.data = message.encode() if isinstance(message, str) else message
            mock_msg.ack = AsyncMock()
            mock_msg.nak = AsyncMock()
            delivered_msg = mock_msg
            await subscription_handler(mock_msg)
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "ping", new_callable=AsyncMock, return_value=True),
        patch.object(
            nats_client, "publish", new_callable=AsyncMock, side_effect=mock_publish
        ) as _mock_pub,
        patch.object(nats_client, "subscribe", new_callable=AsyncMock, side_effect=mock_subscribe),
    ):
        event_subscriber.register_handler(EventType.NOTE_CREATED, handler1)
        event_subscriber.register_handler(EventType.NOTE_CREATED, handler2)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        _result = await event_publisher.publish_note_created(
            note_id=uuid4(),
            author_id="test_author",
            platform_message_id="444",
            summary="Test ack",
            classification="NOT_MISLEADING",
        )

        await asyncio.sleep(0.1)

        assert handler1_called
        assert handler2_called
        assert delivered_msg is not None
        delivered_msg.ack.assert_called_once()
        delivered_msg.nak.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_message_nak_on_partial_handler_failure():
    handler1_called = False
    handler2_called = False

    async def successful_handler(event: NoteCreatedEvent) -> None:
        nonlocal handler1_called
        handler1_called = True

    async def failing_handler(event: NoteCreatedEvent) -> None:
        nonlocal handler2_called
        handler2_called = True
        raise RuntimeError("Handler 2 failed")

    subscription_handler = None
    delivered_msg = None

    async def mock_subscribe(subject: str, queue: str = "", callback=None, **kwargs):
        nonlocal subscription_handler
        subscription_handler = callback

    async def mock_publish(subject: str, message: str, **kwargs) -> PubAck:
        nonlocal delivered_msg
        if subscription_handler:
            mock_msg = MagicMock()
            mock_msg.data = message.encode() if isinstance(message, str) else message
            mock_msg.ack = AsyncMock()
            mock_msg.nak = AsyncMock()
            delivered_msg = mock_msg
            await subscription_handler(mock_msg)
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "ping", new_callable=AsyncMock, return_value=True),
        patch.object(
            nats_client, "publish", new_callable=AsyncMock, side_effect=mock_publish
        ) as _mock_pub,
        patch.object(nats_client, "subscribe", new_callable=AsyncMock, side_effect=mock_subscribe),
    ):
        event_subscriber.register_handler(EventType.NOTE_CREATED, successful_handler)
        event_subscriber.register_handler(EventType.NOTE_CREATED, failing_handler)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        _result = await event_publisher.publish_note_created(
            note_id=uuid4(),
            author_id="test_author",
            platform_message_id="666",
            summary="Test partial failure",
            classification="NOT_MISLEADING",
        )

        await asyncio.sleep(0.1)

        assert handler1_called
        assert handler2_called
        assert delivered_msg is not None
        delivered_msg.nak.assert_called_once()
        delivered_msg.ack.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_does_not_mutate_input():
    event = NoteCreatedEvent(
        event_id="",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    original_event_id = event.event_id

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock),
    ):
        returned_event_id = await event_publisher.publish_event(event)

        assert event.event_id == original_event_id
        assert returned_event_id != original_event_id
        assert len(returned_event_id) > 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_adds_idempotency_headers():
    event = NoteCreatedEvent(
        event_id="test_event_id_123",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock) as mock_publish,
    ):
        await event_publisher.publish_event(event)

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        headers = call_args.kwargs["headers"]

        assert "Msg-Id" in headers
        assert headers["Msg-Id"] == event.event_id
        assert headers["event-id"] == event.event_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_adds_correlation_id_from_headers():
    event = NoteCreatedEvent(
        event_id="test_event_id_456",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    custom_headers = {"correlation_id": "custom_correlation_123"}

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock) as mock_publish,
    ):
        await event_publisher.publish_event(event, headers=custom_headers)

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        headers = call_args.kwargs["headers"]

        assert "X-Correlation-Id" in headers
        assert headers["X-Correlation-Id"] == "custom_correlation_123"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_uses_event_id_as_correlation_id_when_not_provided():
    event = NoteCreatedEvent(
        event_id="test_event_id_789",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock) as mock_publish,
    ):
        await event_publisher.publish_event(event)

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        headers = call_args.kwargs["headers"]

        assert "X-Correlation-Id" in headers
        assert headers["X-Correlation-Id"] == event.event_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_retries_on_transient_nats_error():
    event = NoteCreatedEvent(
        event_id="test_retry_123",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    call_count = 0

    async def failing_publish(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise NATSError("Temporary connection issue")
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock, side_effect=failing_publish),
    ):
        result = await event_publisher.publish_event(event)

        assert call_count == 3
        assert result == event.event_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_retries_on_timeout_error():
    event = NoteCreatedEvent(
        event_id="test_timeout_456",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    call_count = 0

    async def timeout_publish(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise TimeoutError("Request timeout")
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock, side_effect=timeout_publish),
    ):
        result = await event_publisher.publish_event(event)

        assert call_count == 2
        assert result == event.event_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_fails_after_max_retries():
    event = NoteCreatedEvent(
        event_id="test_max_retries_789",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    async def always_failing_publish(*args, **kwargs):
        raise NATSError("Persistent connection issue")

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(
            nats_client, "publish", new_callable=AsyncMock, side_effect=always_failing_publish
        ),
        pytest.raises(NATSError, match="Persistent connection issue"),
    ):
        await event_publisher.publish_event(event)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_does_not_retry_non_transient_errors():
    event = NoteCreatedEvent(
        event_id="test_no_retry_111",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    call_count = 0

    async def validation_error_publish(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise ValueError("Invalid event data")

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(
            nats_client, "publish", new_callable=AsyncMock, side_effect=validation_error_publish
        ),
    ):
        with pytest.raises(ValueError, match="Invalid event data"):
            await event_publisher.publish_event(event)

        assert call_count == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscriber_handlers_execute_in_parallel():
    handler1_start = None
    handler1_end = None
    handler2_start = None
    handler2_end = None

    async def slow_handler1(event: NoteCreatedEvent) -> None:
        nonlocal handler1_start, handler1_end
        handler1_start = asyncio.get_event_loop().time()
        await asyncio.sleep(0.1)
        handler1_end = asyncio.get_event_loop().time()

    async def slow_handler2(event: NoteCreatedEvent) -> None:
        nonlocal handler2_start, handler2_end
        handler2_start = asyncio.get_event_loop().time()
        await asyncio.sleep(0.1)
        handler2_end = asyncio.get_event_loop().time()

    subscription_handler = None

    async def mock_subscribe(subject: str, queue: str = "", callback=None, **kwargs):
        nonlocal subscription_handler
        subscription_handler = callback

    async def mock_publish(subject: str, message: str, **kwargs) -> PubAck:
        if subscription_handler:
            mock_msg = MagicMock()
            mock_msg.data = message.encode() if isinstance(message, str) else message
            mock_msg.ack = AsyncMock()
            mock_msg.nak = AsyncMock()
            mock_msg.metadata = MagicMock(return_value=None)
            await subscription_handler(mock_msg)
            return mock_msg
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "ping", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock, side_effect=mock_publish),
        patch.object(nats_client, "subscribe", new_callable=AsyncMock, side_effect=mock_subscribe),
    ):
        event_subscriber.register_handler(EventType.NOTE_CREATED, slow_handler1)
        event_subscriber.register_handler(EventType.NOTE_CREATED, slow_handler2)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        await event_publisher.publish_note_created(
            note_id=uuid4(),
            author_id="test_author",
            platform_message_id="888",
            summary="Test parallel",
            classification="NOT_MISLEADING",
        )

        await asyncio.sleep(0.2)

        assert handler1_start is not None
        assert handler2_start is not None
        assert abs(handler1_start - handler2_start) < 0.05


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscriber_handler_timeout_nacks_message():
    handler_called = False

    async def timeout_handler(event: NoteCreatedEvent) -> None:
        nonlocal handler_called
        handler_called = True
        await asyncio.sleep(5)

    subscription_handler = None
    delivered_msg = None

    async def mock_subscribe(subject: str, queue: str = "", callback=None, **kwargs):
        nonlocal subscription_handler
        subscription_handler = callback

    async def mock_publish(subject: str, message: str, **kwargs) -> PubAck:
        nonlocal delivered_msg
        if subscription_handler:
            mock_msg = MagicMock()
            mock_msg.data = message.encode() if isinstance(message, str) else message
            mock_msg.ack = AsyncMock()
            mock_msg.nak = AsyncMock()
            mock_metadata = MagicMock()
            mock_metadata.num_delivered = 1
            mock_msg.metadata = mock_metadata
            delivered_msg = mock_msg
            await subscription_handler(mock_msg)
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch("src.events.subscriber.settings.NATS_HANDLER_TIMEOUT", 2),
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "ping", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock, side_effect=mock_publish),
        patch.object(nats_client, "subscribe", new_callable=AsyncMock, side_effect=mock_subscribe),
    ):
        event_subscriber.register_handler(EventType.NOTE_CREATED, timeout_handler)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        _result = await event_publisher.publish_note_created(
            note_id=uuid4(),
            author_id="test_author",
            platform_message_id="888",
            summary="Test timeout",
            classification="NOT_MISLEADING",
        )

        # Wait for the handler timeout to trigger (handler timeout is 2 seconds, add margin for processing)
        await asyncio.sleep(4)

        assert handler_called
        assert delivered_msg is not None
        delivered_msg.nak.assert_called_once()
        delivered_msg.ack.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscriber_partial_handler_timeout_nacks_message():
    handler1_called = False
    handler2_called = False

    async def fast_handler(event: NoteCreatedEvent) -> None:
        nonlocal handler1_called
        handler1_called = True

    async def timeout_handler(event: NoteCreatedEvent) -> None:
        nonlocal handler2_called
        handler2_called = True
        await asyncio.sleep(100)

    subscription_handler = None
    delivered_msg = None

    async def mock_subscribe(subject: str, queue: str = "", callback=None, **kwargs):
        nonlocal subscription_handler
        subscription_handler = callback

    async def mock_publish(subject: str, message: str, **kwargs) -> PubAck:
        nonlocal delivered_msg
        if subscription_handler:
            mock_msg = MagicMock()
            mock_msg.data = message.encode() if isinstance(message, str) else message
            mock_msg.ack = AsyncMock()
            mock_msg.nak = AsyncMock()
            mock_metadata = MagicMock()
            mock_metadata.num_delivered = 1
            mock_msg.metadata = mock_metadata
            delivered_msg = mock_msg
            await subscription_handler(mock_msg)
        return PubAck(stream="test-stream", seq=1, duplicate=False)

    with (
        patch("src.events.subscriber.settings.NATS_HANDLER_TIMEOUT", 2),
        patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "ping", new_callable=AsyncMock, return_value=True),
        patch.object(nats_client, "publish", new_callable=AsyncMock, side_effect=mock_publish),
        patch.object(nats_client, "subscribe", new_callable=AsyncMock, side_effect=mock_subscribe),
    ):
        event_subscriber.register_handler(EventType.NOTE_CREATED, fast_handler)
        event_subscriber.register_handler(EventType.NOTE_CREATED, timeout_handler)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        _result = await event_publisher.publish_note_created(
            note_id=uuid4(),
            author_id="test_author",
            platform_message_id="777",
            summary="Test partial timeout",
            classification="NOT_MISLEADING",
        )

        # Wait for handler timeout to trigger (handler timeout is 2 seconds, add margin for processing)
        await asyncio.sleep(4)

        assert handler1_called
        assert handler2_called
        assert delivered_msg is not None
        delivered_msg.nak.assert_called_once()
        delivered_msg.ack.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_note_score_updated_event_validation():
    test_note_id = uuid4()
    event = NoteScoreUpdatedEvent(
        event_id="score_test_123",
        note_id=test_note_id,
        score=0.75,
        confidence="standard",
        algorithm="matrix_factorization",
        rating_count=10,
        tier=3,
        tier_name="intermediate",
        original_message_id="msg_123",
        channel_id="ch_456",
        community_server_id="guild_789",
    )

    assert event.event_type == EventType.NOTE_SCORE_UPDATED
    assert event.note_id == test_note_id
    assert event.score == 0.75
    assert event.rating_count == 10
    assert event.tier == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_note_score_updated_event_score_validation():
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        NoteScoreUpdatedEvent(
            event_id="test",
            note_id=uuid4(),
            score=1.5,
            confidence="standard",
            algorithm="test",
            rating_count=5,
            tier=1,
            tier_name="basic",
        )

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        NoteScoreUpdatedEvent(
            event_id="test",
            note_id=uuid4(),
            score=-0.1,
            confidence="standard",
            algorithm="test",
            rating_count=5,
            tier=1,
            tier_name="basic",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_note_score_updated(setup_nats):
    event_id = await event_publisher.publish_note_score_updated(
        note_id=uuid4(),
        score=0.85,
        confidence="standard",
        algorithm="matrix_factorization",
        rating_count=15,
        tier=3,
        tier_name="intermediate",
        original_message_id="msg_abc",
        channel_id="ch_def",
        community_server_id="guild_ghi",
    )

    assert event_id is not None
    assert len(event_id) > 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_scoring_event_publisher_uses_event_publisher(setup_nats):
    await ScoringEventPublisher.publish_note_score_updated(
        note_id=uuid4(),
        score=0.92,
        confidence="provisional",
        algorithm="bayesian_average",
        rating_count=3,
        tier=1,
        tier_name="minimal",
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_note_score_updated_confidence_validation():
    with pytest.raises(ValidationError, match="Input should be"):
        NoteScoreUpdatedEvent(
            event_id="test",
            note_id=uuid4(),
            score=0.5,
            confidence="invalid_confidence",
            algorithm="test",
            rating_count=5,
            tier=1,
            tier_name="basic",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_increments_failure_metric_after_max_retries():
    from src.monitoring.instance import InstanceMetadata
    from src.monitoring.metrics import nats_events_failed_total

    event = NoteCreatedEvent(
        event_id="test_metric_failure",
        note_id=uuid4(),
        author_id="author_456",
        platform_message_id="789",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    # Get initial metric value
    instance_id = InstanceMetadata.get_instance_id()
    # Note: nats.errors.Error class name is "Error", not "NATSError"
    initial_value = nats_events_failed_total.labels(
        event_type="note.created", error_type="Error", instance_id=instance_id
    )._value.get()

    async def always_failing_publish(*args, **kwargs):
        raise NATSError("Persistent connection issue")

    with patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True):
        with (
            patch.object(
                nats_client, "publish", new_callable=AsyncMock, side_effect=always_failing_publish
            ),
            pytest.raises(NATSError, match="Persistent connection issue"),
        ):
            await event_publisher.publish_event(event)

        # Verify metric was incremented exactly once (after all retries exhausted)
        final_value = nats_events_failed_total.labels(
            event_type="note.created", error_type="Error", instance_id=instance_id
        )._value.get()
        assert final_value == initial_value + 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_publish_event_increments_failure_metric_with_correct_error_type():
    from src.monitoring.instance import InstanceMetadata
    from src.monitoring.metrics import nats_events_failed_total

    event = NoteCreatedEvent(
        event_id="test_metric_timeout",
        note_id=uuid4(),
        author_id="author_789",
        platform_message_id="101",
        summary="Test note",
        classification="NOT_MISLEADING",
    )

    # Get initial metric value for TimeoutError
    instance_id = InstanceMetadata.get_instance_id()
    initial_value = nats_events_failed_total.labels(
        event_type="note.created", error_type="TimeoutError", instance_id=instance_id
    )._value.get()

    async def always_timeout_publish(*args, **kwargs):
        raise TimeoutError("Request timeout")

    with patch.object(nats_client, "is_connected", new_callable=AsyncMock, return_value=True):
        with (
            patch.object(
                nats_client, "publish", new_callable=AsyncMock, side_effect=always_timeout_publish
            ),
            pytest.raises(TimeoutError, match="Request timeout"),
        ):
            await event_publisher.publish_event(event)

        # Verify metric was incremented with correct error_type label
        final_value = nats_events_failed_total.labels(
            event_type="note.created", error_type="TimeoutError", instance_id=instance_id
        )._value.get()
        assert final_value == initial_value + 1
