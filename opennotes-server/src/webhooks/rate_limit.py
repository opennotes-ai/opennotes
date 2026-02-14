import asyncio
import logging
from typing import Any

import pendulum
import redis.asyncio as redis

from src.cache.redis_client import create_redis_connection
from src.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self) -> None:
        self.redis_client: redis.Redis | None = None
        self._max_retries = 3
        self._retry_delay = 1.0

    async def connect(self) -> None:
        self.redis_client = await create_redis_connection(decode_responses=True)
        logger.info("Connected to Redis for rate limiting")

    async def disconnect(self) -> None:
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

    async def __aenter__(self) -> "RateLimiter":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    async def is_connected(self) -> bool:
        if not self.redis_client:
            return False
        try:
            await self.redis_client.ping()
            return True
        except Exception:
            return False

    async def ping(self) -> bool:
        if not self.redis_client:
            return False
        try:
            await self.redis_client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis ping failed: {e}")
            return False

    async def _ensure_connected(self) -> None:
        if await self.is_connected():
            return

        for attempt in range(self._max_retries):
            try:
                logger.info(
                    f"Attempting to reconnect to Redis (attempt {attempt + 1}/{self._max_retries})"
                )
                await self.connect()
                if await self.is_connected():
                    logger.info("Successfully reconnected to Redis")
                    return
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2**attempt)
                    await asyncio.sleep(delay)

        raise RuntimeError("Redis client not connected and reconnection failed")

    async def check_rate_limit(
        self,
        community_server_id: str,
        user_id: str | None = None,
    ) -> tuple[bool, int]:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        key = f"rate_limit:community_server:{community_server_id}"
        if user_id:
            key = f"rate_limit:community_server:{community_server_id}:user:{user_id}"

        now = pendulum.now("UTC").timestamp()
        window_start = now - settings.WEBHOOK_RATE_LIMIT_WINDOW

        async with self.redis_client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, settings.WEBHOOK_RATE_LIMIT_WINDOW)

            results = await pipe.execute()

        current_count = results[2]

        if current_count > settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER:
            await self.redis_client.zrem(key, str(now))
            remaining = 0
            allowed = False
            logger.warning(f"Rate limit exceeded for {key}")
        else:
            remaining = settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER - current_count
            allowed = True

        return allowed, remaining

    async def get_rate_limit_info(
        self,
        community_server_id: str,
        user_id: str | None = None,
    ) -> dict[str, int]:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        key = f"rate_limit:community_server:{community_server_id}"
        if user_id:
            key = f"rate_limit:community_server:{community_server_id}:user:{user_id}"

        now = pendulum.now("UTC").timestamp()
        window_start = now - settings.WEBHOOK_RATE_LIMIT_WINDOW

        await self.redis_client.zremrangebyscore(key, 0, window_start)
        current_count = await self.redis_client.zcard(key)

        return {
            "limit": settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER,
            "remaining": max(0, settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER - current_count),
            "window": settings.WEBHOOK_RATE_LIMIT_WINDOW,
        }


rate_limiter = RateLimiter()
