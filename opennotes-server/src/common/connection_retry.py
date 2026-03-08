import asyncio
import random
import socket
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.monitoring import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

TRANSIENT_CONNECTION_ERRORS = (socket.gaierror, ConnectionRefusedError, OSError)


def is_transient_connection_error(exc: Exception) -> bool:
    return isinstance(exc, TRANSIENT_CONNECTION_ERRORS)


def _get_metric():
    from src.monitoring.metrics import db_connection_retries_total  # noqa: PLC0415

    return db_connection_retries_total


def async_connect_with_retry(
    creator: Callable[..., Awaitable[T]],
    max_retries: int = 3,
    backoff_base: float = 0.5,
    max_delay: float = 10.0,
    jitter: float = 0.1,
) -> Callable[..., Awaitable[T]]:
    async def connect_with_retry(*args, **kwargs) -> T:
        for attempt in range(max_retries + 1):
            try:
                result = await creator(*args, **kwargs)
                if attempt > 0:
                    logger.warning(
                        "DB connection succeeded after retry", extra={"attempt": attempt + 1}
                    )
                    _get_metric().add(1, {"outcome": "success"})
                return result
            except Exception as e:
                if not is_transient_connection_error(e):
                    raise
                if attempt >= max_retries:
                    logger.warning(
                        "DB connection retries exhausted",
                        extra={"attempts": attempt + 1, "error": str(e)},
                    )
                    _get_metric().add(1, {"outcome": "exhausted"})
                    raise
                delay = min(backoff_base * (2**attempt), max_delay)
                delay *= 1 + random.uniform(-jitter, jitter)
                logger.warning(
                    "DB connection failed, retrying",
                    extra={"attempt": attempt + 1, "delay": round(delay, 3), "error": str(e)},
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    return connect_with_retry


def sync_connect_with_retry(
    creator: Callable[..., T],
    max_retries: int = 3,
    backoff_base: float = 0.5,
    max_delay: float = 10.0,
    jitter: float = 0.1,
) -> Callable[..., T]:
    def connect_with_retry(*args, **kwargs) -> T:
        for attempt in range(max_retries + 1):
            try:
                result = creator(*args, **kwargs)
                if attempt > 0:
                    logger.warning(
                        "DB connection succeeded after retry", extra={"attempt": attempt + 1}
                    )
                    _get_metric().add(1, {"outcome": "success"})
                return result
            except Exception as e:
                if not is_transient_connection_error(e):
                    raise
                if attempt >= max_retries:
                    logger.warning(
                        "DB connection retries exhausted",
                        extra={"attempts": attempt + 1, "error": str(e)},
                    )
                    _get_metric().add(1, {"outcome": "exhausted"})
                    raise
                delay = min(backoff_base * (2**attempt), max_delay)
                delay *= 1 + random.uniform(-jitter, jitter)
                logger.warning(
                    "DB connection failed, retrying",
                    extra={"attempt": attempt + 1, "delay": round(delay, 3), "error": str(e)},
                )
                time.sleep(delay)
        raise RuntimeError("unreachable")

    return connect_with_retry
