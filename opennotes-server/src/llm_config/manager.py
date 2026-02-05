"""
LLM client manager with caching and pooling.

Manages LLM provider client instances, providing caching for performance
and coordinating with the encryption service for API key decryption.
"""

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar, cast, overload
from uuid import UUID

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.llm_config.encryption import EncryptionService
from src.llm_config.models import CommunityServerLLMConfig
from src.llm_config.providers.base import LLMProvider
from src.llm_config.providers.factory import LLMProviderFactory
from src.monitoring import get_logger

K = TypeVar("K")
V = TypeVar("V")


class EvictingTTLCache(TTLCache[K, V]):  # type: ignore[misc]
    """
    TTLCache with eviction callback support.

    Extends cachetools.TTLCache to call a cleanup callback whenever
    an item is evicted due to TTL expiration, cache size limits,
    or explicit removal.
    """

    def __init__(
        self,
        maxsize: int,
        ttl: float,
        eviction_callback: Callable[[K, V], None] | None = None,
    ) -> None:
        """
        Initialize cache with eviction callback.

        Args:
            maxsize: Maximum number of items in cache
            ttl: Time-to-live in seconds
            eviction_callback: Optional callback called with (key, value) on eviction
        """
        super().__init__(maxsize=maxsize, ttl=ttl)
        self.eviction_callback = eviction_callback

    def _evict(self, key: K, value: V) -> None:
        """Call eviction callback if set."""
        if self.eviction_callback:
            self.eviction_callback(key, value)

    def __setitem__(self, key: K, value: V) -> None:
        """Override to trigger eviction callback on replacement."""
        if key in self:
            old_value = self[key]
            super().__setitem__(key, value)
            if old_value is not value:
                self._evict(key, old_value)
        else:
            if len(self) >= self.maxsize:
                evicted_key = next(iter(self))
                evicted_value = self[evicted_key]
                super().__delitem__(evicted_key)
                self._evict(evicted_key, evicted_value)
            super().__setitem__(key, value)

    def __delitem__(self, key: K) -> None:
        """Override to trigger eviction callback on deletion."""
        value = self[key]
        super().__delitem__(key)
        self._evict(key, value)

    @overload
    def pop(self, key: K) -> V: ...

    @overload
    def pop(self, key: K, default: V) -> V: ...

    @overload
    def pop(self, key: K, default: None = None) -> V | None: ...

    def pop(self, key: K, default: V | None = None) -> V | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Override to trigger eviction callback on pop."""
        if key in self:
            value = cast(V, self[key])
            super().__delitem__(key)
            self._evict(key, value)
            return value
        return default

    def clear(self) -> None:
        """Override to trigger eviction callback for all items."""
        items = list(self.items())
        super().clear()
        for key, value in items:
            self._evict(key, value)

    def expire(self, time: float | None = None) -> list[tuple[K, V]]:
        """
        Override to trigger eviction callback for expired items.

        Args:
            time: Current time (default: now)

        Returns:
            List of expired (key, value) pairs
        """
        expired_items = cast(list[tuple[K, V]], super().expire(time))
        for key, value in expired_items:
            self._evict(key, value)
        return expired_items


class LLMClientManager:
    """
    Manages LLM provider client instances with caching.

    Caches initialized LLM clients to avoid repeated decryption and
    initialization overhead. Provides thread-safe access using asyncio locks.

    Attributes:
        encryption_service: Service for decrypting API keys
        client_cache: TTL cache of initialized LLM providers
        locks: Per-key locks for thread-safe cache population
        cache_ttl: Cache time-to-live in seconds
    """

    def __init__(self, encryption_service: EncryptionService, cache_ttl: int = 3600) -> None:
        """
        Initialize client manager.

        Args:
            encryption_service: Encryption service for API key decryption
            cache_ttl: Cache TTL in seconds (default: 1 hour)
        """
        self.encryption_service = encryption_service
        self.client_cache: EvictingTTLCache[tuple[UUID | None, str], LLMProvider[Any, Any]] = (
            EvictingTTLCache(maxsize=1000, ttl=cache_ttl, eviction_callback=self._cleanup_provider)
        )
        self.locks: dict[str, asyncio.Lock] = {}

    def _cleanup_provider(
        self, key: tuple[UUID | None, str], provider: LLMProvider[Any, Any]
    ) -> None:
        """
        Cleanup callback for evicted cache entries.

        Schedules async cleanup of the provider's HTTP client resources
        and removes the corresponding lock to prevent unbounded lock growth.
        This is called synchronously by the cache, so we schedule the async
        cleanup as a background task.

        Args:
            key: Cache key (community_server_id, provider_name)
            provider: LLMProvider instance being evicted
        """
        _task = asyncio.create_task(provider.close())

        lock_key = f"{key[0]}:{key[1]}"
        self.locks.pop(lock_key, None)

    async def get_client(
        self, db: AsyncSession, community_server_id: UUID | None, provider: str
    ) -> LLMProvider[Any, Any] | None:
        """
        Get or create an LLM provider client for the given community and provider.

        Uses caching to avoid repeated database queries and API key decryption.
        Thread-safe via per-key locks.

        When community_server_id is None, uses global API key directly without
        attempting to load community-specific configuration.

        Args:
            db: Database session
            community_server_id: Community server UUID, or None for global fallback
            provider: Provider name ('openai', 'anthropic', etc.)

        Returns:
            Initialized LLM provider instance, or None if not configured

        Raises:
            Exception: If provider initialization fails
        """
        cache_key = (community_server_id, provider)

        if cache_key in self.client_cache:
            return cast(LLMProvider[Any, Any], self.client_cache[cache_key])

        lock_key = f"{community_server_id}:{provider}"
        if lock_key not in self.locks:
            self.locks[lock_key] = asyncio.Lock()

        async with self.locks[lock_key]:
            if cache_key in self.client_cache:
                return cast(LLMProvider[Any, Any], self.client_cache[cache_key])

            client = await self._load_client(db, community_server_id, provider)
            if client:
                self.client_cache[cache_key] = client
            return client

    async def _load_client(
        self, db: AsyncSession, community_server_id: UUID | None, provider: str
    ) -> LLMProvider[Any, Any] | None:
        """
        Load and initialize an LLM client from database configuration.

        Falls back to global API key if no community-specific configuration exists.
        When community_server_id is None, uses global API key directly.

        Args:
            db: Database session
            community_server_id: Community server UUID, or None for global fallback
            provider: Provider name

        Returns:
            Initialized LLM provider, or None if not found/disabled
        """
        config = None
        if community_server_id is not None:
            result = await db.execute(
                select(CommunityServerLLMConfig).where(
                    CommunityServerLLMConfig.community_server_id == community_server_id,
                    CommunityServerLLMConfig.provider == provider,
                    CommunityServerLLMConfig.enabled == True,
                )
            )
            config = result.scalar_one_or_none()

        if not config:
            global_key = self._get_global_api_key(provider)
            if global_key:
                default_model = self._get_default_model(provider)
                logger = get_logger(__name__)
                logger.info(
                    f"Using global {provider} API key",
                    extra={
                        "community_server_id": str(community_server_id)
                        if community_server_id
                        else None,
                        "provider": provider,
                        "api_key_source": "global",
                    },
                )
                return LLMProviderFactory.create(provider, global_key, default_model, {})
            return None

        api_key = self.encryption_service.decrypt_api_key(
            config.api_key_encrypted, config.encryption_key_id
        )

        default_model = config.settings.get("default_model", self._get_default_model(provider))

        logger = get_logger(__name__)
        logger.info(
            f"{provider} client initialized from community configuration",
            extra={
                "community_server_id": str(community_server_id),
                "provider": provider,
                "api_key_source": "community",
            },
        )

        return LLMProviderFactory.create(provider, api_key, default_model, config.settings)

    def _get_default_model(self, provider: str) -> str:
        """
        Get the default model for a provider.

        Uses settings.DEFAULT_FULL_MODEL for OpenAI (extracts model name from provider/model format).

        Args:
            provider: Provider name

        Returns:
            Default model identifier
        """
        if provider == "openai":
            full_model = settings.DEFAULT_FULL_MODEL
            return full_model.split("/")[-1] if "/" in full_model else full_model
        defaults = {
            "anthropic": "claude-3-opus-20240229",
        }
        return defaults.get(provider, "unknown")

    def _get_global_api_key(self, provider: str) -> str | None:
        """
        Get global API key for a provider from environment settings.

        Args:
            provider: Provider name ('openai', 'anthropic', etc.)

        Returns:
            Global API key if configured, None otherwise
        """
        if provider == "openai":
            key: str | None = settings.OPENAI_API_KEY
            return key
        if provider == "anthropic":
            anthropic_key: str | None = getattr(settings, "ANTHROPIC_API_KEY", None)
            return anthropic_key
        return None

    def invalidate_cache(self, community_server_id: UUID, provider: str | None = None) -> None:
        """
        Invalidate cached clients for a community server.

        Removes both the cached client and its corresponding lock to prevent
        unbounded lock growth. Useful after configuration updates.

        Args:
            community_server_id: Community server UUID
            provider: Specific provider to invalidate, or None for all providers
        """
        if provider:
            self.client_cache.pop((community_server_id, provider), None)
            lock_key = f"{community_server_id}:{provider}"
            self.locks.pop(lock_key, None)
        else:
            keys = [k for k in self.client_cache if k[0] == community_server_id]
            for key in keys:
                self.client_cache.pop(key, None)
                lock_key = f"{key[0]}:{key[1]}"
                self.locks.pop(lock_key, None)

    def clear_cache(self) -> None:
        """Clear all cached clients."""
        self.client_cache.clear()
        self.locks.clear()
