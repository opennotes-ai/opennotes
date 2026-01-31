"""Async compatibility utilities for running async code from sync contexts.

This module provides utilities for safely running async coroutines from
synchronous code, handling both cases where an event loop is already
running and where one needs to be created.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_thread_local = threading.local()


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
        return _thread_local.loop.run_until_complete(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()
