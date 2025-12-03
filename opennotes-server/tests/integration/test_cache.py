import pytest

from src.cache.cache import cache_manager, cached
from src.cache.redis_client import redis_client


@pytest.fixture
async def setup_redis():
    await redis_client.connect()
    await cache_manager._ensure_started()
    yield
    await cache_manager.cache.clear()
    await cache_manager.cache.stop()
    cache_manager._started = False
    if redis_client.client:
        await redis_client.client.flushdb()
    await redis_client.disconnect()


@pytest.mark.asyncio
async def test_redis_connection(setup_redis):
    assert await redis_client.ping() is True


@pytest.mark.asyncio
async def test_redis_set_get(setup_redis):
    success = await redis_client.set("test_key", "test_value", ttl=60)
    assert success is True

    value = await redis_client.get("test_key")
    assert value == "test_value"


@pytest.mark.asyncio
async def test_redis_delete(setup_redis):
    await redis_client.set("test_key", "test_value")
    count = await redis_client.delete("test_key")
    assert count == 1

    value = await redis_client.get("test_key")
    assert value is None


@pytest.mark.asyncio
async def test_cache_manager_set_get(setup_redis):
    data = {"user_id": 123, "name": "Test User"}
    success = await cache_manager.set("test:user:123", data, ttl=60)
    assert success is True

    cached_data = await cache_manager.get("test:user:123")
    assert cached_data == data


@pytest.mark.asyncio
async def test_cache_manager_invalidate_pattern(setup_redis):
    await cache_manager.set("test:user:1", {"id": 1})
    await cache_manager.set("test:user:2", {"id": 2})
    await cache_manager.set("other:data", {"id": 3})

    count = await cache_manager.invalidate_pattern("test:user:*")
    assert count == 2

    assert await cache_manager.get("test:user:1") is None
    assert await cache_manager.get("other:data") is not None


@pytest.mark.asyncio
async def test_cached_decorator(setup_redis):
    call_count = 0

    @cached(prefix="test_func", ttl=60)
    async def expensive_function(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

    result1 = await expensive_function(5)
    assert result1 == 10
    assert call_count == 1

    result2 = await expensive_function(5)
    assert result2 == 10
    assert call_count == 1

    result3 = await expensive_function(10)
    assert result3 == 20
    assert call_count == 2


@pytest.mark.asyncio
async def test_redis_ttl(setup_redis):
    await redis_client.set("test_key", "value", ttl=60)
    ttl = await redis_client.ttl("test_key")
    assert ttl > 0
    assert ttl <= 60


@pytest.mark.asyncio
async def test_redis_exists(setup_redis):
    await redis_client.set("test_key", "value")
    exists = await redis_client.exists("test_key")
    assert exists == 1

    exists = await redis_client.exists("nonexistent_key")
    assert exists == 0
