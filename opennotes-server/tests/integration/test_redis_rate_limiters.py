"""Integration tests for redis-rate-limiters library.

Verifies the AsyncSemaphore works correctly with our Redis setup.
"""

import asyncio

import pytest
from limiters import AsyncSemaphore
from redis.asyncio import Redis


@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    client = Redis.from_url("redis://localhost:6379")
    yield client
    await client.aclose()


class TestAsyncSemaphoreIntegration:
    """Integration tests for AsyncSemaphore."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self, redis_client):
        """Verify semaphore limits concurrent access."""
        semaphore = AsyncSemaphore(
            name="test:concurrency",
            capacity=2,
            max_sleep=5,
            expiry=30,
            connection=redis_client,
        )

        concurrent_count = [0]
        max_concurrent = [0]

        async def work():
            async with semaphore:
                concurrent_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
                await asyncio.sleep(0.1)
                concurrent_count[0] -= 1

        await asyncio.gather(*[work() for _ in range(10)])

        assert max_concurrent[0] == 2, f"Expected max 2 concurrent, got {max_concurrent[0]}"

    @pytest.mark.asyncio
    async def test_semaphore_releases_on_exception(self, redis_client):
        """Verify semaphore is released when exception occurs."""
        semaphore = AsyncSemaphore(
            name="test:exception",
            capacity=1,
            max_sleep=2,
            expiry=30,
            connection=redis_client,
        )

        with pytest.raises(ValueError, match="test error"):
            async with semaphore:
                raise ValueError("test error")

        acquired = False
        async with semaphore:
            acquired = True

        assert acquired, "Semaphore not released after exception"

    @pytest.mark.asyncio
    async def test_different_names_are_independent(self, redis_client):
        """Verify different semaphore names don't block each other."""
        sem_a = AsyncSemaphore(
            name="test:name_a",
            capacity=1,
            max_sleep=1,
            expiry=30,
            connection=redis_client,
        )
        sem_b = AsyncSemaphore(
            name="test:name_b",
            capacity=1,
            max_sleep=1,
            expiry=30,
            connection=redis_client,
        )

        results = []

        async def use_a():
            async with sem_a:
                results.append("a_start")
                await asyncio.sleep(0.2)
                results.append("a_end")

        async def use_b():
            async with sem_b:
                results.append("b_start")
                await asyncio.sleep(0.1)
                results.append("b_end")

        await asyncio.gather(use_a(), use_b())

        assert results[0] in ("a_start", "b_start")
        assert results[1] in ("a_start", "b_start")
