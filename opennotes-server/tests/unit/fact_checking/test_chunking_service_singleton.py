"""Unit tests for ChunkingService singleton pattern and semaphore gating.

Task: TASK-1058.02 - Implement NeuralChunker singleton with semaphore-gated access
Task: TASK-1058.11 - Thread-safety tests for _get_chunking_semaphore()

These tests verify:
1. get_chunking_service() returns the same instance (singleton pattern)
2. use_chunking_service() gates concurrent access with a semaphore
3. reset_chunking_service() clears the singleton for testing
4. _get_chunking_semaphore() is thread-safe with double-checked locking
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
class TestChunkingServiceSemaphore:
    """Test use_chunking_service() semaphore gating for concurrent access."""

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
class TestChunkingSemaphoreThreadSafety:
    """Test _get_chunking_semaphore() thread-safety."""

    def setup_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def teardown_method(self):
        from src.fact_checking.chunking_service import reset_chunking_service

        reset_chunking_service()

    def test_concurrent_semaphore_creation_returns_same_instance(self):
        """Concurrent calls to _get_chunking_semaphore() return same instance."""
        from src.fact_checking.chunking_service import _get_chunking_semaphore

        semaphores: list[asyncio.Semaphore] = []
        barrier = threading.Barrier(10)

        def get_semaphore():
            barrier.wait()
            sem = _get_chunking_semaphore()
            semaphores.append(sem)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_semaphore) for _ in range(10)]
            for f in futures:
                f.result()

        assert len(semaphores) == 10
        assert all(s is semaphores[0] for s in semaphores)
