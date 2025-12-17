"""
Test to reproduce and diagnose JetStream concurrent subscription timeout issues.

This test creates multiple JetStream subscriptions concurrently to reproduce
the timeout issue described in nats-py #437.

Related issues:
- https://github.com/nats-io/nats.py/issues/437 (ephemeral consumer timeout)
- https://github.com/nats-io/nats.py/issues/603 (durable_name ignored)
"""

import asyncio
import logging
import os
import time
from typing import Any

import nats
import pytest
from nats.js.api import ConsumerConfig, RetentionPolicy, StorageType, StreamConfig

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration_messaging

STREAM_NAME = "JETSTREAM_TEST"


def get_nats_url() -> str:
    """Get NATS URL dynamically - must be called after testcontainers starts."""
    return os.environ.get("NATS_URL", "nats://localhost:4222")


@pytest.fixture
async def nats_client(db_session: Any) -> Any:
    """Create a fresh NATS connection for testing.

    Note: Depends on db_session to ensure testcontainers is started and
    environment variables (NATS_URL) are set before we try to connect.
    """
    nats_url = get_nats_url()
    logger.info(f"Connecting to NATS at: {nats_url}")
    nc = await nats.connect(nats_url, max_reconnect_attempts=3)
    js = nc.jetstream(timeout=30.0)

    # Create a test stream
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
    logger.info(f"Created stream {STREAM_NAME}")

    yield {"nc": nc, "js": js}

    # Cleanup
    try:
        await js.delete_stream(STREAM_NAME)
    except Exception:
        pass
    await nc.drain()
    await nc.close()


