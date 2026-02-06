import asyncio
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import redis.asyncio as redis
from redis.asyncio.client import Pipeline

from src.circuit_breaker import circuit_breaker_registry
from src.config import settings

logger = logging.getLogger(__name__)


def get_redis_connection_kwargs(
    url: str,
    decode_responses: bool = False,
    max_connections: int | None = None,
    socket_timeout: float | None = None,
    socket_connect_timeout: float | None = None,
    retry_on_timeout: bool | None = None,
    **extra_kwargs: Any,
) -> dict[str, Any]:
    """
    Build Redis connection kwargs with consistent configuration.

    This is the single source of truth for Redis connection configuration.
    All Redis clients should use this function to ensure consistent settings.

    Args:
        url: Redis URL (redis:// or rediss:// for TLS)
        decode_responses: Whether to decode responses to strings (default: False returns bytes)
        max_connections: Max pool connections (default: settings.REDIS_MAX_CONNECTIONS)
        socket_timeout: Socket timeout in seconds (default: settings.REDIS_SOCKET_TIMEOUT)
        socket_connect_timeout: Connection timeout (default: settings.REDIS_SOCKET_CONNECT_TIMEOUT)
        retry_on_timeout: Retry on timeout (default: settings.REDIS_RETRY_ON_TIMEOUT)
        **extra_kwargs: Additional kwargs passed to redis.from_url()

    Returns:
        Dict of kwargs for redis.from_url()

    Raises:
        ValueError: If production requires TLS but URL doesn't use rediss://
    """
    if (
        settings.ENVIRONMENT == "production"
        and settings.REDIS_REQUIRE_TLS
        and not url.startswith("rediss://")
    ):
        raise ValueError(
            "Redis connection must use TLS in production (rediss://). "
            f"Current URL scheme: {url.split('://')[0]}."
        )

    kwargs: dict[str, Any] = {
        "max_connections": max_connections or settings.REDIS_MAX_CONNECTIONS,
        "socket_timeout": socket_timeout or settings.REDIS_SOCKET_TIMEOUT,
        "socket_connect_timeout": socket_connect_timeout or settings.REDIS_SOCKET_CONNECT_TIMEOUT,
        "retry_on_timeout": retry_on_timeout
        if retry_on_timeout is not None
        else settings.REDIS_RETRY_ON_TIMEOUT,
        "decode_responses": decode_responses,
    }

    if url.startswith("rediss://"):
        if settings.REDIS_CA_CERT_PATH:
            ca_path = Path(settings.REDIS_CA_CERT_PATH)
            if not ca_path.exists():
                raise ValueError(
                    f"Redis CA certificate not found at {settings.REDIS_CA_CERT_PATH}. "
                    "Download it from GCP Console or via: "
                    "gcloud redis instances describe INSTANCE_ID --region=REGION"
                )
            kwargs["ssl_ca_certs"] = str(ca_path)
            kwargs["ssl_cert_reqs"] = "required"
        else:
            raise ValueError(
                "REDIS_CA_CERT_PATH must be set for TLS connections (rediss://). "
                "Download the CA certificate from GCP Memorystore and set the path."
            )

    kwargs.update(extra_kwargs)
    return kwargs


async def create_redis_connection(
    url: str | None = None,
    decode_responses: bool = False,
    **kwargs: Any,
) -> redis.Redis:
    """
    Create a Redis connection with proper SSL handling.

    Args:
        url: Redis URL (default: settings.REDIS_URL)
        decode_responses: Whether to decode responses to strings
        **kwargs: Additional kwargs passed to get_redis_connection_kwargs()

    Returns:
        Connected Redis client
    """
    redis_url = url or settings.REDIS_URL
    connection_kwargs = get_redis_connection_kwargs(
        redis_url, decode_responses=decode_responses, **kwargs
    )
    return await redis.from_url(redis_url, **connection_kwargs)  # type: ignore[no-untyped-call]


