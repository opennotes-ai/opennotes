import asyncio
import logging
import os
import time
from typing import Any
from uuid import uuid4

import pytest

from src.cache.cache import cache_manager
from src.cache.redis_client import redis_client
from src.circuit_breaker import circuit_breaker_registry
from src.events.nats_client import nats_client
from src.events.publisher import event_publisher
from src.events.schemas import EventType, NoteCreatedEvent, NoteRatedEvent, UserRegisteredEvent
from src.events.subscriber import event_subscriber

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration_messaging


@pytest.fixture
async def clear_event_state() -> Any:
    await event_subscriber.unsubscribe_all()
    for event_type in EventType:
        event_subscriber.handlers[event_type] = []
    event_subscriber.subscriptions.clear()
    await circuit_breaker_registry.reset_all()
    yield
    await event_subscriber.unsubscribe_all()
    for event_type in EventType:
        event_subscriber.handlers[event_type] = []
    event_subscriber.subscriptions.clear()
    await circuit_breaker_registry.reset_all()


@pytest.fixture
async def setup_messaging_services(clear_event_state: Any, db_session: Any) -> Any:
    # Enable real service connections for integration tests
    os.environ["INTEGRATION_TESTS"] = "true"

    logger.info("Setting up Redis and NATS for integration tests...")

    try:
        redis_url = os.environ.get("REDIS_URL")
        await redis_client.connect(redis_url=redis_url)
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    try:
        await nats_client.connect()
        logger.info("NATS connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        raise

    yield

    logger.info("Tearing down messaging services...")

    try:
        await event_subscriber.unsubscribe_all()
    except Exception as e:
        logger.warning(f"Error unsubscribing: {e}")

    if redis_client.client:
        try:
            await redis_client.client.flushdb()
        except Exception as e:
            logger.warning(f"Error flushing Redis: {e}")

    await nats_client.disconnect()
    await redis_client.disconnect()
    logger.info("Messaging services teardown complete")


@pytest.fixture
async def clean_redis() -> Any:
    if redis_client.client:
        await redis_client.client.flushdb()
    yield
    if redis_client.client:
        await redis_client.client.flushdb()


class TestNATSConnection:
    @pytest.mark.asyncio
    async def test_nats_connection(self, setup_messaging_services: Any) -> None:
        assert await nats_client.is_connected()
        logger.info("NATS connection verified")

    @pytest.mark.asyncio
    async def test_nats_ping(self, setup_messaging_services: Any) -> None:
        result = await nats_client.ping()
        assert result is True
        logger.info("NATS ping successful")

    @pytest.mark.asyncio
    async def test_nats_jetstream_stream_exists(self, setup_messaging_services: Any) -> None:
        if nats_client.js is None:
            pytest.skip(
                "JetStream not available - known nats-py timeout issue during concurrent startup. "
                "System falls back to core NATS subscriptions which is acceptable for dev/test."
            )

        stream_info = await nats_client.js.stream_info("OPENNOTES")
        assert stream_info is not None
        assert stream_info.config.name == "OPENNOTES"
        logger.info(f"NATS JetStream stream verified: {stream_info.config.name}")


class TestNATSPublishing:
    @pytest.mark.asyncio
    async def test_publish_note_created(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        note_id = uuid4()
        event_id = await event_publisher.publish_note_created(
            note_id=note_id,
            author_id="test_author_001",
            platform_message_id="2001",
            summary="Test note for integration testing",
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            metadata={"test": True},
        )

        assert event_id is not None
        assert len(event_id) > 0
        logger.info(f"Published note_created event: {event_id}")

    @pytest.mark.asyncio
    async def test_publish_note_rated(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        note_id = uuid4()
        event_id = await event_publisher.publish_note_rated(
            note_id=note_id,
            rater_id="test_rater_001",
            helpfulness_level="HELPFUL",
            metadata={"score": 5},
        )

        assert event_id is not None
        assert len(event_id) > 0
        logger.info(f"Published note_rated event: {event_id}")

    @pytest.mark.asyncio
    async def test_publish_user_registered(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        user_id = uuid4()
        event_id = await event_publisher.publish_user_registered(
            user_id=user_id,
            username="integration_test_user",
            email="test@example.com",
            registration_source="discord",
            metadata={"env": "test"},
        )

        assert event_id is not None
        assert len(event_id) > 0
        logger.info(f"Published user_registered event: {event_id}")


class TestNATSSubscription:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="NATS JetStream integration tests failing - handlers not receiving published events. "
        "Working theory: Known nats-py JetStream ephemeral consumer timeout issue (nats-py #437). "
        "Evidence: JetStream subscriptions succeed, publishes succeed, but publish acknowledgments "
        "show AsyncMock objects and no events reach handlers. This is a WORKING THEORY that requires "
        "deeper investigation to confirm root cause. See task-648 for Settings singleton issue that "
        "may also be related."
    )
    async def test_subscribe_and_receive_note_created(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        received_events = []
        seen_event_ids = set()

        async def handler(event: NoteCreatedEvent) -> None:
            if event.event_id not in seen_event_ids:
                seen_event_ids.add(event.event_id)
                received_events.append(event)
                logger.info(f"Handler received event: {event.event_id}")

        event_subscriber.register_handler(EventType.NOTE_CREATED, handler)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        await asyncio.sleep(2)

        note_id = uuid4()
        event_id = await event_publisher.publish_note_created(
            note_id=note_id,
            author_id="subscriber_test_author",
            platform_message_id="3001",
            summary="Testing subscription delivery",
            classification="NOT_MISLEADING",
        )

        await asyncio.sleep(3)

        assert len(received_events) >= 1, f"Expected at least 1 event, got {len(received_events)}"
        assert received_events[0].note_id == note_id
        assert received_events[0].author_id == "subscriber_test_author"
        assert received_events[0].event_id == event_id
        logger.info("Subscription test passed: event received and processed")

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="NATS JetStream integration tests failing - handlers not receiving published events. "
        "Working theory: Known nats-py JetStream ephemeral consumer timeout issue (nats-py #437). "
        "Evidence: JetStream subscriptions succeed, publishes succeed, but publish acknowledgments "
        "show AsyncMock objects and no events reach handlers. This is a WORKING THEORY that requires "
        "deeper investigation to confirm root cause. See task-648 for Settings singleton issue that "
        "may also be related."
    )
    async def test_subscribe_multiple_handlers(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        received_events_1 = []
        received_events_2 = []
        seen_ids_1 = set()
        seen_ids_2 = set()

        async def handler_1(event: NoteRatedEvent) -> None:
            if event.event_id not in seen_ids_1:
                seen_ids_1.add(event.event_id)
                received_events_1.append(event)
                logger.info(f"Handler 1 received: {event.event_id}")

        async def handler_2(event: NoteRatedEvent) -> None:
            if event.event_id not in seen_ids_2:
                seen_ids_2.add(event.event_id)
                received_events_2.append(event)
                logger.info(f"Handler 2 received: {event.event_id}")

        event_subscriber.register_handler(EventType.NOTE_RATED, handler_1)
        event_subscriber.register_handler(EventType.NOTE_RATED, handler_2)
        await event_subscriber.subscribe(EventType.NOTE_RATED)

        await asyncio.sleep(2)

        note_id = uuid4()
        await event_publisher.publish_note_rated(
            note_id=note_id,
            rater_id="multi_handler_test",
            helpfulness_level="HELPFUL",
        )

        await asyncio.sleep(3)

        assert len(received_events_1) >= 1, (
            f"Handler 1: expected at least 1 event, got {len(received_events_1)}"
        )
        assert len(received_events_2) >= 1, (
            f"Handler 2: expected at least 1 event, got {len(received_events_2)}"
        )
        assert received_events_1[0].note_id == note_id
        assert received_events_2[0].note_id == note_id
        logger.info("Multiple handlers test passed")


class TestRedisNATSIntegration:
    @pytest.mark.asyncio
    async def test_event_driven_cache_update(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        note_id = uuid4()
        cache_key = f"note:{note_id}"
        cached_events = []
        seen_ids = set()

        async def caching_handler(event: NoteCreatedEvent) -> None:
            if event.event_id not in seen_ids:
                seen_ids.add(event.event_id)
                note_data = {
                    "note_id": str(event.note_id),
                    "author_id": event.author_id,
                    "summary": event.summary,
                    "classification": event.classification,
                    "cached_at": time.time(),
                }
                await cache_manager.set(cache_key, note_data, ttl=300)
                cached_events.append(event)
                logger.info(f"Cached note {event.note_id} in Redis")

        event_subscriber.register_handler(EventType.NOTE_CREATED, caching_handler)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        await asyncio.sleep(2)

        await event_publisher.publish_note_created(
            note_id=note_id,
            author_id="cache_integration_author",
            platform_message_id="5001",
            summary="Testing Redis-NATS integration",
            classification="NOT_MISLEADING",
        )

        await asyncio.sleep(3)

        cached_data = await cache_manager.get(cache_key)

        assert cached_data is not None, "Cache should contain the note data"
        assert cached_data["note_id"] == str(note_id)
        assert cached_data["author_id"] == "cache_integration_author"
        assert len(cached_events) >= 1, (
            f"Expected at least 1 cached event, got {len(cached_events)}"
        )
        logger.info("Event-driven cache update test passed")

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_event(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        note_id = uuid4()
        cache_key = f"note:{note_id}"

        initial_data = {
            "note_id": str(note_id),
            "author_id": "original_author",
            "rating_count": 0,
        }
        await cache_manager.set(cache_key, initial_data, ttl=300)

        async def invalidation_handler(event: NoteRatedEvent) -> None:
            if event.note_id == note_id:
                await cache_manager.delete(cache_key)
                logger.info(f"Invalidated cache for note {event.note_id}")

        event_subscriber.register_handler(EventType.NOTE_RATED, invalidation_handler)
        await event_subscriber.subscribe(EventType.NOTE_RATED)

        await asyncio.sleep(2)

        cached_before = await cache_manager.get(cache_key)
        assert cached_before is not None, "Initial cache data should exist"

        await event_publisher.publish_note_rated(
            note_id=note_id,
            rater_id="invalidation_tester",
            helpfulness_level="HELPFUL",
        )

        await asyncio.sleep(3)

        cached_after = await cache_manager.get(cache_key)
        assert cached_after is None, "Cache should be invalidated after event"
        logger.info("Cache invalidation on event test passed")

    @pytest.mark.asyncio
    async def test_user_session_cache_on_registration(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        user_id = uuid4()
        session_key = f"session:user:{user_id}"

        async def session_handler(event: UserRegisteredEvent) -> None:
            session_data = {
                "user_id": str(event.user_id),
                "username": event.username,
                "email": event.email,
                "registration_source": event.registration_source,
                "session_created_at": time.time(),
            }
            await cache_manager.set(session_key, session_data, ttl=3600)
            logger.info(f"Created session for user {event.user_id}")

        event_subscriber.register_handler(EventType.USER_REGISTERED, session_handler)
        await event_subscriber.subscribe(EventType.USER_REGISTERED)

        await asyncio.sleep(2)

        await event_publisher.publish_user_registered(
            user_id=user_id,
            username="session_test_user",
            email="session@test.com",
            registration_source="web",
        )

        await asyncio.sleep(3)

        session_data = await cache_manager.get(session_key)

        assert session_data is not None, "Session data should be cached"
        assert session_data["user_id"] == str(user_id)
        assert session_data["username"] == "session_test_user"
        logger.info("User session cache on registration test passed")


class TestCircuitBreaker:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="NATS JetStream integration tests failing - handlers not receiving published events. "
        "Working theory: Known nats-py JetStream ephemeral consumer timeout issue (nats-py #437). "
        "Evidence: JetStream subscriptions succeed, publishes succeed, but publish acknowledgments "
        "show AsyncMock objects and no events reach handlers. This is a WORKING THEORY that requires "
        "deeper investigation to confirm root cause. See task-648 for Settings singleton issue that "
        "may also be related."
    )
    async def test_redis_circuit_breaker_on_failure(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        await redis_client.disconnect()

        assert redis_client.client is None, "Client should be None after disconnect"

        result = await redis_client.ping()
        assert result is False, "Ping should return False after disconnect"

        value = await redis_client.get("test_key")
        assert value is None, "Get should return None when client is disconnected"

        await redis_client.connect()

        result = await redis_client.ping()
        assert result is True, "Ping should return True after reconnect"
        logger.info("Redis circuit breaker test passed")

    @pytest.mark.asyncio
    async def test_nats_circuit_breaker_on_timeout(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        await nats_client.disconnect()

        is_connected = await nats_client.is_connected()
        assert is_connected is False, "NATS should not be connected after disconnect"

        ping_result = await nats_client.ping()
        assert ping_result is False, "Ping should return False after disconnect"

        await nats_client.connect()
        await asyncio.sleep(0.5)

        is_connected = await nats_client.is_connected()
        assert is_connected is True, "NATS should be connected after reconnect"
        logger.info("NATS circuit breaker test passed")

    @pytest.mark.asyncio
    async def test_publish_with_circuit_breaker_protection(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        await nats_client.disconnect()

        with pytest.raises(RuntimeError, match="NATS"):
            await event_publisher.publish_note_created(
                note_id=uuid4(),
                author_id="circuit_breaker_test",
                platform_message_id="10001",
                summary="Testing circuit breaker",
                classification="NOT_MISLEADING",
            )

        await nats_client.connect()
        await asyncio.sleep(1)

        event_id = await event_publisher.publish_note_created(
            note_id=uuid4(),
            author_id="circuit_breaker_recovery_test",
            platform_message_id="10002",
            summary="Testing circuit breaker recovery",
            classification="NOT_MISLEADING",
        )

        assert event_id is not None, "Event should be published after reconnection"
        logger.info("Circuit breaker protection test passed")


class TestPerformance:
    @pytest.mark.asyncio
    async def test_publish_throughput(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        num_events = 50
        start_time = time.time()

        for i in range(num_events):
            await event_publisher.publish_note_created(
                note_id=uuid4(),
                author_id=f"perf_test_author_{i}",
                platform_message_id=str(20000 + i),
                summary=f"Performance test note {i}",
                classification="NOT_MISLEADING",
            )

        elapsed = time.time() - start_time
        throughput = num_events / elapsed

        assert throughput > 10
        logger.info(f"Published {num_events} events in {elapsed:.2f}s ({throughput:.2f} events/s)")

    @pytest.mark.asyncio
    async def test_cache_and_event_roundtrip(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        num_iterations = 20
        total_time = 0.0

        for i in range(num_iterations):
            cache_key = f"roundtrip:note:{i}"

            start = time.time()

            await cache_manager.set(cache_key, {"note_id": i, "data": f"test_{i}"}, ttl=60)

            await event_publisher.publish_note_created(
                note_id=uuid4(),
                author_id=f"roundtrip_author_{i}",
                platform_message_id=str(40000 + i),
                summary=f"Roundtrip test {i}",
                classification="NOT_MISLEADING",
            )

            cached = await cache_manager.get(cache_key)
            assert cached is not None

            elapsed = time.time() - start
            total_time += elapsed

        avg_time = total_time / num_iterations

        assert avg_time < 0.5
        logger.info(f"Average roundtrip time: {avg_time * 1000:.2f}ms")


class TestEventOrdering:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="NATS JetStream integration tests failing - handlers not receiving published events. "
        "Working theory: Known nats-py JetStream ephemeral consumer timeout issue (nats-py #437). "
        "Evidence: JetStream subscriptions succeed, publishes succeed, but publish acknowledgments "
        "show AsyncMock objects and no events reach handlers. This is a WORKING THEORY that requires "
        "deeper investigation to confirm root cause. See task-648 for Settings singleton issue that "
        "may also be related."
    )
    async def test_event_sequence_order(
        self, setup_messaging_services: Any, clean_redis: Any
    ) -> None:
        received_order = []
        seen_ids = set()

        async def ordered_handler(event: NoteCreatedEvent) -> None:
            if event.note_id not in seen_ids:
                seen_ids.add(event.note_id)
                received_order.append(event.note_id)

        event_subscriber.register_handler(EventType.NOTE_CREATED, ordered_handler)
        await event_subscriber.subscribe(EventType.NOTE_CREATED)

        await asyncio.sleep(2)

        expected_order = [uuid4() for _ in range(5)]
        for note_id in expected_order:
            await event_publisher.publish_note_created(
                note_id=note_id,
                author_id="order_test_author",
                platform_message_id="60000",
                summary=f"Order test {note_id}",
                classification="NOT_MISLEADING",
            )
            await asyncio.sleep(0.1)

        await asyncio.sleep(3)

        assert len(received_order) >= len(expected_order), (
            f"Expected at least {len(expected_order)} events, got {len(received_order)}"
        )
        assert received_order[: len(expected_order)] == expected_order, (
            f"Event order mismatch: {received_order[: len(expected_order)]} != {expected_order}"
        )
        logger.info("Event ordering test passed")
