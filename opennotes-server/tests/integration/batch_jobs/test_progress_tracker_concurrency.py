"""
Integration tests for BatchJobProgressTracker concurrent operations.

Tests verify that atomic HINCRBY operations prevent race conditions
when multiple coroutines update progress simultaneously.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from src.batch_jobs.progress_tracker import BatchJobProgressTracker
from src.cache.redis_client import RedisClient
from src.config import settings


@pytest.fixture
async def redis_client(test_services) -> AsyncIterator[RedisClient]:
    """Create and connect a Redis client using testcontainers Redis.

    Depends on test_services fixture which sets up testcontainers
    and updates settings.REDIS_URL to point to the container.
    """
    from src.circuit_breaker import circuit_breaker_registry

    # Set INTEGRATION_TESTS to bypass the test-mode skip in RedisClient.connect()
    old_value = os.environ.get("INTEGRATION_TESTS")
    os.environ["INTEGRATION_TESTS"] = "true"
    try:
        # Create client first (this registers the circuit breaker)
        client = RedisClient()
        # Reset circuit breaker AFTER client creation (ensures breaker is registered)
        # but BEFORE connect (so connection isn't blocked by tripped breaker)
        await circuit_breaker_registry.reset("redis")
        # Use os.environ directly because test_services does importlib.reload(config),
        # which creates a new Settings singleton. The module-level 'settings' import
        # still references the OLD singleton with the default REDIS_URL.
        redis_url = os.environ.get("REDIS_URL", settings.REDIS_URL)
        await client.connect(redis_url)
        yield client
        await client.disconnect()
    finally:
        if old_value is None:
            os.environ.pop("INTEGRATION_TESTS", None)
        else:
            os.environ["INTEGRATION_TESTS"] = old_value
        # Reset circuit breaker after test to avoid polluting next test
        await circuit_breaker_registry.reset("redis")


@pytest.fixture
async def tracker(redis_client: RedisClient) -> BatchJobProgressTracker:
    """Create a progress tracker with the test Redis client."""
    return BatchJobProgressTracker(redis_client)


@pytest.mark.integration
async def test_concurrent_progress_increments(tracker: BatchJobProgressTracker) -> None:
    """
    Test that 100 concurrent increment_processed operations all succeed atomically.

    Without atomic HINCRBY, race conditions would cause lost updates when multiple
    coroutines read-modify-write the same counter.

    Uses a semaphore to bound concurrency and avoid exhausting the testcontainers
    Redis connection pool (each update_progress call makes multiple Redis operations).
    """
    job_id = uuid4()
    num_concurrent_updates = 100
    sem = asyncio.Semaphore(10)

    await tracker.start_tracking(job_id)

    async def increment_once() -> None:
        async with sem:
            await tracker.update_progress(job_id, increment_processed=True)

    tasks = [asyncio.create_task(increment_once()) for _ in range(num_concurrent_updates)]
    await asyncio.gather(*tasks)

    progress = await tracker.get_progress(job_id)
    assert progress is not None
    assert progress.processed_count == num_concurrent_updates, (
        f"Expected {num_concurrent_updates} but got {progress.processed_count}. "
        "This indicates a race condition in progress updates."
    )

    await tracker.stop_tracking(job_id)


@pytest.mark.integration
async def test_concurrent_error_increments(tracker: BatchJobProgressTracker) -> None:
    """Test that concurrent error increments are atomic."""
    job_id = uuid4()
    num_concurrent_updates = 50
    sem = asyncio.Semaphore(10)

    await tracker.start_tracking(job_id)

    async def increment_error() -> None:
        async with sem:
            await tracker.update_progress(job_id, increment_errors=True)

    tasks = [asyncio.create_task(increment_error()) for _ in range(num_concurrent_updates)]
    await asyncio.gather(*tasks)

    progress = await tracker.get_progress(job_id)
    assert progress is not None
    assert progress.error_count == num_concurrent_updates

    await tracker.stop_tracking(job_id)


@pytest.mark.integration
async def test_concurrent_mixed_increments(tracker: BatchJobProgressTracker) -> None:
    """Test concurrent updates with both processed and error increments."""
    job_id = uuid4()
    num_processed = 75
    num_errors = 25
    sem = asyncio.Semaphore(10)

    await tracker.start_tracking(job_id)

    async def increment_processed() -> None:
        async with sem:
            await tracker.update_progress(job_id, increment_processed=True)

    async def increment_error() -> None:
        async with sem:
            await tracker.update_progress(job_id, increment_errors=True)

    processed_tasks = [asyncio.create_task(increment_processed()) for _ in range(num_processed)]
    error_tasks = [asyncio.create_task(increment_error()) for _ in range(num_errors)]

    await asyncio.gather(*processed_tasks, *error_tasks)

    progress = await tracker.get_progress(job_id)
    assert progress is not None
    assert progress.processed_count == num_processed
    assert progress.error_count == num_errors

    await tracker.stop_tracking(job_id)


@pytest.mark.integration
async def test_absolute_count_overrides_increment(tracker: BatchJobProgressTracker) -> None:
    """Test that absolute count values override increment behavior."""
    job_id = uuid4()

    await tracker.start_tracking(job_id)

    await tracker.update_progress(job_id, increment_processed=True)
    await tracker.update_progress(job_id, increment_processed=True)
    progress = await tracker.get_progress(job_id)
    assert progress is not None
    assert progress.processed_count == 2

    await tracker.update_progress(job_id, processed_count=100)
    progress = await tracker.get_progress(job_id)
    assert progress is not None
    assert progress.processed_count == 100

    await tracker.stop_tracking(job_id)


@pytest.mark.integration
async def test_current_item_update_during_concurrent_increments(
    tracker: BatchJobProgressTracker,
) -> None:
    """Test that current_item updates work correctly alongside concurrent increments."""
    job_id = uuid4()

    await tracker.start_tracking(job_id)

    async def increment_with_item(item: str) -> None:
        await tracker.update_progress(job_id, increment_processed=True, current_item=item)

    tasks = [asyncio.create_task(increment_with_item(f"item_{i}")) for i in range(10)]
    await asyncio.gather(*tasks)

    progress = await tracker.get_progress(job_id)
    assert progress is not None
    assert progress.processed_count == 10
    assert progress.current_item is not None
    assert progress.current_item.startswith("item_")

    await tracker.stop_tracking(job_id)
