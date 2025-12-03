import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis

from src.cache.redis_client import create_redis_connection
from src.config import settings

logger = logging.getLogger(__name__)


class InteractionCache:
    def __init__(self) -> None:
        self.redis_client: redis.Redis | None = None
        self._max_retries = 3
        self._retry_delay = 1.0

    async def connect(self) -> None:
        self.redis_client = await create_redis_connection(decode_responses=True)
        logger.info("Connected to Redis for caching")

    async def disconnect(self) -> None:
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

    async def __aenter__(self) -> "InteractionCache":
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

    async def check_duplicate(self, interaction_id: str) -> bool:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        key = f"interaction:seen:{interaction_id}"
        exists = await self.redis_client.exists(key)
        return bool(exists)

    async def mark_processed(self, interaction_id: str) -> None:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        key = f"interaction:seen:{interaction_id}"
        await self.redis_client.setex(
            key,
            settings.INTERACTION_CACHE_TTL,
            "1",
        )

    async def get_cached_response(
        self,
        interaction_id: str,
    ) -> dict[str, Any] | None:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        key = f"interaction:response:{interaction_id}"
        cached = await self.redis_client.get(key)

        if cached:
            logger.info(f"Cache hit for interaction {interaction_id}")
            result: dict[str, Any] = json.loads(cached)
            return result

        return None

    async def cache_response(
        self,
        interaction_id: str,
        response: dict[str, Any],
    ) -> None:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        key = f"interaction:response:{interaction_id}"
        await self.redis_client.setex(
            key,
            settings.INTERACTION_CACHE_TTL,
            json.dumps(response),
        )

    async def invalidate_cache(self, interaction_id: str) -> None:
        await self._ensure_connected()
        assert self.redis_client is not None, "Redis client should be connected"

        response_key = f"interaction:response:{interaction_id}"
        seen_key = f"interaction:seen:{interaction_id}"

        await self.redis_client.delete(response_key, seen_key)


interaction_cache = InteractionCache()
