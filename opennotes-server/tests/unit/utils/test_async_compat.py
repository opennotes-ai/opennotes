"""Tests for async_compat utilities."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from src.utils.async_compat import (
    _executor,
    _thread_local_loops,
    cleanup_event_loops,
    run_sync,
    shutdown,
)


class TestRunSync:
    """Tests for the run_sync utility function."""

    def test_run_sync_from_sync_context(self) -> None:
        """Test run_sync works from a synchronous context with no running loop."""

        async def async_add(a: int, b: int) -> int:
            return a + b

        result = run_sync(async_add(2, 3))
        assert result == 5

    def test_run_sync_from_async_context(self) -> None:
        """Test run_sync works from within an async context (running loop)."""

        async def async_multiply(a: int, b: int) -> int:
            return a * b

        async def outer() -> int:
            return run_sync(async_multiply(4, 5))

        result = asyncio.run(outer())
        assert result == 20

    def test_run_sync_reuses_event_loop(self) -> None:
        """Test that run_sync reuses the thread-local event loop for efficiency."""
        loop_ids: list[int] = []

        async def capture_loop_id() -> int:
            loop = asyncio.get_running_loop()
            return id(loop)

        loop_ids.append(run_sync(capture_loop_id()))
        loop_ids.append(run_sync(capture_loop_id()))
        loop_ids.append(run_sync(capture_loop_id()))

        assert len(set(loop_ids)) == 1, "Loop should be reused across calls"

    def test_run_sync_handles_exceptions(self) -> None:
        """Test that exceptions from coroutines are properly propagated."""

        async def async_fail() -> None:
            raise ValueError("Expected test error")

        with pytest.raises(ValueError, match="Expected test error"):
            run_sync(async_fail())

    def test_run_sync_handles_exceptions_in_async_context(self) -> None:
        """Test exceptions propagate when called from async context."""

        async def async_fail() -> None:
            raise RuntimeError("Expected runtime error")

        async def outer() -> None:
            run_sync(async_fail())

        with pytest.raises(RuntimeError, match="Expected runtime error"):
            asyncio.run(outer())

    def test_run_sync_returns_complex_types(self) -> None:
        """Test run_sync works with complex return types."""

        async def async_complex() -> dict[str, Any]:
            return {"nested": {"list": [1, 2, 3], "value": "test"}}

        result = run_sync(async_complex())
        assert result == {"nested": {"list": [1, 2, 3], "value": "test"}}

    def test_run_sync_in_multiple_threads(self) -> None:
        """Test run_sync works correctly in multiple threads."""
        results: list[int] = []
        errors: list[Exception] = []

        async def async_compute(val: int) -> int:
            await asyncio.sleep(0.001)
            return val * 2

        def thread_func(val: int) -> None:
            try:
                result = run_sync(async_compute(val))
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Threads raised errors: {errors}"
        assert sorted(results) == [0, 2, 4, 6, 8]

    def test_run_sync_awaits_properly(self) -> None:
        """Test that run_sync properly awaits the coroutine."""
        call_order: list[str] = []

        async def async_track() -> str:
            call_order.append("start")
            await asyncio.sleep(0.001)
            call_order.append("end")
            return "done"

        result = run_sync(async_track())

        assert result == "done"
        assert call_order == ["start", "end"]

    def test_run_sync_reuses_executor_from_async_context(self) -> None:
        executor_ids: list[int] = []

        async def capture() -> None:
            run_sync(asyncio.sleep(0))
            executor_ids.append(id(_executor))
            run_sync(asyncio.sleep(0))
            executor_ids.append(id(_executor))

        asyncio.run(capture())

        assert len(set(executor_ids)) == 1

    def test_run_sync_concurrent_from_async_context(self) -> None:
        results: list[int] = []
        errors: list[Exception] = []

        async def outer() -> None:
            threads = []
            for i in range(10):

                async def work(val: int = i) -> int:
                    return val * 3

                def submit(val: int = i) -> None:
                    try:
                        results.append(run_sync(work(val)))
                    except Exception as e:
                        errors.append(e)

                t = threading.Thread(target=submit)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

        asyncio.run(outer())

        assert not errors
        assert sorted(results) == [i * 3 for i in range(10)]


class TestCleanup:
    def test_cleanup_event_loops_closes_registered_loops(self) -> None:
        loops_before = len(_thread_local_loops)

        async def noop() -> None:
            pass

        def worker() -> None:
            run_sync(noop())

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert len(_thread_local_loops) > loops_before

        cleanup_event_loops()

        assert len(_thread_local_loops) == 0

    def test_shutdown_cleans_up(self) -> None:
        async def noop() -> None:
            pass

        def worker() -> None:
            run_sync(noop())

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        shutdown()

        assert len(_thread_local_loops) == 0
