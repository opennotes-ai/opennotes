import pytest
from pydantic import BaseModel, Field
from redis.exceptions import ConnectionError as RedisConnectionError

from src.cache.adapters.redis import RedisCacheAdapter


class UserProfile(BaseModel):
    user_id: str
    username: str
    email: str
    age: int = Field(ge=0, le=150)


class InvalidUserProfile(BaseModel):
    user_id: str
    username: str
    different_field: str


@pytest.fixture
async def redis_adapter():
    adapter = RedisCacheAdapter()
    try:
        await adapter.start()
        yield adapter
    except RedisConnectionError:
        pytest.skip("Redis not available")
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_get_with_valid_schema(redis_adapter: RedisCacheAdapter) -> None:
    adapter = redis_adapter

    valid_data = {
        "user_id": "123",
        "username": "alice",
        "email": "alice@example.com",
        "age": 30,
    }

    await adapter.set("user:123", valid_data)

    result = await adapter.get("user:123", schema=UserProfile)

    assert result is not None
    assert isinstance(result, UserProfile)
    assert result.user_id == "123"
    assert result.username == "alice"


@pytest.mark.asyncio
async def test_get_with_invalid_schema_returns_default(redis_adapter: RedisCacheAdapter) -> None:
    adapter = redis_adapter

    invalid_data = {
        "user_id": "123",
        "username": "alice",
        "email": "alice@example.com",
        "age": -5,
    }

    await adapter.set("user:123", invalid_data)

    result = await adapter.get("user:123", default=None, schema=UserProfile)

    assert result is None


@pytest.mark.asyncio
async def test_get_with_missing_field_returns_default(redis_adapter: RedisCacheAdapter) -> None:
    adapter = redis_adapter

    incomplete_data = {
        "user_id": "123",
        "username": "alice",
    }

    await adapter.set("user:123", incomplete_data)

    result = await adapter.get("user:123", default=None, schema=UserProfile)

    assert result is None


@pytest.mark.asyncio
async def test_get_with_wrong_type_returns_default(redis_adapter: RedisCacheAdapter) -> None:
    adapter = redis_adapter

    wrong_type_data = {
        "user_id": "123",
        "username": "alice",
        "email": "alice@example.com",
        "age": "thirty",
    }

    await adapter.set("user:123", wrong_type_data)

    result = await adapter.get("user:123", default=None, schema=UserProfile)

    assert result is None


@pytest.mark.asyncio
async def test_get_without_schema_returns_raw_data(redis_adapter: RedisCacheAdapter) -> None:
    adapter = redis_adapter

    data = {"key": "value", "number": 42}

    await adapter.set("raw:data", data)

    result = await adapter.get("raw:data")

    assert result == data
    assert not isinstance(result, BaseModel)


@pytest.mark.asyncio
async def test_mget_with_valid_schema(redis_adapter: RedisCacheAdapter) -> None:
    adapter = redis_adapter

    user1 = {
        "user_id": "1",
        "username": "alice",
        "email": "alice@example.com",
        "age": 30,
    }
    user2 = {
        "user_id": "2",
        "username": "bob",
        "email": "bob@example.com",
        "age": 25,
    }

    await adapter.set("user:1", user1)
    await adapter.set("user:2", user2)

    results = await adapter.mget(["user:1", "user:2"], schema=UserProfile)

    assert len(results) == 2
    assert isinstance(results[0], UserProfile)
    assert isinstance(results[1], UserProfile)
    assert results[0].username == "alice"
    assert results[1].username == "bob"


@pytest.mark.asyncio
async def test_mget_with_mixed_valid_invalid(redis_adapter: RedisCacheAdapter) -> None:
    adapter = redis_adapter

    valid_user = {
        "user_id": "1",
        "username": "alice",
        "email": "alice@example.com",
        "age": 30,
    }
    invalid_user = {
        "user_id": "2",
        "username": "bob",
        "email": "bob@example.com",
        "age": -5,
    }

    await adapter.set("user:1", valid_user)
    await adapter.set("user:2", invalid_user)

    results = await adapter.mget(["user:1", "user:2"], schema=UserProfile)

    assert len(results) == 2
    assert isinstance(results[0], UserProfile)
    assert results[1] is None


@pytest.mark.asyncio
async def test_cache_poisoning_scenario(redis_adapter: RedisCacheAdapter) -> None:
    adapter = redis_adapter

    malicious_data = {
        "user_id": "123",
        "username": "attacker",
        "email": "attacker@example.com",
        "age": 200,
    }

    await adapter.set("user:123", malicious_data)

    result = await adapter.get("user:123", schema=UserProfile)

    assert result is None