class RedisClient:
    def __init__(self) -> None:
        self.client: redis.Redis | None = None
        self.circuit_breaker = circuit_breaker_registry.get_breaker(
            name="redis",
            expected_exception=redis.RedisError,
        )

    async def connect(self, redis_url: str | None = None) -> None:
        # Skip Redis connection in test environment unless explicitly needed for integration tests
        # Integration tests set INTEGRATION_TESTS=true to bypass this check
        if settings.TESTING and not os.environ.get("INTEGRATION_TESTS"):
            logger.info("Skipping Redis connection in test environment (will be mocked)")
            return

        try:
            url = redis_url or settings.REDIS_URL
            self.client = await create_redis_connection(url, decode_responses=False)
            await self.ping()
            logger.info(f"Connected to Redis successfully at {url}")
        except redis.RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("Disconnected from Redis")

    async def ping(self) -> bool:
        if not self.client:
            return False

        try:
            await self.circuit_breaker.call(self.client.ping)
            return True
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    async def check_connection(self) -> bool:
        return await self.ping()

    async def get(self, key: str) -> str | None:
        if not self.client:
            return None

        try:
            value = await self.circuit_breaker.call(self.client.get, key)
            if value is None:
                return None
            return value.decode("utf-8") if isinstance(value, bytes) else value
        except Exception as e:
            logger.error(f"Redis GET failed for key '{key}': {e}")
            return None

    async def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
    ) -> bool:
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            value_bytes = value.encode("utf-8")
            if ttl:
                await self.circuit_breaker.call(self.client.setex, key, ttl, value_bytes)
            else:
                await self.circuit_breaker.call(self.client.set, key, value_bytes)
            return True
        except Exception as e:
            logger.error(f"Redis SET failed for key '{key}': {e}")
            return False

    async def delete(self, *keys: str) -> int:
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.delete, *keys)
        except Exception as e:
            logger.error(f"Redis DELETE failed for keys {keys}: {e}")
            return 0

    async def exists(self, *keys: str) -> int:
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.exists, *keys)
        except Exception as e:
            logger.error(f"Redis EXISTS failed for keys {keys}: {e}")
            return 0

    async def expire(self, key: str, ttl: int) -> bool:
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.expire, key, ttl)
        except Exception as e:
            logger.error(f"Redis EXPIRE failed for key '{key}': {e}")
            return False

    async def ttl(self, key: str) -> int:
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.ttl, key)
        except Exception as e:
            logger.error(f"Redis TTL failed for key '{key}': {e}")
            return -2

    async def keys(self, pattern: str) -> list[str]:
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            keys = await self.circuit_breaker.call(self.client.keys, pattern)
            return [k.decode("utf-8") if isinstance(k, bytes) else k for k in keys]
        except Exception as e:
            logger.error(f"Redis KEYS failed for pattern '{pattern}': {e}")
            return []

    async def info(self, section: str = "all") -> dict[str, str]:
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.info, section)
        except Exception as e:
            logger.error(f"Redis INFO failed: {e}")
            return {}

    async def scan_iter(self, match: str | None = None) -> AsyncIterator[str]:
        """
        Iterate over keys matching the pattern using SCAN.

        Args:
            match: Pattern to match keys against

        Yields:
            Key strings matching the pattern
        """
        if not self.client:
            return

        cursor = 0
        while True:
            try:
                cursor, keys = await self.circuit_breaker.call(
                    self.client.scan, cursor, match=match
                )
                for key in keys:
                    yield key.decode("utf-8") if isinstance(key, bytes) else key
                if cursor == 0:
                    break
            except Exception as e:
                logger.error(f"Redis SCAN failed for pattern '{match}': {e}")
                break

    async def mget(self, keys: list[str]) -> list[str | None]:
        """
        Get multiple keys at once.

        Args:
            keys: List of keys to get

        Returns:
            List of values (None for missing keys)
        """
        if not self.client or not keys:
            return []

        try:
            values = await self.circuit_breaker.call(self.client.mget, keys)
            return [v.decode("utf-8") if isinstance(v, bytes) else v for v in values]
        except Exception as e:
            logger.error(f"Redis MGET failed for keys: {e}")
            return []

    async def hset(self, key: str, mapping: dict[str, str | int | float]) -> int:
        """
        Set multiple hash fields at once.

        Args:
            key: The hash key
            mapping: Dictionary of field-value pairs

        Returns:
            Number of fields added (not updated)
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            str_mapping = {k: str(v) for k, v in mapping.items()}
            return await self.circuit_breaker.call(self.client.hset, key, mapping=str_mapping)  # pyright: ignore[reportArgumentType]
        except Exception as e:
            logger.error(f"Redis HSET failed for key '{key}': {e}")
            return 0

    async def hgetall(self, key: str) -> dict[str, str]:
        """
        Get all fields and values from a hash.

        Args:
            key: The hash key

        Returns:
            Dictionary of field-value pairs (empty if key doesn't exist)
        """
        if not self.client:
            return {}

        try:
            result = await self.circuit_breaker.call(self.client.hgetall, key)  # pyright: ignore[reportArgumentType]
            return {
                k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8")
                if isinstance(v, bytes)
                else v
                for k, v in result.items()
            }
        except Exception as e:
            logger.error(f"Redis HGETALL failed for key '{key}': {e}")
            return {}

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        """
        Atomically increment a hash field by the given amount.

        Args:
            key: The hash key
            field: The field to increment
            amount: Amount to increment by (default 1)

        Returns:
            The new value after increment
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.hincrby, key, field, amount)  # pyright: ignore[reportArgumentType]
        except Exception as e:
            logger.error(f"Redis HINCRBY failed for key '{key}' field '{field}': {e}")
            raise

    async def setbit(self, key: str, offset: int, value: int) -> int:
        """
        Set or clear the bit at offset in the string value stored at key.

        Args:
            key: The key
            offset: Bit offset (0-indexed, must be >= 0)
            value: Bit value (must be 0 or 1)

        Returns:
            The original bit value at offset

        Raises:
            ValueError: If offset < 0 or value is not 0 or 1
            RuntimeError: If Redis client not connected
        """
        if offset < 0:
            raise ValueError(f"offset must be >= 0, got {offset}")
        if value not in (0, 1):
            raise ValueError(f"value must be 0 or 1, got {value}")
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.setbit, key, offset, value)
        except Exception as e:
            logger.error(f"Redis SETBIT failed for key '{key}' offset {offset}: {e}")
            raise

    async def getbit(self, key: str, offset: int) -> int:
        """
        Get the bit value at offset in the string value stored at key.

        Args:
            key: The key
            offset: Bit offset (0-indexed, must be >= 0)

        Returns:
            The bit value at offset (0 or 1)

        Raises:
            ValueError: If offset < 0
            RuntimeError: If Redis client not connected
        """
        if offset < 0:
            raise ValueError(f"offset must be >= 0, got {offset}")
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.getbit, key, offset)
        except Exception as e:
            logger.error(f"Redis GETBIT failed for key '{key}' offset {offset}: {e}")
            raise

    async def bitcount(self, key: str, start: int | None = None, end: int | None = None) -> int:
        """
        Count the number of set bits (1s) in a string.

        Args:
            key: The key
            start: Optional start byte offset
            end: Optional end byte offset

        Returns:
            Number of set bits

        Raises:
            RuntimeError: If Redis client not connected
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            if start is not None and end is not None:
                return await self.circuit_breaker.call(self.client.bitcount, key, start, end)
            return await self.circuit_breaker.call(self.client.bitcount, key)
        except Exception as e:
            logger.error(f"Redis BITCOUNT failed for key '{key}': {e}")
            raise

    def pipeline(self) -> Pipeline:
        """
        Create a Redis pipeline for batching commands.

        Pipelines allow multiple commands to be sent to Redis in a single
        network round-trip. When used with transaction=True (default),
        commands are executed atomically via MULTI/EXEC.

        Returns:
            Redis pipeline object

        Raises:
            RuntimeError: If client is not connected
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")
        return self.client.pipeline()

    async def sadd(self, key: str, *members: str) -> int:
        """
        Add one or more members to a set.

        Args:
            key: The set key
            *members: Members to add

        Returns:
            Number of members added (not already in set)

        Raises:
            RuntimeError: If Redis client not connected
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.sadd, key, *members)  # pyright: ignore[reportArgumentType]
        except Exception as e:
            logger.error(f"Redis SADD failed for key '{key}': {e}")
            raise

    async def sismember(self, key: str, member: str) -> int:
        """
        Check if a member is in a set.

        Args:
            key: The set key
            member: Member to check

        Returns:
            1 if member is in set, 0 otherwise

        Raises:
            RuntimeError: If Redis client not connected
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            return await self.circuit_breaker.call(self.client.sismember, key, member)  # pyright: ignore[reportArgumentType]
        except Exception as e:
            logger.error(f"Redis SISMEMBER failed for key '{key}': {e}")
            raise


