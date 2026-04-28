"""Global in-process limiter for Vertex/Gemini calls."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import logfire

from src.config import Settings, get_settings


@dataclass
class _LimiterState:
    limit: int
    loop: asyncio.AbstractEventLoop
    semaphore: asyncio.Semaphore
    active: int = 0
    pending: int = 0


_state: _LimiterState | None = None
_state_lock = threading.Lock()


def _limiter_state_for(limit: int, loop: asyncio.AbstractEventLoop) -> _LimiterState:
    global _state  # noqa: PLW0603
    if limit <= 0:
        raise ValueError("VERTEX_MAX_CONCURRENCY must be > 0")

    with _state_lock:
        if _state is None:
            _state = _LimiterState(limit=limit, loop=loop, semaphore=asyncio.Semaphore(limit))
        elif _state.loop is not loop:
            if _state.active or _state.pending:
                raise RuntimeError("Vertex limiter event loop changed while calls are active or waiting")
            _state = _LimiterState(limit=limit, loop=loop, semaphore=asyncio.Semaphore(limit))
        elif _state.limit != limit:
            if _state.active or _state.pending:
                raise RuntimeError(
                    "VERTEX_MAX_CONCURRENCY changed "
                    f"from {_state.limit} to {limit} while Vertex calls are active or waiting"
                )
            _state = _LimiterState(limit=limit, loop=loop, semaphore=asyncio.Semaphore(limit))
        _state.pending += 1
        return _state


@asynccontextmanager
async def vertex_slot(settings: Settings | None = None) -> AsyncIterator[None]:
    """Wait for a configured Vertex/Gemini execution slot.

    The semaphore is process-local by design while Vibecheck production is
    pinned to one Cloud Run instance. Saturated callers wait indefinitely.
    """
    resolved_settings = settings or get_settings()
    limit = resolved_settings.VERTEX_MAX_CONCURRENCY
    state = _limiter_state_for(limit, asyncio.get_running_loop())
    started = time.perf_counter()
    pending = True
    slot_active = False

    try:
        with logfire.span("vibecheck.vertex_limiter.wait") as span:
            await state.semaphore.acquire()
            wait_ms = (time.perf_counter() - started) * 1000
            with _state_lock:
                state.pending -= 1
                pending = False
                state.active += 1
                slot_active = True
            span.set_attribute("vertex_limiter.wait_ms", wait_ms)
            span.set_attribute("vertex_limiter.max_concurrency", limit)

        yield
    finally:
        if pending:
            with _state_lock:
                state.pending -= 1
        if slot_active:
            with _state_lock:
                state.active -= 1
            state.semaphore.release()
