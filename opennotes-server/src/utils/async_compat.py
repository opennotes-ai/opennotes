"""Async compatibility utilities for running async code from sync contexts.

This module provides utilities for safely running async coroutines from
synchronous code, handling both cases where an event loop is already
running and where one needs to be created.
"""

from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_thread_local = threading.local()
_thread_local_loops: list[asyncio.AbstractEventLoop] = []
_loops_lock = threading.Lock()
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _register_loop(loop: asyncio.AbstractEventLoop) -> None:
    with _loops_lock:
        _thread_local_loops.append(loop)


def cleanup_event_loops() -> None:
    with _loops_lock:
        for loop in _thread_local_loops:
            if not loop.is_closed():
                loop.call_soon_threadsafe(loop.stop)
                loop.close()
        _thread_local_loops.clear()


def shutdown() -> None:
    cleanup_event_loops()
    _executor.shutdown(wait=False)


atexit.register(shutdown)


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine synchronously.

    Handles two scenarios:
    1. No event loop running: Reuses thread-local loop for efficiency
    2. Event loop running: Runs in separate thread to avoid RuntimeError

    This is useful for DBOS workflows which are synchronous but need to
    call async database and service methods.

    Args:
        coro: The coroutine to execute

    Returns:
        The result of the coroutine

    Raises:
        Any exception raised by the coroutine
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        if not hasattr(_thread_local, "loop") or _thread_local.loop.is_closed():
            _thread_local.loop = asyncio.new_event_loop()
            _register_loop(_thread_local.loop)
        return _thread_local.loop.run_until_complete(coro)

    future = _executor.submit(asyncio.run, coro)
    return future.result()