redis_client = RedisClient()

_shared_redis: redis.Redis | None = None
_shared_redis_loop: asyncio.AbstractEventLoop | None = None


async def get_shared_redis_client(redis_url: str | None = None) -> redis.Redis:
    """Return a long-lived Redis connection for use across DBOS steps.

    Unlike RedisClient (which creates a new connection per step),
    this function reuses a module-level connection and only reconnects
    when the existing one is stale or the event loop has changed.

    DBOS workflow steps run in sync threads via ``run_sync()`` which create
    thread-local event loops. A Redis connection created on the main uvicorn
    loop will fail with "Task got Future attached to a different loop" when
    used from a worker thread's loop. This function detects that situation
    and creates a fresh connection bound to the current loop.
    """
    global _shared_redis, _shared_redis_loop  # noqa: PLW0603

    current_loop = asyncio.get_running_loop()

    if _shared_redis is not None and current_loop is _shared_redis_loop:
        try:
            await _shared_redis.ping()
            return _shared_redis
        except Exception:
            _shared_redis = None
            _shared_redis_loop = None

    if _shared_redis is not None and current_loop is not _shared_redis_loop:
        try:
            await _shared_redis.close()
        except Exception:
            pass
        _shared_redis = None
        _shared_redis_loop = None

    url = redis_url or settings.REDIS_URL
    _shared_redis = await create_redis_connection(url, decode_responses=False)
    _shared_redis_loop = current_loop
    return _shared_redis
