from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.webhooks.rate_limit import RateLimiter
from tests.redis_mock import create_stateful_redis_mock

pytestmark = pytest.mark.unit


@pytest.fixture
async def limiter():
    rl = RateLimiter()
    rl.redis_client = create_stateful_redis_mock()
    return rl


@pytest.fixture
async def connected_limiter():
    rl = RateLimiter()
    mock_redis = create_stateful_redis_mock()
    rl.redis_client = mock_redis
    return rl


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_init(self):
        rl = RateLimiter()
        assert rl.redis_client is None

    @pytest.mark.asyncio
    async def test_connect(self):
        rl = RateLimiter()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = AsyncMock()
            mock_from_url.return_value = mock_redis

            await rl.connect()

            assert rl.redis_client == mock_redis
            mock_from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        rl = RateLimiter()
        mock_redis = AsyncMock()
        rl.redis_client = mock_redis
        await rl.disconnect()
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        rl = RateLimiter()
        await rl.disconnect()

    @pytest.mark.asyncio
    async def test_check_rate_limit_without_connection(self):
        rl = RateLimiter()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await rl.check_rate_limit("guild_123")

    @pytest.mark.asyncio
    async def test_check_rate_limit_guild_only_allowed(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 50

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            allowed, remaining = await connected_limiter.check_rate_limit(
                platform_community_server_id
            )

        assert allowed is True
        assert remaining == 50
        mock_pipeline.zremrangebyscore.assert_called_once()
        mock_pipeline.zcard.assert_called_once()
        mock_pipeline.zadd.assert_called_once()
        mock_pipeline.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_rate_limit_guild_only_exceeded(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 101

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            allowed, remaining = await connected_limiter.check_rate_limit(
                platform_community_server_id
            )

        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_user_id_allowed(self, connected_limiter):
        platform_community_server_id = "guild_123"
        user_id = "user_456"
        current_count = 25

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            allowed, remaining = await connected_limiter.check_rate_limit(
                platform_community_server_id, user_id
            )

        assert allowed is True
        assert remaining == 75

        calls = mock_pipeline.zremrangebyscore.call_args_list
        assert len(calls) == 1
        key = calls[0][0][0]
        assert f"community_server:{platform_community_server_id}:user:{user_id}" in key

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_user_id_exceeded(self, connected_limiter):
        platform_community_server_id = "guild_123"
        user_id = "user_456"
        current_count = 150

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            allowed, remaining = await connected_limiter.check_rate_limit(
                platform_community_server_id, user_id
            )

        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_pipeline_operations(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 10

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            await connected_limiter.check_rate_limit(platform_community_server_id)

        connected_limiter.redis_client.pipeline.assert_called_once_with(transaction=True)
        mock_pipeline.zremrangebyscore.assert_called_once()
        mock_pipeline.zcard.assert_called_once()
        mock_pipeline.zadd.assert_called_once()
        mock_pipeline.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_rate_limit_edge_case_at_limit(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 99

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            allowed, remaining = await connected_limiter.check_rate_limit(
                platform_community_server_id
            )

        assert allowed is True
        assert remaining == 1

    @pytest.mark.asyncio
    async def test_check_rate_limit_zero_count(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 0

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            allowed, remaining = await connected_limiter.check_rate_limit(
                platform_community_server_id
            )

        assert allowed is True
        assert remaining == 100

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_without_connection(self):
        rl = RateLimiter()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await rl.get_rate_limit_info("guild_123")

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_guild_only(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 30

        connected_limiter.redis_client.zremrangebyscore = AsyncMock()
        connected_limiter.redis_client.zcard = AsyncMock(return_value=current_count)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            info = await connected_limiter.get_rate_limit_info(platform_community_server_id)

        assert info == {"limit": 100, "remaining": 70, "window": 60}

        connected_limiter.redis_client.zremrangebyscore.assert_called_once()
        key = connected_limiter.redis_client.zremrangebyscore.call_args[0][0]
        assert f"community_server:{platform_community_server_id}" in key
        assert "user" not in key

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_with_user_id(self, connected_limiter):
        platform_community_server_id = "guild_123"
        user_id = "user_456"
        current_count = 45

        connected_limiter.redis_client.zremrangebyscore = AsyncMock()
        connected_limiter.redis_client.zcard = AsyncMock(return_value=current_count)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            info = await connected_limiter.get_rate_limit_info(
                platform_community_server_id, user_id
            )

        assert info == {"limit": 100, "remaining": 55, "window": 60}

        key = connected_limiter.redis_client.zremrangebyscore.call_args[0][0]
        assert f"community_server:{platform_community_server_id}:user:{user_id}" in key

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_at_limit(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 100

        connected_limiter.redis_client.zremrangebyscore = AsyncMock()
        connected_limiter.redis_client.zcard = AsyncMock(return_value=current_count)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            info = await connected_limiter.get_rate_limit_info(platform_community_server_id)

        assert info["remaining"] == 0

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_exceeded_limit(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 150

        connected_limiter.redis_client.zremrangebyscore = AsyncMock()
        connected_limiter.redis_client.zcard = AsyncMock(return_value=current_count)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            info = await connected_limiter.get_rate_limit_info(platform_community_server_id)

        assert info["remaining"] == 0

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_zero_count(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 0

        connected_limiter.redis_client.zremrangebyscore = AsyncMock()
        connected_limiter.redis_client.zcard = AsyncMock(return_value=current_count)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            info = await connected_limiter.get_rate_limit_info(platform_community_server_id)

        assert info["remaining"] == 100

    @pytest.mark.asyncio
    async def test_check_rate_limit_exact_enforcement_at_limit(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 100

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            allowed, remaining = await connected_limiter.check_rate_limit(
                platform_community_server_id
            )

        assert allowed is True
        assert remaining == 0
        connected_limiter.redis_client.zrem.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_rate_limit_exact_enforcement_over_limit(self, connected_limiter):
        platform_community_server_id = "guild_123"
        current_count = 101

        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[None, None, current_count, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        connected_limiter.redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        with patch("src.webhooks.rate_limit.settings") as mock_settings:
            mock_settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER = 100
            mock_settings.WEBHOOK_RATE_LIMIT_WINDOW = 60

            allowed, remaining = await connected_limiter.check_rate_limit(
                platform_community_server_id
            )

        assert allowed is False
        assert remaining == 0
        connected_limiter.redis_client.zrem.assert_called_once()
