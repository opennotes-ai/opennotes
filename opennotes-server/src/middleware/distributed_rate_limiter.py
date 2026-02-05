import logging
import time
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from src.cache.redis_client import create_redis_connection

logger = logging.getLogger(__name__)


@dataclass
class RateLimitInfo:
    allowed: bool
    remaining: int
    reset_at: int
    retry_after: int | None = None


class DistributedRateLimiter:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url
        self.redis: redis.Redis | None = None
        self.key_prefix = "rate_limit:"

    async def connect(self) -> None:
        if not self.redis_url:
            logger.warning("Redis URL not configured for distributed rate limiting")
            return

        try:
            self.redis = await create_redis_connection(
                url=self.redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            await self.redis.ping()
            logger.info("Connected to Redis for distributed rate limiting")
        except Exception as e:
            logger.error(f"Failed to connect to Redis for rate limiting: {e}")
            self.redis = None

    async def disconnect(self) -> None:
        if self.redis:
            await self.redis.aclose()
            logger.info("Disconnected from Redis for distributed rate limiting")

    def _build_key(self, identifier: str, window_key: str | None = None) -> str:
        if window_key:
            return f"{self.key_prefix}{window_key}:{identifier}"
        return f"{self.key_prefix}{identifier}"

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        window_key: str | None = None,
    ) -> RateLimitInfo:
        if not self.redis:
            logger.debug("Redis not available, allowing request (fallback mode)")
            return RateLimitInfo(
                allowed=True, remaining=limit, reset_at=int(time.time()) + window_seconds
            )

        key = self._build_key(identifier, window_key)

        try:
            current_time = int(time.time())
            window_start = current_time - window_seconds

            lua_script = """
            local key = KEYS[1]
            local limit = tonumber(ARGV[1])
            local window_start = tonumber(ARGV[2])
            local current_time = tonumber(ARGV[3])
            local window_seconds = tonumber(ARGV[4])

            local reset_at = current_time + window_seconds

            -- Remove old entries outside the window
            redis.call('zremrangebyscore', key, '-inf', window_start)

            -- Count current requests in window
            local current_count = redis.call('zcard', key)

            if current_count < limit then
                -- Add new request with current timestamp as score
                redis.call('zadd', key, current_time, current_time .. ':' .. math.random())
                -- Set expiration to cleanup old data
                redis.call('expire', key, window_seconds + 1)
                -- Return: allowed=1, remaining, reset_at
                return {1, limit - current_count - 1, reset_at}
            else
                -- Rate limit exceeded
                -- Return: allowed=0, remaining=0, reset_at
                return {0, 0, reset_at}
            end
            """

            result = await self.redis.eval(  # type: ignore
                lua_script,
                1,
                key,
                str(limit),
                str(window_start),
                str(current_time),
                str(window_seconds),
            )

            if result:
                allowed = bool(result[0])
                remaining = int(result[1])
                reset_at = int(result[2])
                retry_after = max(0, reset_at - current_time) if not allowed else None

                return RateLimitInfo(
                    allowed=allowed,
                    remaining=remaining,
                    reset_at=reset_at,
                    retry_after=retry_after,
                )

            return RateLimitInfo(
                allowed=True, remaining=limit, reset_at=int(time.time()) + window_seconds
            )

        except Exception as e:
            logger.error(f"Rate limit check failed for {identifier}: {e}")
            return RateLimitInfo(
                allowed=True, remaining=limit, reset_at=int(time.time()) + window_seconds
            )

    async def reset_limit(
        self,
        identifier: str,
        window_key: str | None = None,
    ) -> bool:
        if not self.redis:
            return True

        key = self._build_key(identifier, window_key)

        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to reset rate limit for {identifier}: {e}")
            return False

    async def get_limit_info(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        window_key: str | None = None,
    ) -> dict[str, Any]:
        if not self.redis:
            return {
                "limit": limit,
                "remaining": limit,
                "reset_at": int(time.time()) + window_seconds,
                "window_seconds": window_seconds,
            }

        key = self._build_key(identifier, window_key)

        try:
            current_time = int(time.time())
            window_start = current_time - window_seconds

            lua_script = """
            local key = KEYS[1]
            local limit = tonumber(ARGV[1])
            local window_start = tonumber(ARGV[2])
            local current_time = tonumber(ARGV[3])
            local window_seconds = tonumber(ARGV[4])

            local reset_at = current_time + window_seconds

            -- Count current requests in window
            local current_count = redis.call('zcount', key, window_start, current_time)

            return {limit - current_count, reset_at}
            """

            result = await self.redis.eval(  # type: ignore
                lua_script,
                1,
                key,
                str(limit),
                str(window_start),
                str(current_time),
                str(window_seconds),
            )

            if result:
                remaining = max(0, int(result[0]))
                reset_at = int(result[1])

                return {
                    "limit": limit,
                    "remaining": remaining,
                    "reset_at": reset_at,
                    "window_seconds": window_seconds,
                }

            return {
                "limit": limit,
                "remaining": limit,
                "reset_at": int(time.time()) + window_seconds,
                "window_seconds": window_seconds,
            }

        except Exception as e:
            logger.error(f"Failed to get rate limit info for {identifier}: {e}")
            return {
                "limit": limit,
                "remaining": limit,
                "reset_at": int(time.time()) + window_seconds,
                "window_seconds": window_seconds,
            }
