"""Global in-process limiter for Vertex/Gemini calls."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import logfire

from src.config import Settings, get_settings

_semaphores: dict[int, asyncio.Semaphore] = {}
_semaphores_lock = threading.Lock()


def _semaphore_for(limit: int) -> asyncio.Semaphore:
    if limit <= 0:
        raise ValueError("VERTEX_MAX_CONCURRENCY must be > 0")

    with _semaphores_lock:
        semaphore = _semaphores.get(limit)
        if semaphore is None:
            semaphore = asyncio.Semaphore(limit)
            _semaphores[limit] = semaphore
        return semaphore


@asynccontextmanager
async def vertex_slot(settings: Settings | None = None) -> AsyncIterator[None]:
    """Wait for a configured Vertex/Gemini execution slot.

    The semaphore is process-local by design while Vibecheck production is
    pinned to one Cloud Run instance. Saturated callers wait indefinitely.
    """
    resolved_settings = settings or get_settings()
    limit = resolved_settings.VERTEX_MAX_CONCURRENCY
    semaphore = _semaphore_for(limit)
    started = time.perf_counter()

    with logfire.span("vibecheck.vertex_limiter.wait") as span:
        await semaphore.acquire()
        wait_ms = (time.perf_counter() - started) * 1000
        span.set_attribute("vertex_limiter.wait_ms", wait_ms)
        span.set_attribute("vertex_limiter.max_concurrency", limit)

    try:
        yield
    finally:
        semaphore.release()
