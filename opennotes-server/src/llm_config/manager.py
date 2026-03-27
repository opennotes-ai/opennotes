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

from src.config import settings
from src.llm_config.constants import ADC_SENTINEL, get_default_model_for_provider
from src.llm_config.encryption import EncryptionService
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
        self.encryption_service = encryption_service
        self.client_cache: EvictingTTLCache[tuple[None, str], LLMProvider[Any, Any]] = (
            EvictingTTLCache(maxsize=1000, ttl=cache_ttl, eviction_callback=self._cleanup_provider)
        )
        self.locks: dict[str, asyncio.Lock] = {}

    def _cleanup_provider(self, key: tuple[None, str], provider: LLMProvider[Any, Any]) -> None:
        _task = asyncio.create_task(provider.close())

        lock_key = key[1]
        self.locks.pop(lock_key, None)

    async def get_client(self, provider: str) -> LLMProvider[Any, Any] | None:
        cache_key = (None, provider)

        if cache_key in self.client_cache:
            return cast(LLMProvider[Any, Any], self.client_cache[cache_key])

        lock_key = provider
        if lock_key not in self.locks:
            self.locks[lock_key] = asyncio.Lock()

        async with self.locks[lock_key]:
            if cache_key in self.client_cache:
                return cast(LLMProvider[Any, Any], self.client_cache[cache_key])

            client = await self._load_client(provider)
            if client:
                self.client_cache[cache_key] = client
            return client

    async def _load_client(self, provider: str) -> LLMProvider[Any, Any] | None:
        global_key = self._get_global_api_key(provider)
        if global_key:
            default_model = self._get_default_model(provider)
            logger = get_logger(__name__)
            logger.info(
                f"Using global {provider} API key",
                extra={
                    "provider": provider,
                    "api_key_source": "global",
                },
            )
            return LLMProviderFactory.create(provider, global_key, default_model, {})
        return None

    def _get_default_model(self, provider: str) -> str:
        return get_default_model_for_provider(provider)

    def _get_global_api_key(self, provider: str) -> str | None:
        """
        Get global API key for a provider from environment settings.

        Args:
            provider: Provider name ('openai', 'anthropic', 'vertex_ai', etc.)

        Returns:
            Global API key if configured, None otherwise.
            Returns ADC_SENTINEL for vertex_ai/gemini (Application Default Credentials).
        """
        if provider == "openai":
            key: str | None = settings.OPENAI_API_KEY
            return key
        if provider == "anthropic":
            anthropic_key: str | None = getattr(settings, "ANTHROPIC_API_KEY", None)
            return anthropic_key
        if provider in ("vertex_ai", "gemini"):
            if settings.VERTEXAI_PROJECT:
                return ADC_SENTINEL
            return None
        return None

    def invalidate_cache(self, community_server_id: UUID, provider: str | None = None) -> None:  # noqa: ARG002
        if provider:
            self.client_cache.pop((None, provider), None)
            self.locks.pop(provider, None)
        else:
            self.clear_cache()

    def clear_cache(self) -> None:
        """Clear all cached clients."""
        self.client_cache.clear()
        self.locks.clear()
