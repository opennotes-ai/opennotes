"""Tests for async_compat utilities."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any

import pytest

from src.utils.async_compat import (
    _bg_state,
    _ensure_background_loop,
    run_sync,
    shutdown,
)


class TestRunSync:
    """Tests for the run_sync utility function."""

    def test_run_sync_from_sync_context(self) -> None:
        async def async_add(a: int, b: int) -> int:
            return a + b

        result = run_sync(async_add(2, 3))
        assert result == 5

    def test_run_sync_from_async_context(self) -> None:
        async def async_multiply(a: int, b: int) -> int:
            return a * b

        async def outer() -> int:
            return run_sync(async_multiply(4, 5))

        result = asyncio.run(outer())
        assert result == 20

    def test_run_sync_reuses_background_loop(self) -> None:
        loop_ids: list[int] = []

        async def capture_loop_id() -> int:
            loop = asyncio.get_running_loop()
            return id(loop)

        loop_ids.append(run_sync(capture_loop_id()))
        loop_ids.append(run_sync(capture_loop_id()))
        loop_ids.append(run_sync(capture_loop_id()))

        assert len(set(loop_ids)) == 1, "Background loop should be reused across calls"

    def test_run_sync_handles_exceptions(self) -> None:
        async def async_fail() -> None:
            raise ValueError("Expected test error")

        with pytest.raises(ValueError, match="Expected test error"):
            run_sync(async_fail())

    def test_run_sync_handles_exceptions_in_async_context(self) -> None:
        async def async_fail() -> None:
            raise RuntimeError("Expected runtime error")

        async def outer() -> None:
            run_sync(async_fail())

        with pytest.raises(RuntimeError, match="Expected runtime error"):
            asyncio.run(outer())

    def test_run_sync_returns_complex_types(self) -> None:
        async def async_complex() -> dict[str, Any]:
            return {"nested": {"list": [1, 2, 3], "value": "test"}}

        result = run_sync(async_complex())
        assert result == {"nested": {"list": [1, 2, 3], "value": "test"}}

    def test_run_sync_in_multiple_threads(self) -> None:
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
        call_order: list[str] = []

        async def async_track() -> str:
            call_order.append("start")
            await asyncio.sleep(0.001)
            call_order.append("end")
            return "done"

        result = run_sync(async_track())

        assert result == "done"
        assert call_order == ["start", "end"]

    def test_run_sync_reuses_background_loop_from_async_context(self) -> None:
        loop_ids: list[int] = []

        async def capture_loop() -> int:
            return id(asyncio.get_running_loop())

        async def outer() -> None:
            for _ in range(5):
                loop_ids.append(run_sync(capture_loop()))

        asyncio.run(outer())
        assert len(set(loop_ids)) == 1, f"Expected 1 background loop, got {len(set(loop_ids))}"

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

    def test_concurrent_run_sync_with_session_maker(self) -> None:
        errors: list[Exception] = []

        async def db_work() -> str:
            from src.database import get_session_maker

            maker = get_session_maker()
            loop_id = id(asyncio.get_running_loop())
            return f"loop={loop_id},maker={id(maker)}"

        async def outer() -> None:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(run_sync, db_work()) for _ in range(20)]
                for f in concurrent.futures.as_completed(futures):
                    try:
                        f.result()
                    except Exception as e:
                        errors.append(e)

        asyncio.run(outer())
        assert not errors, f"Concurrent run_sync errors: {errors}"

    def test_sync_and_async_contexts_use_same_background_loop(self) -> None:
        loop_ids: list[int] = []

        async def capture_loop() -> int:
            return id(asyncio.get_running_loop())

        loop_ids.append(run_sync(capture_loop()))

        async def outer() -> None:
            loop_ids.append(run_sync(capture_loop()))

        asyncio.run(outer())

        assert len(set(loop_ids)) == 1, "Both sync and async contexts should use the same bg loop"


class TestEnsureBackgroundLoopDoubleCheck:
    def test_inner_lock_fast_path_when_another_thread_fixed_it(self) -> None:
        from unittest.mock import patch

        shutdown()

        healthy_loop = asyncio.new_event_loop()
        healthy_thread = threading.Thread(
            target=healthy_loop.run_forever, daemon=True, name="test_bg_loop"
        )
        healthy_thread.start()

        _bg_state["loop"] = healthy_loop
        _bg_state["thread"] = healthy_thread

        call_count = 0

        def mock_is_loop_healthy(loop: object, thread: object) -> bool:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return False
            return (
                loop is not None
                and not loop.is_closed()  # type: ignore[union-attr]
                and loop.is_running()  # type: ignore[union-attr]
                and thread is not None
                and thread.is_alive()  # type: ignore[union-attr]
            )

        with patch("src.utils.async_compat._is_loop_healthy", side_effect=mock_is_loop_healthy):
            result = _ensure_background_loop()

        assert result is healthy_loop
        assert call_count == 2

        healthy_loop.call_soon_threadsafe(healthy_loop.stop)
        healthy_thread.join(timeout=5)
        if not healthy_loop.is_closed():
            healthy_loop.close()

        shutdown()


class TestShutdownLocking:
    def test_shutdown_acquires_bg_lock(self) -> None:
        async def noop() -> None:
            pass

        async def outer() -> None:
            run_sync(noop())

        asyncio.run(outer())

        assert _bg_state["loop"] is not None
        assert _bg_state["thread"] is not None

        shutdown()

        assert _bg_state["loop"] is None
        assert _bg_state["thread"] is None


class TestRunSyncTimeout:
    def test_run_sync_cancels_future_on_timeout(self) -> None:
        async def slow_coro() -> str:
            await asyncio.sleep(60)
            return "never"

        async def outer() -> None:
            with pytest.raises(TimeoutError):
                run_sync(slow_coro(), timeout=0.1)

        asyncio.run(outer())

    def test_run_sync_timeout_from_sync_context(self) -> None:
        async def slow_coro() -> str:
            await asyncio.sleep(60)
            return "never"

        with pytest.raises(TimeoutError):
            run_sync(slow_coro(), timeout=0.1)


class TestEnsureBackgroundLoopDeadThread:
    def test_ensure_background_loop_detects_dead_thread(self) -> None:
        async def noop() -> None:
            pass

        async def outer() -> None:
            run_sync(noop())

        asyncio.run(outer())

        old_loop = _bg_state["loop"]
        old_thread = _bg_state["thread"]
        assert old_loop is not None
        assert old_thread is not None
        assert old_thread.is_alive()

        old_loop.call_soon_threadsafe(old_loop.stop)
        old_thread.join(timeout=5)
        assert not old_thread.is_alive()

        new_loop = _ensure_background_loop()
        assert new_loop is not old_loop
        assert new_loop.is_running()
        assert old_loop.is_closed()
        new_thread = _bg_state["thread"]
        assert new_thread is not None
        assert new_thread.is_alive()

        shutdown()


class TestRunSyncReentrancy:
    def test_run_sync_detects_reentrancy(self) -> None:
        bg_loop = _ensure_background_loop()

        async def reentrant_coro() -> str:
            async def inner() -> str:
                return "inner"

            return run_sync(inner())

        future = asyncio.run_coroutine_threadsafe(reentrant_coro(), bg_loop)

        with pytest.raises(RuntimeError, match="deadlock"):
            future.result(timeout=5)

        shutdown()
