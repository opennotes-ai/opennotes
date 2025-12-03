"""
Cache abstraction interfaces for unified caching across the application.

Provides abstract base classes for cache implementations, supporting both
in-memory and distributed caching strategies with consistent TTL management.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheConfig:
    """Configuration for cache implementations."""

    default_ttl: int = 3600  # 1 hour
    key_prefix: str = ""
    max_size: int | None = None
    eviction_policy: str = "lru"  # lru, fifo
    serializer: str = "json"  # json, pickle, msgpack
    compression: bool = False


@dataclass
class CacheMetrics:
    """Metrics for monitoring cache performance."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    size: int = 0
    memory_bytes: int = 0

    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class CacheInterface(ABC, Generic[T]):
    """
    Abstract base class for cache implementations.

    Provides a unified interface for cache operations across different
    implementations (memory, Redis, etc.).

    Type Parameters:
        T: The type of values stored in the cache

    Example:
        # Cache with string values
        cache: CacheInterface[str] = RedisCacheAdapter()
        await cache.set("key", "value")
        result: str | None = await cache.get("key")

        # Cache with Pydantic models
        cache: CacheInterface[UserModel] = RedisCacheAdapter()
        await cache.set("user:123", user_model)
        user: UserModel | None = await cache.get("user:123")
    """

    @abstractmethod
    async def get(self, key: str, default: T | None = None) -> T | None:
        """
        Get a value from the cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            The cached value or default if not found
        """

    @abstractmethod
    async def set(self, key: str, value: T, ttl: int | None = None) -> bool:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (optional)

        Returns:
            True if successful
        """

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            True if the key existed and was deleted
        """

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache.

        Args:
            key: Cache key

        Returns:
            True if the key exists
        """

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration time for a key.

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            True if successful
        """

    @abstractmethod
    async def mget(self, keys: list[str]) -> list[T | None]:
        """
        Get multiple values from the cache.

        Args:
            keys: List of cache keys

        Returns:
            List of values (None for missing keys)
        """

    @abstractmethod
    async def mset(self, items: dict[str, T], ttl: int | None = None) -> bool:
        """
        Set multiple values in the cache.

        Args:
            items: Dictionary of key-value pairs
            ttl: Time to live in seconds (optional)

        Returns:
            True if successful
        """

    @abstractmethod
    async def clear(self, pattern: str | None = None) -> int:
        """
        Clear cache entries matching a pattern.

        Args:
            pattern: Key pattern (optional, clears all if not provided)

        Returns:
            Number of keys deleted
        """

    @abstractmethod
    async def ping(self) -> bool:
        """
        Check if the cache is healthy.

        Returns:
            True if the cache is operational
        """

    @abstractmethod
    def get_metrics(self) -> CacheMetrics:
        """
        Get cache metrics.

        Returns:
            Current cache metrics
        """

    @abstractmethod
    async def start(self) -> None:
        """Start the cache (for implementations that need initialization)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the cache (cleanup resources)."""


@dataclass
class CacheEntry(Generic[T]):
    """
    Cache entry with expiration metadata for internal cache storage.

    This dataclass is used by cache adapters for internal storage with
    time-based expiration logic. For API/serialization purposes, use
    CacheEntrySchema from src.cache.models.

    Type Parameters:
        T: The type of the cached value

    Attributes:
        value: The cached value
        expires_at: Unix timestamp when entry expires (None for no expiration)
        created_at: Unix timestamp when entry was created
    """

    value: T
    expires_at: float | None = None
    created_at: float = field(default_factory=lambda: __import__("time").time())

    def is_expired(self) -> bool:
        """Check if the entry has expired based on current time."""
        if self.expires_at is None:
            return False
        return bool(__import__("time").time() > self.expires_at)
