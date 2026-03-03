from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_logger = logging.getLogger(__name__)

_thread_local = threading.local()
_thread_local_loops: list[asyncio.AbstractEventLoop] = []
_loops_lock = threading.Lock()

_bg_state: dict[str, Any] = {"loop": None, "thread": None}
_bg_lock = threading.Lock()


def _register_loop(loop: asyncio.AbstractEventLoop) -> None:
    with _loops_lock:
        _thread_local_loops.append(loop)


def _is_loop_healthy(
    loop: asyncio.AbstractEventLoop | None, thread: threading.Thread | None
) -> bool:
    return (
        loop is not None
        and not loop.is_closed()
        and loop.is_running()
        and thread is not None
        and thread.is_alive()
    )


def _ensure_background_loop() -> asyncio.AbstractEventLoop:
    existing = _bg_state["loop"]
    thread = _bg_state["thread"]
    if _is_loop_healthy(existing, thread):
        return existing  # type: ignore[return-value]
    with _bg_lock:
        existing = _bg_state["loop"]
        thread = _bg_state["thread"]
        if _is_loop_healthy(existing, thread):
            return existing  # type: ignore[return-value]
        if existing is not None and not existing.is_closed():
            existing.close()
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True, name="run_sync_bg_loop")
        thread.start()
        _bg_state["loop"] = loop
        _bg_state["thread"] = thread
        return loop


def cleanup_event_loops() -> None:
    with _loops_lock:
        for loop in _thread_local_loops:
            if not loop.is_closed():
                try:
                    if not loop.is_running():
                        loop.close()
                except RuntimeError:
                    pass
        _thread_local_loops.clear()


def shutdown() -> None:
    cleanup_event_loops()
    with _bg_lock:
        bg_loop = _bg_state["loop"]
        bg_thread = _bg_state["thread"]
        _bg_state["loop"] = None
        _bg_state["thread"] = None
    if bg_loop is not None and not bg_loop.is_closed():
        bg_loop.call_soon_threadsafe(bg_loop.stop)
        if bg_thread is not None:
            bg_thread.join(timeout=5)
        if not bg_loop.is_closed():
            bg_loop.close()


atexit.register(shutdown)


def run_sync(coro: Coroutine[Any, Any, T], *, timeout: float = 300.0) -> T:
    try:
        loop = asyncio.get_running_loop()
        _logger.debug(
            "run_sync: running event loop detected, submitting to background loop (thread=%s, loop=%s)",
            threading.current_thread().name,
            id(loop),
        )
    except RuntimeError:
        if not hasattr(_thread_local, "loop") or _thread_local.loop.is_closed():
            _thread_local.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_thread_local.loop)
            _register_loop(_thread_local.loop)
        _logger.debug(
            "run_sync: no running loop, using thread-local loop (thread=%s)",
            threading.current_thread().name,
        )
        return _thread_local.loop.run_until_complete(coro)

    bg_loop = _ensure_background_loop()
    try:
        current = asyncio.get_running_loop()
        if current is bg_loop:
            raise RuntimeError(
                "run_sync() called from the background event loop — this would deadlock. "
                "Use 'await' directly instead."
            )
    except RuntimeError as e:
        if "deadlock" in str(e):
            raise
    future = asyncio.run_coroutine_threadsafe(coro, bg_loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        raise
