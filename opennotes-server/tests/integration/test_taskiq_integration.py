"""
Integration tests for taskiq with NATS broker and Redis result backend.

TDD RED PHASE: These tests are written BEFORE the implementation exists.
They will fail on import because src.tasks.broker and src.tasks.example
do not exist yet. This defines the expected API for the implementation.

Expected modules to be created:
- src/tasks/broker.py - Configures NATS broker with Redis result backend
- src/tasks/example.py - Example task for testing

Expected API:
    from src.tasks.broker import broker
    from src.tasks.example import example_task

    await broker.startup()
    task = await example_task.kiq("message")
    result = await task.wait_result(timeout=10)
    assert result.return_value == "Processed: message"
    await broker.shutdown()
"""

import asyncio
import logging
import os
from typing import Any

import pytest

from src.cache.redis_client import redis_client
from src.events.nats_client import nats_client

pytestmark = pytest.mark.integration_messaging

logger = logging.getLogger(__name__)


@pytest.fixture
async def setup_nats_redis(db_session: Any) -> Any:
    """
    Setup real NATS and Redis connections for taskiq tests.

    This fixture connects to real NATS and Redis services
    provided by testcontainers via the test_services fixture.
    """
    os.environ["INTEGRATION_TESTS"] = "true"

    logger.info("Setting up Redis and NATS for taskiq integration tests...")

    try:
        redis_url = os.environ.get("REDIS_URL")
        await redis_client.connect(redis_url=redis_url)
        logger.info(f"Redis connected successfully: {redis_url}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    try:
        await nats_client.connect()
        logger.info(f"NATS connected successfully: {os.environ.get('NATS_URL')}")
    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        raise

    yield

    logger.info("Tearing down messaging services...")

    if redis_client.client:
        try:
            await redis_client.client.flushdb()
        except Exception as e:
            logger.warning(f"Error flushing Redis: {e}")

    await nats_client.disconnect()
    await redis_client.disconnect()
    logger.info("Messaging services teardown complete")


@pytest.fixture
async def setup_taskiq_broker(setup_nats_redis: Any) -> Any:
    """
    Setup taskiq broker with real NATS and Redis services.

    This fixture depends on setup_nats_redis which provides
    real NATS and Redis connections via testcontainers.

    Imports are done inside the fixture to allow tests to be collected
    even when the modules don't exist yet (TDD RED phase).
    """
    from src.tasks.broker import broker

    logger.info("Starting taskiq broker...")
    await broker.startup()
    logger.info("Taskiq broker started successfully")

    yield broker

    logger.info("Shutting down taskiq broker...")
    await broker.shutdown()
    logger.info("Taskiq broker shutdown complete")


class TestBrokerLifecycle:
    """Test taskiq broker startup and shutdown with NATS."""

    @pytest.mark.asyncio
    async def test_broker_startup_shutdown(self, setup_nats_redis: Any) -> None:
        """
        Verify broker can start and stop cleanly.

        This test verifies:
        1. Broker can be imported from src.tasks.broker
        2. Broker startup() succeeds with real NATS connection
        3. Broker shutdown() completes without errors
        """
        from src.tasks.broker import broker

        await broker.startup()
        logger.info("Broker started successfully")

        await broker.shutdown()
        logger.info("Broker shutdown successfully")

    @pytest.mark.asyncio
    async def test_broker_double_startup_is_safe(self, setup_nats_redis: Any) -> None:
        """
        Verify calling startup() twice doesn't cause issues.

        Brokers should handle idempotent startup gracefully.
        """
        from src.tasks.broker import broker

        await broker.startup()
        await broker.startup()

        await broker.shutdown()


class TestTaskDispatch:
    """Test task dispatch and result retrieval with real NATS/Redis."""

    @pytest.mark.asyncio
    async def test_task_dispatch_and_result(self, setup_taskiq_broker: Any) -> None:
        """
        Dispatch task with .kiq(), await result with .wait_result().

        This test verifies the core taskiq workflow:
        1. Task can be dispatched via .kiq()
        2. Result can be awaited via .wait_result(timeout=10)
        3. Return value is accessible and correct
        4. Result indicates no error occurred
        """
        from src.tasks.example import example_task

        task = await example_task.kiq("test message")
        logger.info(f"Task dispatched: {task.task_id}")

        result = await task.wait_result(timeout=10)
        logger.info(f"Task result received: {result}")

        assert result.return_value == "Processed: test message"
        assert not result.is_err
        logger.info("Task dispatch and result test passed")

    @pytest.mark.asyncio
    async def test_task_with_parameters(self, setup_taskiq_broker: Any) -> None:
        """
        Task with parameters returns correct processed result.

        This test verifies tasks can accept various parameter types
        and process them correctly.
        """
        from src.tasks.example import example_task

        test_cases = [
            ("hello world", "Processed: hello world"),
            ("", "Processed: "),
            ("special chars !@#$%", "Processed: special chars !@#$%"),
            ("unicode \u65e5\u672c\u8a9e", "Processed: unicode \u65e5\u672c\u8a9e"),
        ]

        for input_msg, expected_output in test_cases:
            task = await example_task.kiq(input_msg)
            result = await task.wait_result(timeout=10)

            assert result.return_value == expected_output, (
                f"Expected '{expected_output}', got '{result.return_value}'"
            )
            assert not result.is_err
            logger.info(f"Parameter test passed for input: '{input_msg}'")

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tasks(self, setup_taskiq_broker: Any) -> None:
        """
        Multiple tasks can be dispatched and completed concurrently.

        This test verifies:
        1. Multiple tasks can be dispatched simultaneously
        2. All tasks complete successfully
        3. Results are correctly matched to their inputs
        """
        from src.tasks.example import example_task

        num_tasks = 5
        messages = [f"concurrent message {i}" for i in range(num_tasks)]

        tasks = [await example_task.kiq(msg) for msg in messages]
        logger.info(f"Dispatched {num_tasks} concurrent tasks")

        results = await asyncio.gather(*[t.wait_result(timeout=15) for t in tasks])

        for i, result in enumerate(results):
            expected = f"Processed: concurrent message {i}"
            assert result.return_value == expected
            assert not result.is_err

        logger.info(f"All {num_tasks} concurrent tasks completed successfully")


class TestResultBackend:
    """Test Redis result backend functionality."""

    @pytest.mark.asyncio
    async def test_result_stored_in_redis(self, setup_taskiq_broker: Any) -> None:
        """
        Verify result is retrievable from Redis backend.

        This test verifies:
        1. Task result is persisted to Redis
        2. Result can be retrieved after task completion
        3. Result data integrity is maintained
        """
        from src.tasks.example import example_task

        task = await example_task.kiq("redis storage test")
        task_id = task.task_id
        logger.info(f"Task dispatched with ID: {task_id}")

        result = await task.wait_result(timeout=10)
        assert result.return_value == "Processed: redis storage test"
        assert not result.is_err

        logger.info(f"Result verified for task {task_id}")

    @pytest.mark.asyncio
    async def test_result_timeout_behavior(self, setup_taskiq_broker: Any) -> None:
        """
        Verify wait_result respects timeout parameter.

        If a task takes longer than the timeout, wait_result should
        raise an appropriate exception or return a timeout indicator.
        """
        from src.tasks.example import slow_task

        task = await slow_task.kiq(delay_seconds=0.5)
        logger.info(f"Slow task dispatched: {task.task_id}")

        result = await task.wait_result(timeout=10)
        assert not result.is_err
        logger.info("Slow task completed within timeout")


class TestErrorHandling:
    """Test error handling in task execution."""

    @pytest.mark.asyncio
    async def test_task_exception_captured(self, setup_taskiq_broker: Any) -> None:
        """
        Task exceptions are captured and available in result.

        When a task raises an exception:
        1. result.is_err should be True
        2. result.error should contain exception info
        """
        from src.tasks.example import failing_task

        task = await failing_task.kiq()
        logger.info(f"Failing task dispatched: {task.task_id}")

        result = await task.wait_result(timeout=10)

        assert result.is_err, "Expected result.is_err to be True for failing task"
        assert result.error is not None, "Expected error information in result"
        logger.info(f"Task error captured: {result.error}")


class TestBrokerConfiguration:
    """Test broker configuration with environment variables."""

    @pytest.mark.asyncio
    async def test_broker_uses_environment_urls(self, setup_nats_redis: Any) -> None:
        """
        Verify broker uses NATS_URL and REDIS_URL from environment.

        The broker should read connection URLs from environment variables
        to support different deployment configurations.
        """
        nats_url = os.environ.get("NATS_URL")
        redis_url = os.environ.get("REDIS_URL")

        assert nats_url is not None, "NATS_URL should be set by test fixtures"
        assert redis_url is not None, "REDIS_URL should be set by test fixtures"

        from src.tasks.broker import broker

        await broker.startup()

        from src.tasks.example import example_task

        task = await example_task.kiq("config test")
        result = await task.wait_result(timeout=10)

        assert result.return_value == "Processed: config test"
        assert not result.is_err

        await broker.shutdown()
        logger.info("Broker correctly used environment configuration")
