"""
Database retry utilities for handling transient errors like deadlocks.

Provides decorators and utilities for retrying database operations that may fail
due to transient conditions such as:
- Deadlocks (concurrent transactions conflicting on row locks)
- Serialization failures (in SERIALIZABLE isolation)
- Connection timeouts

Usage:
    @with_deadlock_retry(max_attempts=3)
    async def my_db_operation(db: AsyncSession, item_id: UUID):
        # database operations that might deadlock
        pass
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from asyncpg.exceptions import DeadlockDetectedError
from sqlalchemy.exc import OperationalError

from src.monitoring import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def is_deadlock_error(exc: Exception) -> bool:
    """
    Check if an exception is a PostgreSQL deadlock error.

    SQLAlchemy wraps asyncpg exceptions in OperationalError. We need to check
    both the wrapper and the original exception.

    Args:
        exc: The exception to check

    Returns:
        True if the exception represents a deadlock
    """
    if isinstance(exc, DeadlockDetectedError):
        return True

    if isinstance(exc, OperationalError):
        orig = getattr(exc, "orig", None)
        if isinstance(orig, DeadlockDetectedError):
            return True
        error_code = getattr(exc, "pgcode", None) or getattr(orig, "pgcode", None)
        if error_code == "40P01":
            return True

    return False


def with_deadlock_retry(
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    jitter: float = 0.1,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Decorator for retrying async database operations on deadlock.

    Uses exponential backoff with jitter to avoid thundering herd when multiple
    workers retry simultaneously.

    Args:
        max_attempts: Maximum number of attempts (including initial attempt)
        base_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay in seconds between retries
        jitter: Random jitter factor (0.1 = +/- 10% randomness)

    Returns:
        Decorated function that retries on deadlock

    Example:
        @with_deadlock_retry(max_attempts=3)
        async def update_chunks(db: AsyncSession, chunk_ids: list[UUID]):
            # This will automatically retry up to 3 times if a deadlock occurs
            await db.execute(update(ChunkEmbedding).where(...))
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if not is_deadlock_error(e):
                        raise

                    last_exception = e

                    if attempt >= max_attempts:
                        logger.warning(
                            "Deadlock retry exhausted",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                            },
                        )
                        raise

                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    jittered_delay = delay * (1 + random.uniform(-jitter, jitter))

                    logger.info(
                        "Deadlock detected, retrying",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "delay_seconds": round(jittered_delay, 3),
                        },
                    )

                    await asyncio.sleep(jittered_delay)

            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected state: no exception captured")

        return wrapper

    return decorator
