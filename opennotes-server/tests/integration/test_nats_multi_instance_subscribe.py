"""Integration tests for multi-instance NATS subscription behavior.

These tests verify that multiple instances can subscribe to the same
subjects without conflicts, simulating Cloud Run scaling behavior.

The bind-or-create pattern ensures:
1. First instance creates the consumer
2. Subsequent instances bind to existing consumer (join queue group)
3. No consumer deletion occurs
"""

import asyncio
import logging
import os
from typing import Any

import nats
import pytest
from nats.js.api import ConsumerConfig, RetentionPolicy, StorageType, StreamConfig

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration_messaging

STREAM_NAME = "MULTI_INSTANCE_TEST"


def get_nats_url() -> str:
    """Get NATS URL dynamically - must be called after testcontainers starts."""
    return os.environ.get("NATS_URL", "nats://localhost:4222")


@pytest.fixture
async def jetstream_with_workqueue(db_session: Any) -> Any:
    """Create a JetStream context with WORK_QUEUE retention.

    This mirrors production configuration where only one consumer
    can filter on a given subject.

    Note: Depends on db_session to ensure testcontainers is started.
    """
    nats_url = get_nats_url()
    logger.info(f"Connecting to NATS at: {nats_url}")
    nc = await nats.connect(nats_url, max_reconnect_attempts=3)
    js = nc.jetstream(timeout=30.0)

    try:
        await js.delete_stream(STREAM_NAME)
    except Exception:
        pass

    await js.add_stream(
        StreamConfig(
            name=STREAM_NAME,
            subjects=[f"{STREAM_NAME}.>"],
            retention=RetentionPolicy.WORK_QUEUE,
            storage=StorageType.MEMORY,
            max_age=60,
        )
    )
    logger.info(f"Created stream {STREAM_NAME} with WORK_QUEUE retention")

    yield {"nc": nc, "js": js}

    try:
        await js.delete_stream(STREAM_NAME)
    except Exception:
        pass
    await nc.drain()
    await nc.close()


