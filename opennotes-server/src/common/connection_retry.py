import asyncio
import logging
import random
import socket
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_CONNECTION_ERRORS = (
    socket.gaierror,
    ConnectionRefusedError,
    ConnectionResetError,
    ConnectionAbortedError,
)


def is_transient_connection_error(exc: Exception) -> bool:
    if isinstance(exc, TRANSIENT_CONNECTION_ERRORS):
        return True
    try:
        import psycopg2  # noqa: PLC0415

        if isinstance(exc, psycopg2.OperationalError):
            return exc.pgcode is None
    except ImportError:
        pass
    try:
        import psycopg  # noqa: PLC0415

        if isinstance(exc, psycopg.OperationalError):
            return exc.sqlstate is None
    except ImportError:
        pass
    return False


def _get_metric():
    from src.monitoring.metrics import db_connection_retries_total  # noqa: PLC0415

    return db_connection_retries_total


def _emit_metric(outcome: str) -> None:
    try:
        _get_metric().add(1, {"outcome": outcome})
    except Exception:
        logger.debug("Failed to emit connection retry metric", exc_info=True)


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
                    _emit_metric("success")
                return result
            except Exception as e:
                if not is_transient_connection_error(e):
                    raise
                if attempt >= max_retries:
                    logger.warning(
                        "DB connection retries exhausted",
                        extra={"attempts": attempt + 1, "error": str(e)},
                    )
                    _emit_metric("exhausted")
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
                    _emit_metric("success")
                return result
            except Exception as e:
                if not is_transient_connection_error(e):
                    raise
                if attempt >= max_retries:
                    logger.warning(
                        "DB connection retries exhausted",
                        extra={"attempts": attempt + 1, "error": str(e)},
                    )
                    _emit_metric("exhausted")
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
