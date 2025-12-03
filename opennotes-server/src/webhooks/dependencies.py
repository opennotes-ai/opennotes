from collections.abc import AsyncGenerator

from src.webhooks.cache import InteractionCache, interaction_cache
from src.webhooks.queue import TaskQueue, task_queue
from src.webhooks.rate_limit import RateLimiter, rate_limiter


async def get_interaction_cache() -> AsyncGenerator[InteractionCache, None]:
    yield interaction_cache


async def get_task_queue() -> AsyncGenerator[TaskQueue, None]:
    yield task_queue


async def get_rate_limiter() -> AsyncGenerator[RateLimiter, None]:
    yield rate_limiter


async def get_new_interaction_cache() -> AsyncGenerator[InteractionCache, None]:
    async with InteractionCache() as cache:
        yield cache


async def get_new_task_queue() -> AsyncGenerator[TaskQueue, None]:
    async with TaskQueue() as queue:
        yield queue


async def get_new_rate_limiter() -> AsyncGenerator[RateLimiter, None]:
    async with RateLimiter() as limiter:
        yield limiter
