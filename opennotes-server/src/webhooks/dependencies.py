from collections.abc import AsyncGenerator

from src.webhooks.cache import InteractionCache, interaction_cache
from src.webhooks.rate_limit import RateLimiter, rate_limiter


async def get_interaction_cache() -> AsyncGenerator[InteractionCache, None]:
    yield interaction_cache


async def get_rate_limiter() -> AsyncGenerator[RateLimiter, None]:
    yield rate_limiter


async def get_new_interaction_cache() -> AsyncGenerator[InteractionCache, None]:
    async with InteractionCache() as cache:
        yield cache


async def get_new_rate_limiter() -> AsyncGenerator[RateLimiter, None]:
    async with RateLimiter() as limiter:
        yield limiter
