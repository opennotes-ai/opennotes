"""Unit tests for ChunkingService singleton pattern and lock-gated access.

Task: TASK-1058.02 - Implement NeuralChunker singleton with semaphore-gated access
Task: TASK-1058.11 - Thread-safety tests for _get_chunking_semaphore()
Task: TASK-1058.18 - Fix async/sync lock coordination with unified threading.Lock
Task: TASK-1058.29 - Add async usage tests for thread-safety

These tests verify:
1. get_chunking_service() returns the same instance (singleton pattern)
2. use_chunking_service() gates concurrent async access with the unified lock
3. use_chunking_service_sync() gates concurrent sync access with the unified lock
4. Async and sync access are mutually exclusive (unified _access_lock)
5. reset_chunking_service() clears the singleton for testing
6. Rapid acquire/release cycles don't cause race conditions
7. Concurrent async/sync singleton access returns same instance
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestChunkingServiceSingleton:
    """Test get_chunking_service() singleton pattern."""

    def setup_method(self):
        """Reset singleton state before each test."""
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def teardown_method(self):
        """Clean up singleton state after each test."""
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_get_chunking_service_returns_singleton(self, mock_neural_chunker):
        """Test get_chunking_service() returns the same instance on subsequent calls."""
        from src.fact_checking.chunking_service import get_chunking_service

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        service1 = get_chunking_service()
        service2 = get_chunking_service()

        assert service1 is service2

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_get_chunking_service_initializes_once(self, mock_neural_chunker):
        """Test NeuralChunker is only initialized once across multiple get_chunking_service calls."""
        from src.fact_checking.chunking_service import get_chunking_service

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        service1 = get_chunking_service()
        _ = service1.chunker

        service2 = get_chunking_service()
        _ = service2.chunker

        service3 = get_chunking_service()
        _ = service3.chunker

        mock_neural_chunker.assert_called_once()

    def test_reset_chunking_service_clears_singleton(self):
        """Test reset_chunking_service() allows creating a new instance."""
        from src.fact_checking.chunking_service import (
            get_chunking_service,
            reset_chunking_service,
        )

        service1 = get_chunking_service()
        reset_chunking_service()
        service2 = get_chunking_service()

        assert service1 is not service2


@pytest.mark.unit
@pytest.mark.asyncio
class TestChunkingServiceAsyncLock:
    """Test use_chunking_service() lock gating for concurrent async access."""

    def setup_method(self):
        """Reset singleton state before each test."""
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def teardown_method(self):
        """Clean up singleton state after each test."""
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_use_chunking_service_yields_service(self, mock_neural_chunker):
        """Test use_chunking_service() yields the singleton service."""
        from src.fact_checking.chunking_service import (
            get_chunking_service,
            use_chunking_service,
        )

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        async with use_chunking_service() as service:
            singleton = get_chunking_service()
            assert service is singleton

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_use_chunking_service_limits_concurrency(self, mock_neural_chunker):
        """Test use_chunking_service() only allows one concurrent access."""
        from src.fact_checking.chunking_service import use_chunking_service

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        execution_order = []
        lock_acquired_times = []

        async def worker(worker_id: int, hold_duration: float = 0.1):
            async with use_chunking_service():
                lock_acquired_times.append(time.monotonic())
                execution_order.append(f"start_{worker_id}")
                await asyncio.sleep(hold_duration)
                execution_order.append(f"end_{worker_id}")

        await asyncio.gather(
            worker(1, hold_duration=0.05),
            worker(2, hold_duration=0.05),
        )

        assert len(lock_acquired_times) == 2
        time_gap = lock_acquired_times[1] - lock_acquired_times[0]
        assert time_gap >= 0.04, f"Expected sequential execution, got gap of {time_gap}s"

        first_end_idx = min(execution_order.index("end_1"), execution_order.index("end_2"))
        second_start_idx = max(execution_order.index("start_1"), execution_order.index("start_2"))
        assert first_end_idx < second_start_idx, (
            f"Expected sequential execution, got order: {execution_order}"
        )

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_use_chunking_service_releases_on_exception(self, mock_neural_chunker):
        """Test semaphore is released when exception occurs inside context."""
        from src.fact_checking.chunking_service import use_chunking_service

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        try:
            async with use_chunking_service():
                raise ValueError("Test exception")
        except ValueError:
            pass

        acquired = False
        async with use_chunking_service():
            acquired = True

        assert acquired, "Semaphore was not released after exception"

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_use_chunking_service_preserves_singleton(self, mock_neural_chunker):
        """Test use_chunking_service() returns the same service instance each time."""
        from src.fact_checking.chunking_service import use_chunking_service

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        services = []
        for _ in range(3):
            async with use_chunking_service() as service:
                services.append(service)

        assert all(s is services[0] for s in services)


@pytest.mark.unit
class TestChunkingServiceSyncWrapper:
    """Test use_chunking_service_sync() for use in synchronous DBOS workflows."""

    def setup_method(self):
        """Reset singleton state before each test."""
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def teardown_method(self):
        """Clean up singleton state after each test."""
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_use_chunking_service_sync_yields_service(self, mock_neural_chunker):
        """Test use_chunking_service_sync() yields the singleton service."""
        from src.fact_checking.chunking_service import (
            get_chunking_service,
            use_chunking_service_sync,
        )

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        with use_chunking_service_sync() as service:
            singleton = get_chunking_service()
            assert service is singleton

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_use_chunking_service_sync_returns_same_instance(self, mock_neural_chunker):
        """Test use_chunking_service_sync() returns the same service instance."""
        from src.fact_checking.chunking_service import use_chunking_service_sync

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        services = []
        for _ in range(3):
            with use_chunking_service_sync() as service:
                services.append(service)

        assert all(s is services[0] for s in services)


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncSyncMutualExclusion:
    """Test unified lock provides mutual exclusion between async and sync access.

    Task: TASK-1058.18 - These tests verify the unified _access_lock prevents
    concurrent access from both async (use_chunking_service) and sync
    (use_chunking_service_sync) code paths.
    """

    def setup_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def teardown_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_async_sync_mutual_exclusion(self, mock_neural_chunker):
        """Sync caller blocks while async caller holds the lock."""
        from src.fact_checking.chunking_service import (
            use_chunking_service,
            use_chunking_service_sync,
        )

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        events: list[str] = []
        sync_started = threading.Event()
        async_released = asyncio.Event()

        async def async_holder():
            async with use_chunking_service():
                events.append("async_acquired")
                sync_started.set()
                await asyncio.sleep(0.1)
                events.append("async_releasing")
            async_released.set()

        def sync_waiter():
            sync_started.wait()
            events.append("sync_waiting")
            with use_chunking_service_sync():
                events.append("sync_acquired")

        loop = asyncio.get_running_loop()
        async_task = asyncio.create_task(async_holder())
        sync_future = loop.run_in_executor(None, sync_waiter)

        await asyncio.gather(async_task, sync_future)

        assert events.index("async_acquired") < events.index("sync_waiting")
        assert events.index("async_releasing") < events.index("sync_acquired")

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_sync_async_mutual_exclusion(self, mock_neural_chunker):
        """Async caller waits while sync caller holds the lock."""
        from src.fact_checking.chunking_service import (
            use_chunking_service,
            use_chunking_service_sync,
        )

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        events: list[str] = []
        sync_acquired = threading.Event()
        sync_done = threading.Event()

        def sync_holder():
            with use_chunking_service_sync():
                events.append("sync_acquired")
                sync_acquired.set()
                time.sleep(0.1)
                events.append("sync_releasing")
            sync_done.set()

        async def async_waiter():
            sync_acquired.wait()
            events.append("async_waiting")
            async with use_chunking_service():
                events.append("async_acquired")

        loop = asyncio.get_running_loop()
        sync_future = loop.run_in_executor(None, sync_holder)
        await asyncio.sleep(0.01)
        async_task = asyncio.create_task(async_waiter())

        await asyncio.gather(async_task, sync_future)

        assert events.index("sync_acquired") < events.index("async_waiting")
        assert events.index("sync_releasing") < events.index("async_acquired")

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_concurrent_async_serialization(self, mock_neural_chunker):
        """10 concurrent async tasks are serialized (no overlap)."""
        from src.fact_checking.chunking_service import use_chunking_service

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        active_count = 0
        max_concurrent = 0
        events: list[tuple[str, int, float]] = []
        lock = threading.Lock()

        async def worker(worker_id: int):
            nonlocal active_count, max_concurrent

            async with use_chunking_service():
                with lock:
                    active_count += 1
                    max_concurrent = max(max_concurrent, active_count)
                    events.append(("start", worker_id, time.monotonic()))

                await asyncio.sleep(0.02)

                with lock:
                    events.append(("end", worker_id, time.monotonic()))
                    active_count -= 1

        tasks = [asyncio.create_task(worker(i)) for i in range(10)]
        await asyncio.gather(*tasks)

        assert max_concurrent == 1, f"Expected max 1 concurrent, got {max_concurrent}"
        assert len(events) == 20

        for i in range(0, len(events) - 2, 2):
            assert events[i][0] == "start"
            assert events[i + 1][0] == "end"
            if i + 2 < len(events):
                assert events[i + 1][2] <= events[i + 2][2], (
                    f"Task {events[i + 2][1]} started before task {events[i][1]} ended"
                )


@pytest.mark.unit
@pytest.mark.asyncio
class TestChunkingServiceAsyncUsagePatterns:
    """Tests for async usage patterns of ChunkingService with unified lock.

    Task: TASK-1058.29 - Add async usage tests for thread-safety

    These tests verify that the async context manager (use_chunking_service)
    correctly serializes access when many concurrent async tasks contend for
    the lock. The lock is acquired via run_in_executor to avoid blocking the
    event loop.
    """

    def setup_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def teardown_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_lock_serializes_many_concurrent_tasks(self, mock_neural_chunker):
        """Test lock serializes access with many concurrent async tasks."""
        from src.fact_checking.chunking_service import use_chunking_service

        mock_neural_chunker.return_value = MagicMock()

        concurrent_count = 0
        max_concurrent = 0

        async def worker(worker_id: int):
            nonlocal concurrent_count, max_concurrent
            async with use_chunking_service():
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
                await asyncio.sleep(0.01)
                concurrent_count -= 1

        await asyncio.gather(*[worker(i) for i in range(10)])
        assert max_concurrent == 1, f"Expected max 1 concurrent access, got {max_concurrent}"

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_lock_prevents_race_conditions(self, mock_neural_chunker):
        """Test rapid acquire/release cycles don't cause race conditions."""
        from src.fact_checking.chunking_service import use_chunking_service

        mock_neural_chunker.return_value = MagicMock()

        access_count = 0
        errors: list[str] = []

        async def rapid_access(worker_id: int):
            nonlocal access_count
            for iteration in range(5):
                async with use_chunking_service():
                    prev = access_count
                    access_count += 1
                    await asyncio.sleep(0)
                    if access_count != prev + 1:
                        errors.append(f"Race: worker {worker_id}, iteration {iteration}")
                    access_count -= 1

        await asyncio.gather(*[rapid_access(i) for i in range(5)])
        assert not errors, f"Race conditions detected: {errors}"

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_concurrent_async_singleton_creation_returns_same_instance(
        self, mock_neural_chunker
    ):
        """Concurrent async tasks calling get_chunking_service() return same instance."""
        from src.fact_checking.chunking_service import get_chunking_service

        mock_neural_chunker.return_value = MagicMock()

        services: list = []
        start_event = asyncio.Event()

        async def get_service():
            await start_event.wait()
            svc = get_chunking_service()
            services.append(svc)

        tasks = [asyncio.create_task(get_service()) for _ in range(10)]
        start_event.set()
        await asyncio.gather(*tasks)

        assert len(services) == 10
        assert all(s is services[0] for s in services)


