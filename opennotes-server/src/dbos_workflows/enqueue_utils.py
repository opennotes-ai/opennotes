from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import OperationalError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class DBOSEnqueueTransientError(Exception):
    """Raised when DBOS enqueue fails after retries due to transient DB errors."""


def _is_transient_enqueue_error(exc: BaseException) -> bool:
    if isinstance(exc, OperationalError):
        return True
    return isinstance(exc, AttributeError) and "sqlstate" in str(exc)


_enqueue_retry = retry(
    retry=retry_if_exception(_is_transient_enqueue_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)


async def safe_enqueue(enqueue_fn: Callable[[], T]) -> T:
    @_enqueue_retry
    def _with_retry() -> T:
        return enqueue_fn()

    try:
        return await asyncio.to_thread(_with_retry)
    except (OperationalError, AttributeError) as exc:
        if _is_transient_enqueue_error(exc):
            raise DBOSEnqueueTransientError(f"DBOS enqueue failed after retries: {exc}") from exc
        raise


def safe_enqueue_sync(enqueue_fn: Callable[[], T]) -> T:
    @_enqueue_retry
    def _with_retry() -> T:
        return enqueue_fn()

    try:
        return _with_retry()
    except (OperationalError, AttributeError) as exc:
        if _is_transient_enqueue_error(exc):
            raise DBOSEnqueueTransientError(f"DBOS enqueue failed after retries: {exc}") from exc
        raise