class TestJetStreamConcurrentSubscription:
    """Tests to diagnose JetStream concurrent subscription issues."""

    @pytest.mark.asyncio
    async def test_single_subscription_works(self, nats_client: dict[str, Any]) -> None:
        """Verify a single JetStream subscription works correctly."""
        js = nats_client["js"]
        received = []

        async def handler(msg: Any) -> None:
            received.append(msg.data.decode())
            await msg.ack()

        subject = f"{STREAM_NAME}.single"
        sub = await js.subscribe(
            subject,
            cb=handler,
            config=ConsumerConfig(max_deliver=3),
        )

        await js.publish(subject, b"test message")
        await asyncio.sleep(1)

        assert len(received) >= 1, f"Expected 1 message, got {len(received)}"
        assert received[0] == "test message"
        await sub.unsubscribe()
        logger.info("Single subscription test PASSED")

    @pytest.mark.asyncio
    async def test_sequential_subscriptions(self, nats_client: dict[str, Any]) -> None:
        """Create subscriptions sequentially - should always work."""
        js = nats_client["js"]
        subs = []
        results = {"success": 0, "timeout": 0, "error": 0}
        num_subscriptions = 8

        for i in range(num_subscriptions):
            subject = f"{STREAM_NAME}.seq.{i}"
            try:
                start = time.time()
                sub = await asyncio.wait_for(
                    js.subscribe(
                        subject,
                        cb=lambda msg: None,
                        config=ConsumerConfig(max_deliver=3),
                    ),
                    timeout=10.0,
                )
                elapsed = time.time() - start
                subs.append(sub)
                results["success"] += 1
                logger.info(f"Sequential sub {i}: SUCCESS in {elapsed:.2f}s")
            except TimeoutError:
                results["timeout"] += 1
                logger.error(f"Sequential sub {i}: TIMEOUT")
            except Exception as e:
                results["error"] += 1
                logger.error(f"Sequential sub {i}: ERROR - {e}")

        for sub in subs:
            await sub.unsubscribe()

        logger.info(f"Sequential results: {results}")
        assert results["success"] == num_subscriptions, (
            f"Expected all {num_subscriptions} to succeed, got {results}"
        )

    @pytest.mark.asyncio
    async def test_concurrent_subscriptions_reproduce_issue(
        self, nats_client: dict[str, Any]
    ) -> None:
        """
        Create subscriptions concurrently to reproduce timeout issue.

        This is the key test - concurrent consumer creation is known to
        cause timeouts in nats-py.
        """
        js = nats_client["js"]
        results = {"success": 0, "timeout": 0, "error": 0}
        subs = []
        num_subscriptions = 8

        async def create_subscription(idx: int) -> Any:
            subject = f"{STREAM_NAME}.concurrent.{idx}"
            try:
                start = time.time()
                sub = await asyncio.wait_for(
                    js.subscribe(
                        subject,
                        cb=lambda msg: None,
                        config=ConsumerConfig(max_deliver=3),
                    ),
                    timeout=10.0,
                )
                elapsed = time.time() - start
                logger.info(f"Concurrent sub {idx}: SUCCESS in {elapsed:.2f}s")
                return ("success", sub)
            except TimeoutError:
                logger.error(f"Concurrent sub {idx}: TIMEOUT")
                return ("timeout", None)
            except Exception as e:
                logger.error(f"Concurrent sub {idx}: ERROR - {e}")
                return ("error", None)

        # Create all subscriptions concurrently
        tasks = [create_subscription(i) for i in range(num_subscriptions)]
        outcomes = await asyncio.gather(*tasks)

        for status, sub in outcomes:
            results[status] += 1
            if sub:
                subs.append(sub)

        for sub in subs:
            await sub.unsubscribe()

        logger.info(f"Concurrent results: {results}")

        # Document the behavior - don't fail if this reproduces known issue
        if results["timeout"] > 0:
            logger.warning(
                f"REPRODUCED ISSUE: {results['timeout']} subscriptions timed out. "
                "This confirms nats-py #437 behavior."
            )

        # The test passes if at least some subscriptions work
        # (we're documenting behavior, not asserting it's fixed)
        assert results["success"] > 0, "At least some subscriptions should succeed"

    @pytest.mark.asyncio
    async def test_message_delivery_after_subscription(self, nats_client: dict[str, Any]) -> None:
        """Test if messages are delivered after JetStream subscription."""
        js = nats_client["js"]
        nc = nats_client["nc"]
        received_js = []
        received_core = []

        async def js_handler(msg: Any) -> None:
            received_js.append(msg.data.decode())
            await msg.ack()
            logger.info(f"JetStream handler received: {msg.data.decode()}")

        async def core_handler(msg: Any) -> None:
            received_core.append(msg.data.decode())
            logger.info(f"Core NATS handler received: {msg.data.decode()}")

        subject = f"{STREAM_NAME}.delivery"

        # Subscribe with JetStream
        try:
            js_sub = await asyncio.wait_for(
                js.subscribe(subject, cb=js_handler, config=ConsumerConfig(max_deliver=3)),
                timeout=10.0,
            )
            logger.info("JetStream subscription created")
        except TimeoutError:
            logger.error("JetStream subscription TIMED OUT - using core NATS only")
            js_sub = None

        # Also subscribe with core NATS (fallback)
        core_sub = await nc.subscribe(subject, cb=core_handler)
        logger.info("Core NATS subscription created")

        await asyncio.sleep(0.5)

        # Publish via JetStream
        await js.publish(subject, b"js_message")
        logger.info("Published via JetStream")

        # Also publish via core NATS
        await nc.publish(subject, b"core_message")
        logger.info("Published via core NATS")

        await asyncio.sleep(2)

        logger.info(f"JetStream received: {received_js}")
        logger.info(f"Core NATS received: {received_core}")

        # Core NATS should always work
        assert len(received_core) >= 1, "Core NATS should receive messages"

        # JetStream may or may not work depending on nats-py issues
        if js_sub and len(received_js) == 0:
            logger.warning(
                "JetStream subscription succeeded but handler didn't receive messages. "
                "This is the exact behavior described in the integration tests."
            )

        if js_sub:
            await js_sub.unsubscribe()
        await core_sub.unsubscribe()


class TestNATSServerInfo:
    """Gather diagnostic information about NATS server."""

    @pytest.mark.asyncio
    async def test_server_version(self, nats_client: dict[str, Any]) -> None:
        """Log NATS server version for diagnosis."""
        import re

        nc = nats_client["nc"]
        # nats-py uses connected_server_version for version string
        version = nc.connected_server_version

        logger.info("=" * 60)
        logger.info("NATS SERVER DIAGNOSTICS")
        logger.info("=" * 60)
        logger.info(f"Version: {version}")
        logger.info(f"Connected URL: {nc.connected_url}")
        logger.info(f"Client ID: {nc.client_id}")
        logger.info("=" * 60)

        # Log for later analysis
        version_str = str(version)
        logger.info(f"Current NATS server version: {version_str}")

        # Check if we're on a version known to have issues
        match = re.search(r"(\d+)\.(\d+)", version_str)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            if major == 2 and minor == 9:
                logger.warning(
                    f"NATS {version_str} - Version 2.9.15 known to have consumer timeout issues. "
                    "Consider upgrading to 2.10+ or 2.12+"
                )
            elif major == 2 and minor >= 12:
                logger.info(f"NATS {version_str} - Latest stable version, good!")

        assert version is not None
