"""
Redis cache implementation with connection pooling and retry logic.

Features:
- Async operations with connection pooling
- Automatic retry with exponential backoff
- Connection health monitoring
- Pub/Sub support for cache invalidation
- Circuit breaker pattern
- Metrics collection

Suitable for:
- Production deployments
- Multi-instance/distributed systems
- High-availability requirements
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from typing import Any, Generic, TypeVar, cast

import orjson
from pydantic import BaseModel, Field, ValidationError
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    RedisError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from src.config import settings

from ..interfaces import CacheConfig, CacheInterface, CacheMetrics
from ..redis_client import get_redis_connection_kwargs

logger = logging.getLogger(__name__)
T = TypeVar("T")

MAX_MESSAGE_AGE_SECONDS = 300


class PubSubMessage(BaseModel):
    """Validated pub/sub message structure."""

    type: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] | str
    timestamp: int = Field(..., ge=0)
    signature: str | None = Field(default=None, min_length=64, max_length=128)


class RedisCacheAdapter(CacheInterface[T], Generic[T]):
    """
    Redis cache adapter with connection pooling and retry logic.

    Type Parameters:
        T: The type of values stored in the cache

    Example:
        # Cache with JSON-serializable data
        cache: RedisCacheAdapter[dict[str, Any]] = RedisCacheAdapter(url="redis://localhost")
        await cache.start()
        await cache.set("session:123", {"user_id": 456, "expires": 1234567890})
        session: dict[str, Any] | None = await cache.get("session:123")

        # Cache with Pydantic models (using schema validation)
        cache: RedisCacheAdapter[UserModel] = RedisCacheAdapter(url="redis://localhost")
        await cache.start()
        await cache.set("user:123", user_model)
        user: UserModel | None = await cache.get("user:123", schema=UserModel)
    """

    def __init__(
        self,
        config: CacheConfig | None = None,
        url: str | None = None,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
        db: int = 0,
        max_connections: int = 10,
        max_retries: int = 3,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ):
        self.config = config or CacheConfig()
        self.metrics = CacheMetrics()

        # Connection parameters - use settings for consistency
        self.url = url or settings.REDIS_URL
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.max_connections = max_connections
        self.max_retries = max_retries
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout

        # Connection objects
        self.pool: ConnectionPool | None = None
        self.client: Redis | None = None
        self.is_connected = False

        # Track subscription tasks to prevent leaks
        self.subscription_tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Initialize Redis connection pool."""
        if self.is_connected:
            return

        try:
            # Ensure url is not None
            if self.url is None:
                raise ValueError("Redis URL cannot be None")

            # Create connection pool with retry strategy
            retry = Retry(ExponentialBackoff(), self.max_retries)

            # Get base connection kwargs from shared factory (handles SSL, TLS validation)
            pool_kwargs = get_redis_connection_kwargs(
                self.url,
                decode_responses=False,  # We handle JSON serialization
                max_connections=self.max_connections,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                retry=retry,
            )

            self.pool = ConnectionPool.from_url(self.url, **pool_kwargs)

            self.client = Redis(connection_pool=self.pool)

            # Test connection
            await self.client.ping()
            self.is_connected = True

        except (RedisConnectionError, RedisTimeoutError, RedisError) as e:
            self.is_connected = False
            # Clean up resources on failure to prevent leaks
            if self.client:
                try:
                    await self.client.aclose()
                except RedisError:
                    pass
                self.client = None
            if self.pool:
                try:
                    await self.pool.aclose()
                except RedisError:
                    pass
                self.pool = None
            raise RedisConnectionError(f"Failed to connect to Redis: {e}") from e

    async def stop(self) -> None:
        """Close Redis connection and cleanup resources."""
        if not self.is_connected:
            return

        try:
            # Cancel all subscription tasks first
            for task in self.subscription_tasks:
                if not task.done():
                    task.cancel()

            # Wait for all tasks to complete or be cancelled
            if self.subscription_tasks:
                await asyncio.gather(*self.subscription_tasks, return_exceptions=True)
                self.subscription_tasks.clear()

            if self.client:
                await self.client.aclose()
                self.client = None

            if self.pool:
                await self.pool.aclose()
                self.pool = None

            self.is_connected = False

        except RedisError:
            pass

    async def _ensure_connected(self) -> bool:
        """Ensure Redis connection is alive and reconnect if needed."""
        if not self.is_connected or not self.client:
            try:
                await self.start()
                return True
            except (RedisConnectionError, RedisTimeoutError, RedisError):
                return False

        try:
            await self.client.ping()
            return True
        except (RedisConnectionError, RedisTimeoutError, RedisError):
            self.is_connected = False
            try:
                await self.start()
                return True
            except (RedisConnectionError, RedisTimeoutError, RedisError):
                return False

    async def get(  # noqa: PLR0911
        self,
        key: str,
        default: T | None = None,
        value_type: type[T] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> T | None:
        """Get a value from the cache with optional type and schema validation."""
        if not await self._ensure_connected():
            return default

        assert self.client is not None  # Type narrowing after connection check

        try:
            full_key = self._build_key(key)
            value = await self.client.get(full_key)

            if value is None:
                self.metrics.misses += 1
                return default

            deserialized = orjson.loads(value)

            if schema is not None:
                try:
                    validated = schema.model_validate(deserialized)
                    self.metrics.hits += 1
                    return cast(T, validated)
                except ValidationError as e:
                    logger.error(
                        f"Cache validation failed for key {key}: {e.error_count()} errors",
                        extra={"key": key, "errors": e.errors()},
                    )
                    self.metrics.misses += 1
                    return default

            if value_type is not None and not isinstance(deserialized, value_type):
                logger.warning(
                    f"Type mismatch for key {key}: expected {value_type.__name__}, "
                    f"got {type(deserialized).__name__}"
                )
                self.metrics.misses += 1
                return default

            self.metrics.hits += 1
            return cast(T, deserialized)

        except orjson.JSONDecodeError as e:
            logger.warning(
                f"Failed to deserialize cached value for key '{key}': {e}",
                extra={"key": key, "error_type": "json_decode"},
            )
            self.metrics.misses += 1
            return default
        except RedisError as e:
            logger.error(
                f"Redis error getting key '{key}': {e}",
                extra={"key": key, "error_type": "redis"},
            )
            self.metrics.misses += 1
            return default

    async def set(self, key: str, value: T, ttl: int | None = None) -> bool:
        """Set a value in the cache."""
        if not await self._ensure_connected():
            return False

        assert self.client is not None  # Type narrowing after connection check

        try:
            full_key = self._build_key(key)
            effective_ttl = ttl if ttl is not None else self.config.default_ttl

            if effective_ttl < 0:
                logger.warning(
                    f"Invalid TTL value {effective_ttl} for key '{key}', using 0 (no expiration)"
                )
                effective_ttl = 0

            serialized = orjson.dumps(value)

            if effective_ttl > 0:
                await self.client.setex(full_key, effective_ttl, serialized)
            else:
                await self.client.set(full_key, serialized)

            self.metrics.sets += 1
            return True

        except TypeError as e:
            logger.error(
                f"Failed to serialize value for key '{key}': {e}",
                extra={"key": key, "error_type": "json_encode", "value_type": type(value).__name__},
            )
            return False
        except RedisError as e:
            logger.error(
                f"Redis error setting key '{key}': {e}",
                extra={"key": key, "error_type": "redis"},
            )
            return False

    async def delete(self, key: str) -> bool:
        """Delete a value from the cache."""
        if not await self._ensure_connected():
            return False

        assert self.client is not None  # Type narrowing after connection check

        try:
            full_key = self._build_key(key)
            result = await self.client.delete(full_key)
            existed = bool(result > 0)

            if existed:
                self.metrics.deletes += 1

            return existed

        except RedisError:
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        if not await self._ensure_connected():
            return False

        assert self.client is not None  # Type narrowing after connection check

        try:
            full_key = self._build_key(key)
            result = await self.client.exists(full_key)
            return bool(result == 1)

        except RedisError:
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for a key."""
        if not await self._ensure_connected():
            return False

        assert self.client is not None  # Type narrowing after connection check

        try:
            full_key = self._build_key(key)
            result = await self.client.expire(full_key, ttl)
            return bool(result == 1)

        except RedisError:
            return False

    async def mget(self, keys: list[str], schema: type[BaseModel] | None = None) -> list[T | None]:
        """Get multiple values from the cache with optional schema validation."""
        if not keys:
            return []
        if not await self._ensure_connected():
            return [None] * len(keys)

        assert self.client is not None  # Type narrowing after connection check

        try:
            full_keys = [self._build_key(k) for k in keys]
            values = await self.client.mget(full_keys)

            result: list[T | None] = []
            for idx, value in enumerate(values):
                if value is None:
                    self.metrics.misses += 1
                    result.append(None)
                else:
                    try:
                        deserialized = orjson.loads(value)

                        if schema is not None:
                            try:
                                validated = schema.model_validate(deserialized)
                                self.metrics.hits += 1
                                result.append(cast(T, validated))
                            except ValidationError as e:
                                logger.error(
                                    f"Cache validation failed for key {keys[idx]}: {e.error_count()} errors"
                                )
                                self.metrics.misses += 1
                                result.append(None)
                        else:
                            self.metrics.hits += 1
                            result.append(cast(T, deserialized))
                    except orjson.JSONDecodeError:
                        self.metrics.misses += 1
                        result.append(None)

            return result

        except RedisError:
            self.metrics.misses += len(keys)
            return [None] * len(keys)

    async def mset(self, items: dict[str, T], ttl: int | None = None) -> bool:
        """Set multiple values in the cache."""
        if not items:
            return False
        if not await self._ensure_connected():
            return False

        assert self.client is not None  # Type narrowing after connection check

        try:
            effective_ttl = ttl if ttl is not None else self.config.default_ttl

            # Use pipeline for atomic operations
            async with self.client.pipeline(transaction=False) as pipe:
                for key, value in items.items():
                    full_key = self._build_key(key)
                    serialized = orjson.dumps(value)

                    if effective_ttl > 0:
                        pipe.setex(full_key, effective_ttl, serialized)
                    else:
                        pipe.set(full_key, serialized)

                await pipe.execute()

            self.metrics.sets += len(items)
            return True

        except (RedisError, orjson.JSONDecodeError):
            return False

    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache entries matching a pattern."""
        if not await self._ensure_connected():
            return 0

        assert self.client is not None  # Type narrowing after connection check

        try:
            match_pattern = self._build_key(pattern) if pattern else self._build_key("*")

            count = 0
            cursor = 0

            while True:
                cursor, keys = await self.client.scan(cursor, match=match_pattern, count=100)

                if keys:
                    deleted = await self.client.delete(*keys)
                    count += deleted

                if cursor == 0:
                    break

            return count

        except RedisError:
            return 0

    async def ping(self) -> bool:
        """Check if the cache is healthy."""
        return await self._ensure_connected()

    def get_metrics(self) -> CacheMetrics:
        """Get cache metrics."""
        return self.metrics

    def _build_key(self, key: str) -> str:
        """Build full key with prefix."""
        return f"{self.config.key_prefix}:{key}" if self.config.key_prefix else key

    async def subscribe(
        self,
        channel: str,
        handler: Callable[[PubSubMessage], None],
        hmac_secret: str | None = None,
    ) -> None:
        """Subscribe to a Redis pub/sub channel with message validation."""
        if not await self._ensure_connected():
            return

        assert self.client is not None  # Type narrowing after connection check

        try:
            pubsub = self.client.pubsub()
            await pubsub.subscribe(channel)

            # Listen for messages in background
            async def listen() -> None:
                try:
                    async for message in pubsub.listen():
                        if message["type"] == "message":
                            raw_data = message["data"].decode("utf-8")

                            if not self._validate_message(raw_data, hmac_secret):
                                logger.warning(
                                    f"Invalid pub/sub message received on channel {channel}"
                                )
                                continue

                            try:
                                validated_message = PubSubMessage.model_validate_json(raw_data)
                                handler(validated_message)
                            except ValidationError as e:
                                logger.error(
                                    f"Failed to parse/validate message on channel {channel}: {e}"
                                )
                                continue

                except asyncio.CancelledError:
                    # Clean shutdown of subscription
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()  # type: ignore[no-untyped-call]
                    raise

            # Store task reference to prevent garbage collection and enable cancellation
            task = asyncio.create_task(listen())
            self.subscription_tasks.append(task)

        except RedisError:
            pass

    def _validate_message(self, raw_data: str, hmac_secret: str | None = None) -> bool:
        """Validate message structure, timestamp, and optional HMAC signature."""
        try:
            message = PubSubMessage.model_validate_json(raw_data)

            current_time = int(time.time())
            message_age = abs(current_time - message.timestamp)

            if message_age > MAX_MESSAGE_AGE_SECONDS:
                logger.warning(
                    f"Message timestamp too old: age={message_age}s, max={MAX_MESSAGE_AGE_SECONDS}s"
                )
                return False

            if hmac_secret and message.signature:
                payload_str = json.dumps(message.payload, sort_keys=True)
                message_to_sign = f"{message.type}:{payload_str}:{message.timestamp}"
                expected_signature = hmac.new(
                    hmac_secret.encode(),
                    message_to_sign.encode(),
                    hashlib.sha256,
                ).hexdigest()

                if not hmac.compare_digest(expected_signature, message.signature):
                    logger.warning("Message HMAC signature verification failed")
                    return False

            return True

        except (orjson.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}")
            return False

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a Redis pub/sub channel."""
        if not await self._ensure_connected():
            return 0

        assert self.client is not None  # Type narrowing after connection check

        try:
            result = await self.client.publish(channel, message.encode("utf-8"))
            return int(result)

        except RedisError:
            return 0
