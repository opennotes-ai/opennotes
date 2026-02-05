import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import xxhash

from src.cache.adapters import RedisCacheAdapter
from src.cache.interfaces import CacheConfig
from src.cache.monitoring import update_cache_metrics
from src.config import settings

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CacheManager:
    def __init__(self) -> None:
        self.cache: RedisCacheAdapter[Any] = RedisCacheAdapter(
            config=CacheConfig(
                default_ttl=settings.CACHE_DEFAULT_TTL,
                key_prefix="",
            ),
            url=settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            max_retries=3,
            socket_timeout=float(settings.REDIS_SOCKET_TIMEOUT),
            socket_connect_timeout=float(settings.REDIS_SOCKET_CONNECT_TIMEOUT),
        )
        self._started = False
        self._start_lock = asyncio.Lock()

    async def _ensure_started(self) -> None:
        if not self._started:
            async with self._start_lock:
                if not self._started:
                    await self.cache.start()
                    logger.info("Redis cache started successfully")
                    self._started = True

    def generate_key(self, prefix: str, *args: Any, **kwargs: Any) -> str:
        key_parts = [str(arg) for arg in args]
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        key_string = ":".join(key_parts)

        if len(key_string) > 100:
            key_hash = xxhash.xxh3_64(key_string.encode()).hexdigest()
            return f"{prefix}:{key_hash}"

        return f"{prefix}:{key_string}" if key_string else prefix

    async def get(self, key: str) -> Any | None:
        try:
            await self._ensure_started()
            cached = await self.cache.get(key)
            if cached is not None:
                logger.debug(f"Cache hit for key: {key}")
                return cached
            logger.debug(f"Cache miss for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache get failed for key '{key}': {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        try:
            await self._ensure_started()
            effective_ttl = ttl if ttl is not None else settings.CACHE_DEFAULT_TTL

            if effective_ttl < 0:
                logger.warning(
                    f"Invalid TTL value {effective_ttl} for key '{key}', using 0 (no expiration)"
                )
                effective_ttl = 0

            success = await self.cache.set(key, value, ttl=effective_ttl)
            if success:
                logger.debug(f"Cached data for key: {key} (TTL: {effective_ttl}s)")
            return success
        except Exception as e:
            logger.error(f"Cache set failed for key '{key}': {e}")
            return False

    async def delete(self, *keys: str) -> int:
        try:
            await self._ensure_started()
            count = 0
            for key in keys:
                if await self.cache.delete(key):
                    count += 1
            logger.debug(f"Deleted {count} keys from cache")
            return count
        except Exception as e:
            logger.error(f"Cache delete failed for keys {keys}: {e}")
            return 0

    async def invalidate_pattern(self, pattern: str) -> int:
        try:
            await self._ensure_started()
            count = await self.cache.clear(pattern)
            logger.debug(f"Invalidated {count} keys matching pattern: {pattern}")
            return count
        except Exception as e:
            logger.error(f"Cache invalidation failed for pattern '{pattern}': {e}")
            return 0

    async def clear_all(self) -> bool:
        try:
            await self._ensure_started()
            count = await self.cache.clear()
            logger.warning(f"Cleared all cache data ({count} keys)")
            return True
        except Exception as e:
            logger.error(f"Cache clear failed: {e}")
            return False

    def get_metrics(self) -> dict[str, int | float | bool | str]:
        """Get cache metrics for monitoring."""
        try:
            metrics = self.cache.get_metrics()
            return {
                "hits": metrics.hits,
                "misses": metrics.misses,
                "hit_rate": metrics.hit_rate(),
                "sets": metrics.sets,
                "deletes": metrics.deletes,
                "evictions": metrics.evictions,
                "size": metrics.size,
                "memory_bytes": metrics.memory_bytes,
                "cache_type": "redis",
            }
        except Exception as e:
            logger.error(f"Failed to get cache metrics: {e}")
            return {}

    async def update_prometheus_metrics(self) -> None:
        """Update Prometheus metrics from cache adapter."""
        try:
            metrics = self.cache.get_metrics()
            update_cache_metrics("redis", metrics)
        except Exception as e:
            logger.debug(f"Failed to update Prometheus metrics: {e}")


cache_manager = CacheManager()


class ProcessAwareLockManager:
    def __init__(self) -> None:
        pass

    def _get_redis_lock_key(self, cache_key: str) -> str:
        return f"lock:{cache_key}"

    async def acquire_lock(self, cache_key: str, timeout: float = 30.0) -> bool:
        lock_key = self._get_redis_lock_key(cache_key)
        try:
            if cache_manager.cache.client is None:
                return False
            result = await cache_manager.cache.client.set(
                lock_key, "locked", ex=int(timeout), nx=True
            )
            return bool(result)
        except Exception as e:
            logger.warning(f"Failed to acquire Redis lock for {cache_key}: {e}")
            return False

    async def release_lock(self, cache_key: str) -> None:
        lock_key = self._get_redis_lock_key(cache_key)
        try:
            if cache_manager.cache.client is None:
                return
            await cache_manager.cache.client.delete(lock_key)
        except Exception as e:
            logger.warning(f"Failed to release Redis lock for {cache_key}: {e}")

    async def wait_for_lock(self, cache_key: str, timeout: float = 30.0) -> bool:
        lock_key = self._get_redis_lock_key(cache_key)
        start = time.time()
        while time.time() - start < timeout:
            try:
                if cache_manager.cache.client is None:
                    return True
                exists = await cache_manager.cache.client.exists(lock_key)
                if not exists:
                    return True
            except Exception as e:
                logger.warning(f"Failed to check Redis lock for {cache_key}: {e}")
                return True

            await asyncio.sleep(0.01)

        return False


lock_manager = ProcessAwareLockManager()


def cached(
    prefix: str,
    ttl: int | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Cache decorator with stampede prevention using single-flight pattern.

    When multiple concurrent requests need the same uncached key, only the first
    request executes the function while others wait for the result. This prevents
    the "thundering herd" problem where many requests would execute expensive
    operations simultaneously.

    Uses Redis-based locks for process-aware synchronization across pytest-xdist workers.

    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds (None uses default)
        key_builder: Optional custom key builder function

    Returns:
        Decorated async function with caching and stampede prevention
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = cache_manager.generate_key(prefix, *args, **kwargs)

            # Fast path: check cache without lock
            cached_value = await cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value  # type: ignore[no-any-return]

            # Attempt to acquire Redis lock (single-flight pattern)
            lock_acquired = await lock_manager.acquire_lock(cache_key)

            try:
                if lock_acquired:
                    # This worker acquired the lock - execute the function
                    # Double-check cache before computing (another worker may have populated it)
                    cached_value = await cache_manager.get(cache_key)
                    if cached_value is not None:
                        return cached_value  # type: ignore[no-any-return]

                    # Execute the wrapped function (let exceptions propagate)
                    result = await func(*args, **kwargs)

                    # Attempt to cache the result and log if it fails
                    success = await cache_manager.set(cache_key, result, ttl=ttl)
                    if not success:
                        logger.warning(
                            f"Failed to cache result for key: {cache_key}",
                            extra={"cache_key": cache_key, "prefix": prefix, "ttl": ttl},
                        )

                    return result
                # Another worker is computing - wait for the lock to be released
                await lock_manager.wait_for_lock(cache_key)

                # Check cache after lock is released
                cached_value = await cache_manager.get(cache_key)
                if cached_value is not None:
                    return cached_value  # type: ignore[no-any-return]

                # If lock wait timed out or cache is still empty, compute locally
                # This graceful degradation ensures we don't block indefinitely
                result = await func(*args, **kwargs)
                await cache_manager.set(cache_key, result, ttl=ttl)
                return result
            finally:
                # Release lock if we acquired it
                if lock_acquired:
                    await lock_manager.release_lock(cache_key)

        return wrapper

    return decorator


def cache_scoring_result(
    func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]:
    return cached(prefix="scoring", ttl=settings.CACHE_SCORING_TTL)(func)


def cache_user_profile(
    func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]:
    return cached(prefix="user_profile", ttl=settings.CACHE_USER_PROFILE_TTL)(func)