@pytest.mark.unit
class TestChunkingServiceLockThreadSafety:
    """Test unified _access_lock thread-safety for concurrent sync access.

    Task: TASK-1058.29 - Add async usage tests for thread-safety

    The unified threading.Lock (_access_lock) provides mutual exclusion between
    both async and sync callers. These tests verify thread-safe access patterns.
    """

    def setup_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def teardown_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_concurrent_sync_access_is_serialized(self, mock_neural_chunker):
        """Concurrent sync access via threads is serialized by _access_lock."""
        from src.fact_checking.chunking_service import use_chunking_service_sync

        mock_neural_chunker.return_value = MagicMock()

        concurrent_count = 0
        max_concurrent = 0
        lock = threading.Lock()
        barrier = threading.Barrier(10)

        def worker():
            nonlocal concurrent_count, max_concurrent
            barrier.wait()
            with use_chunking_service_sync():
                with lock:
                    concurrent_count += 1
                    max_concurrent = max(max_concurrent, concurrent_count)
                time.sleep(0.01)
                with lock:
                    concurrent_count -= 1

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker) for _ in range(10)]
            for f in futures:
                f.result()

        assert max_concurrent == 1, f"Expected max 1 concurrent access, got {max_concurrent}"


@pytest.mark.unit
@pytest.mark.asyncio
class TestMixedAsyncSyncAccessPatterns:
    """Tests for mixed async/sync access patterns using the unified lock.

    Task: TASK-1058.29 - Add async usage tests for thread-safety

    The unified _access_lock ensures mutual exclusion between async callers
    (use_chunking_service) and sync callers (use_chunking_service_sync).
    """

    def setup_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def teardown_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    @patch("chonkie.chunker.neural.NeuralChunker")
    async def test_async_and_sync_access_are_mutually_exclusive(self, mock_neural_chunker):
        """Test async and sync callers don't access the service simultaneously."""
        from src.fact_checking.chunking_service import (
            use_chunking_service,
            use_chunking_service_sync,
        )

        mock_neural_chunker.return_value = MagicMock()

        concurrent_count = 0
        max_concurrent = 0
        count_lock = threading.Lock()

        async def async_worker():
            nonlocal concurrent_count, max_concurrent
            async with use_chunking_service():
                with count_lock:
                    concurrent_count += 1
                    max_concurrent = max(max_concurrent, concurrent_count)
                await asyncio.sleep(0.01)
                with count_lock:
                    concurrent_count -= 1

        def sync_worker():
            nonlocal concurrent_count, max_concurrent
            with use_chunking_service_sync():
                with count_lock:
                    concurrent_count += 1
                    max_concurrent = max(max_concurrent, concurrent_count)
                time.sleep(0.01)
                with count_lock:
                    concurrent_count -= 1

        loop = asyncio.get_running_loop()
        async_tasks = [async_worker() for _ in range(5)]
        sync_futures = [loop.run_in_executor(None, sync_worker) for _ in range(5)]

        await asyncio.gather(*async_tasks, *sync_futures)
        assert max_concurrent == 1, f"Expected max 1 concurrent access, got {max_concurrent}"
