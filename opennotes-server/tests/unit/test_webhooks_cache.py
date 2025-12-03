import json
from unittest.mock import AsyncMock, patch

import pytest

from src.webhooks.cache import InteractionCache
from tests.redis_mock import create_stateful_redis_mock

pytestmark = pytest.mark.unit


@pytest.fixture
async def cache():
    ic = InteractionCache()
    ic.redis_client = create_stateful_redis_mock()
    return ic


@pytest.fixture
async def connected_cache():
    ic = InteractionCache()
    mock_redis = create_stateful_redis_mock()
    ic.redis_client = mock_redis
    return ic


class TestInteractionCache:
    @pytest.mark.asyncio
    async def test_init(self):
        ic = InteractionCache()
        assert ic.redis_client is None

    @pytest.mark.asyncio
    async def test_connect(self):
        ic = InteractionCache()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_redis = AsyncMock()
            mock_from_url.return_value = mock_redis

            await ic.connect()

            assert ic.redis_client == mock_redis
            mock_from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        ic = InteractionCache()
        mock_redis = AsyncMock()
        ic.redis_client = mock_redis
        await ic.disconnect()
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        ic = InteractionCache()
        await ic.disconnect()

    @pytest.mark.asyncio
    async def test_check_duplicate_without_connection(self):
        ic = InteractionCache()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await ic.check_duplicate("interaction_123")

    @pytest.mark.asyncio
    async def test_check_duplicate_exists(self, connected_cache):
        interaction_id = "interaction_123"
        connected_cache.redis_client.exists = AsyncMock(return_value=1)

        result = await connected_cache.check_duplicate(interaction_id)

        assert result is True
        connected_cache.redis_client.exists.assert_called_once_with(
            f"interaction:seen:{interaction_id}"
        )

    @pytest.mark.asyncio
    async def test_check_duplicate_not_exists(self, connected_cache):
        interaction_id = "interaction_456"
        connected_cache.redis_client.exists = AsyncMock(return_value=0)

        result = await connected_cache.check_duplicate(interaction_id)

        assert result is False
        connected_cache.redis_client.exists.assert_called_once_with(
            f"interaction:seen:{interaction_id}"
        )

    @pytest.mark.asyncio
    async def test_mark_processed_without_connection(self):
        ic = InteractionCache()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await ic.mark_processed("interaction_123")

    @pytest.mark.asyncio
    async def test_mark_processed_success(self, connected_cache):
        interaction_id = "interaction_789"
        connected_cache.redis_client.setex = AsyncMock()

        with patch("src.webhooks.cache.settings") as mock_settings:
            mock_settings.INTERACTION_CACHE_TTL = 300

            await connected_cache.mark_processed(interaction_id)

        connected_cache.redis_client.setex.assert_called_once_with(
            f"interaction:seen:{interaction_id}", 300, "1"
        )

    @pytest.mark.asyncio
    async def test_get_cached_response_without_connection(self):
        ic = InteractionCache()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await ic.get_cached_response("interaction_123")

    @pytest.mark.asyncio
    async def test_get_cached_response_hit(self, connected_cache):
        interaction_id = "interaction_abc"
        response_data = {"type": 4, "data": {"content": "Cached response"}}
        cached_json = json.dumps(response_data)

        connected_cache.redis_client.get = AsyncMock(return_value=cached_json)

        result = await connected_cache.get_cached_response(interaction_id)

        assert result == response_data
        connected_cache.redis_client.get.assert_called_once_with(
            f"interaction:response:{interaction_id}"
        )

    @pytest.mark.asyncio
    async def test_get_cached_response_miss(self, connected_cache):
        interaction_id = "interaction_xyz"
        connected_cache.redis_client.get = AsyncMock(return_value=None)

        result = await connected_cache.get_cached_response(interaction_id)

        assert result is None
        connected_cache.redis_client.get.assert_called_once_with(
            f"interaction:response:{interaction_id}"
        )

    @pytest.mark.asyncio
    async def test_get_cached_response_complex_data(self, connected_cache):
        interaction_id = "interaction_complex"
        response_data = {
            "type": 4,
            "data": {
                "content": "Complex response",
                "embeds": [
                    {
                        "title": "Title",
                        "description": "Description",
                        "fields": [
                            {"name": "Field1", "value": "Value1"},
                            {"name": "Field2", "value": "Value2"},
                        ],
                    }
                ],
                "components": [],
            },
        }
        cached_json = json.dumps(response_data)

        connected_cache.redis_client.get = AsyncMock(return_value=cached_json)

        result = await connected_cache.get_cached_response(interaction_id)

        assert result == response_data
        assert "embeds" in result["data"]
        assert len(result["data"]["embeds"][0]["fields"]) == 2

    @pytest.mark.asyncio
    async def test_cache_response_without_connection(self):
        ic = InteractionCache()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await ic.cache_response("interaction_123", {})

    @pytest.mark.asyncio
    async def test_cache_response_success(self, connected_cache):
        interaction_id = "interaction_def"
        response_data = {"type": 4, "data": {"content": "New response"}}

        connected_cache.redis_client.setex = AsyncMock()

        with patch("src.webhooks.cache.settings") as mock_settings:
            mock_settings.INTERACTION_CACHE_TTL = 300

            await connected_cache.cache_response(interaction_id, response_data)

        connected_cache.redis_client.setex.assert_called_once()
        call_args = connected_cache.redis_client.setex.call_args

        assert call_args[0][0] == f"interaction:response:{interaction_id}"
        assert call_args[0][1] == 300

        cached_data = json.loads(call_args[0][2])
        assert cached_data == response_data

    @pytest.mark.asyncio
    async def test_cache_response_complex_data(self, connected_cache):
        interaction_id = "interaction_complex_cache"
        response_data = {
            "type": 4,
            "data": {
                "content": "Complex data with unicode: 你好 🎉",
                "embeds": [{"title": "Title", "fields": [{"name": "N", "value": "V"}]}],
            },
        }

        connected_cache.redis_client.setex = AsyncMock()

        with patch("src.webhooks.cache.settings") as mock_settings:
            mock_settings.INTERACTION_CACHE_TTL = 300

            await connected_cache.cache_response(interaction_id, response_data)

        call_args = connected_cache.redis_client.setex.call_args
        cached_data = json.loads(call_args[0][2])
        assert cached_data == response_data

    @pytest.mark.asyncio
    async def test_invalidate_cache_without_connection(self):
        ic = InteractionCache()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Redis connection failed")
            with pytest.raises(
                RuntimeError, match="Redis client not connected and reconnection failed"
            ):
                await ic.invalidate_cache("interaction_123")

    @pytest.mark.asyncio
    async def test_invalidate_cache_success(self, connected_cache):
        interaction_id = "interaction_ghi"
        connected_cache.redis_client.delete = AsyncMock()

        await connected_cache.invalidate_cache(interaction_id)

        connected_cache.redis_client.delete.assert_called_once_with(
            f"interaction:response:{interaction_id}", f"interaction:seen:{interaction_id}"
        )

    @pytest.mark.asyncio
    async def test_cache_workflow_integration(self, connected_cache):
        interaction_id = "workflow_test_123"
        response_data = {"type": 4, "data": {"content": "Test"}}

        connected_cache.redis_client.exists = AsyncMock(return_value=0)
        connected_cache.redis_client.setex = AsyncMock()
        connected_cache.redis_client.get = AsyncMock(return_value=json.dumps(response_data))
        connected_cache.redis_client.delete = AsyncMock()

        is_duplicate = await connected_cache.check_duplicate(interaction_id)
        assert is_duplicate is False

        with patch("src.webhooks.cache.settings") as mock_settings:
            mock_settings.INTERACTION_CACHE_TTL = 300
            await connected_cache.mark_processed(interaction_id)

        with patch("src.webhooks.cache.settings") as mock_settings:
            mock_settings.INTERACTION_CACHE_TTL = 300
            await connected_cache.cache_response(interaction_id, response_data)

        cached = await connected_cache.get_cached_response(interaction_id)
        assert cached == response_data

        await connected_cache.invalidate_cache(interaction_id)
        connected_cache.redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_check_after_mark_processed(self, connected_cache):
        interaction_id = "duplicate_check_test"

        connected_cache.redis_client.exists = AsyncMock(side_effect=[0, 1])
        connected_cache.redis_client.setex = AsyncMock()

        is_duplicate_before = await connected_cache.check_duplicate(interaction_id)
        assert is_duplicate_before is False

        with patch("src.webhooks.cache.settings") as mock_settings:
            mock_settings.INTERACTION_CACHE_TTL = 300
            await connected_cache.mark_processed(interaction_id)

        is_duplicate_after = await connected_cache.check_duplicate(interaction_id)
        assert is_duplicate_after is True
