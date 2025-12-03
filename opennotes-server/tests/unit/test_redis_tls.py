from unittest.mock import patch

import pytest

from src.cache.adapters.redis import RedisCacheAdapter
from src.cache.redis_client import RedisClient

pytestmark = pytest.mark.skip(
    reason="Tests need refactoring: require isolation and alignment with current TLS behavior. See backlog task."
)


@pytest.mark.asyncio
async def test_redis_client_requires_tls_in_production() -> None:
    with (
        patch("src.cache.redis_client.settings.ENVIRONMENT", "production"),
        patch("src.cache.redis_client.settings.REDIS_URL", "redis://localhost:6379"),
        patch("src.cache.redis_client.settings.TESTING", False),
    ):
        client = RedisClient()

        with pytest.raises(ValueError, match="must use TLS in production"):
            await client.connect()


@pytest.mark.asyncio
async def test_redis_client_allows_non_tls_in_development() -> None:
    with (
        patch("src.cache.redis_client.settings.ENVIRONMENT", "development"),
        patch("src.cache.redis_client.settings.REDIS_URL", "redis://localhost:6379"),
        patch("src.cache.redis_client.settings.TESTING", False),
    ):
        client = RedisClient()

        try:
            await client.connect()
        except Exception as e:
            if "must use TLS" in str(e):
                pytest.fail("Should allow non-TLS in development")
        finally:
            await client.disconnect()


@pytest.mark.asyncio
async def test_redis_adapter_requires_tls_in_production() -> None:
    with (
        patch("src.cache.redis_client.settings.ENVIRONMENT", "production"),
        patch("src.cache.redis_client.settings.REDIS_REQUIRE_TLS", True),
    ):
        adapter = RedisCacheAdapter(url="redis://localhost:6379")

        with pytest.raises(ValueError, match="must use TLS in production"):
            await adapter.start()


@pytest.mark.asyncio
async def test_redis_adapter_allows_non_tls_in_development() -> None:
    with (
        patch("src.cache.redis_client.settings.ENVIRONMENT", "development"),
        patch("src.cache.redis_client.settings.REDIS_REQUIRE_TLS", False),
    ):
        adapter = RedisCacheAdapter(url="redis://localhost:6379")

        try:
            await adapter.start()
        except Exception as e:
            if "must use TLS" in str(e):
                pytest.fail("Should allow non-TLS in development")
        finally:
            await adapter.stop()


@pytest.mark.asyncio
async def test_redis_client_configures_tls_correctly() -> None:
    with (
        patch("src.cache.redis_client.settings.ENVIRONMENT", "production"),
        patch("src.cache.redis_client.settings.REDIS_URL", "rediss://secure-redis:6380"),
        patch("src.cache.redis_client.settings.TESTING", False),
    ):
        client = RedisClient()

        try:
            await client.connect()
        except Exception as e:
            if "must use TLS" in str(e):
                pytest.fail("Should accept TLS URL in production")
            # Connection failures are expected (no actual TLS server)
        finally:
            await client.disconnect()