class TestMultiInstanceSubscribe:
    """Tests for multi-instance subscription scenarios."""

    @pytest.mark.asyncio
    async def test_second_instance_binds_to_existing_consumer(
        self, jetstream_with_workqueue: dict[str, Any]
    ) -> None:
        """Second instance should bind to consumer created by first instance.

        This simulates what happens when Cloud Run starts a second instance
        while the first is still running.
        """
        js = jetstream_with_workqueue["js"]
        subject = f"{STREAM_NAME}.bind_test"
        consumer_name = "test_shared_consumer"

        messages_received: dict[str, list[str]] = {"instance1": [], "instance2": []}

        async def handler1(msg: Any) -> None:
            messages_received["instance1"].append(msg.data.decode())
            await msg.ack()

        async def handler2(msg: Any) -> None:
            messages_received["instance2"].append(msg.data.decode())
            await msg.ack()

        config = ConsumerConfig(
            durable_name=consumer_name,
            deliver_group=consumer_name,
        )
        sub1 = await js.subscribe(subject, cb=handler1, config=config)
        logger.info("Instance 1 created consumer")

        sub2 = await js.subscribe(
            subject,
            cb=handler2,
            durable=consumer_name,
            stream=STREAM_NAME,
        )
        logger.info("Instance 2 bound to existing consumer")

        for i in range(10):
            await js.publish(subject, f"message-{i}".encode())

        await asyncio.sleep(1.0)

        total_received = len(messages_received["instance1"]) + len(messages_received["instance2"])
        logger.info(f"Instance 1 received {len(messages_received['instance1'])} messages")
        logger.info(f"Instance 2 received {len(messages_received['instance2'])} messages")

        assert total_received == 10, f"Expected 10 messages total, got {total_received}"

        await sub1.unsubscribe()
        await sub2.unsubscribe()

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_uses_bind_pattern(
        self, jetstream_with_workqueue: dict[str, Any]
    ) -> None:
        """Concurrent subscription attempts should not cause consumer conflicts.

        Simulates multiple instances starting at exactly the same time.
        One will create the consumer, others will get a conflict but should
        be able to bind to it.
        """
        js = jetstream_with_workqueue["js"]
        subject = f"{STREAM_NAME}.concurrent_test"
        consumer_name = "concurrent_consumer"

        results: list[tuple[str, int, Any]] = []

        async def subscribe_instance(instance_id: int) -> tuple[str, int, Any]:
            try:
                config = ConsumerConfig(
                    durable_name=consumer_name,
                    deliver_group=consumer_name,
                )
                sub = await js.subscribe(
                    subject,
                    cb=lambda msg: None,
                    config=config,
                )
                return ("created", instance_id, sub)
            except Exception as create_error:
                logger.info(f"Instance {instance_id} create failed ({create_error}), trying bind")
                try:
                    sub = await js.subscribe(
                        subject,
                        cb=lambda msg: None,
                        durable=consumer_name,
                        stream=STREAM_NAME,
                    )
                    return ("bound", instance_id, sub)
                except Exception as bind_error:
                    logger.error(f"Instance {instance_id} bind also failed: {bind_error}")
                    return ("error", instance_id, str(bind_error))

        tasks = [subscribe_instance(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        created_count = sum(1 for r in results if r[0] == "created")
        bound_count = sum(1 for r in results if r[0] == "bound")
        error_count = sum(1 for r in results if r[0] == "error")

        logger.info(f"Results: {created_count} created, {bound_count} bound, {error_count} errors")

        assert created_count == 1, f"Exactly 1 should create, got {created_count}"
        assert bound_count == 4, f"4 should bind, got {bound_count}"
        assert error_count == 0, f"No errors expected, got {error_count}"

        for status, _, sub in results:
            if status in ("created", "bound"):
                try:
                    await sub.unsubscribe()
                except Exception:
                    pass

    @pytest.mark.asyncio
    async def test_messages_load_balanced_between_instances(
        self, jetstream_with_workqueue: dict[str, Any]
    ) -> None:
        """Messages should be load-balanced between instances in queue group.

        With WORK_QUEUE retention and deliver_group, each message should
        go to exactly one instance.
        """
        js = jetstream_with_workqueue["js"]
        subject = f"{STREAM_NAME}.load_balance"
        consumer_name = "load_balance_consumer"

        messages: dict[int, list[str]] = {i: [] for i in range(3)}

        async def make_handler(instance_id: int) -> Any:
            async def handler(msg: Any) -> None:
                messages[instance_id].append(msg.data.decode())
                await msg.ack()

            return handler

        config = ConsumerConfig(
            durable_name=consumer_name,
            deliver_group=consumer_name,
        )
        sub1 = await js.subscribe(subject, cb=await make_handler(0), config=config)

        sub2 = await js.subscribe(
            subject,
            cb=await make_handler(1),
            durable=consumer_name,
            stream=STREAM_NAME,
        )

        sub3 = await js.subscribe(
            subject,
            cb=await make_handler(2),
            durable=consumer_name,
            stream=STREAM_NAME,
        )

        for i in range(30):
            await js.publish(subject, f"msg-{i}".encode())

        await asyncio.sleep(2.0)

        total = sum(len(msgs) for msgs in messages.values())
        logger.info(f"Total messages: {total}")
        for i, msgs in messages.items():
            logger.info(f"Instance {i}: {len(msgs)} messages")

        assert total == 30, f"All 30 messages should be delivered, got {total}"

        instances_with_messages = sum(1 for msgs in messages.values() if len(msgs) > 0)
        assert instances_with_messages >= 2, (
            f"At least 2 instances should receive messages, got {instances_with_messages}"
        )

        await sub1.unsubscribe()
        await sub2.unsubscribe()
        await sub3.unsubscribe()
