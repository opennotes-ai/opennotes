"""
Tests for task-242: Verify Redis adapter has type validation for deserialized cache values.

These tests verify that the RedisCacheAdapter:
1. Has optional value_type parameter in get() method
2. Validates deserialized value matches expected type
3. Returns default on type mismatch
4. Logs warning for type mismatches
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.cache.adapters.redis import RedisCacheAdapter


@pytest.fixture
def redis_adapter():
    """Create Redis adapter instance for testing."""
    return RedisCacheAdapter(
        host="localhost",
        port=6379,
    )


@pytest.mark.asyncio
async def test_get_with_value_type_parameter(redis_adapter):
    """Test that get() method accepts value_type parameter."""
    # Mock _ensure_connected
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        # Mock client.get to return a dict
        mock_client = AsyncMock()
        import json

        mock_data = {"key": "value", "number": 42}
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        # Call get with value_type parameter
        result = await redis_adapter.get("test_key", value_type=dict)

        # Verify result matches expected type
        assert result == mock_data
        assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_type_validation_success(redis_adapter):
    """Test that type validation passes when types match."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store a list
        mock_data = [1, 2, 3, 4, 5]
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        # Request with correct type
        result = await redis_adapter.get("test_key", value_type=list)

        # Verify result is returned
        assert result == mock_data
        assert isinstance(result, list)


@pytest.mark.asyncio
async def test_type_validation_mismatch_returns_default(redis_adapter):
    """Test that type mismatch returns default value."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store a dict but expect a list
        mock_data = {"key": "value"}
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        default_value = []

        # Request with incorrect type
        result = await redis_adapter.get("test_key", default=default_value, value_type=list)

        # Verify default is returned
        assert result == default_value


@pytest.mark.asyncio
async def test_type_mismatch_logs_warning(redis_adapter, caplog):
    """Test that type mismatches are logged with warnings."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store a string but expect a dict
        mock_data = "just a string"
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        # Request with incorrect type
        with caplog.at_level("WARNING"):
            await redis_adapter.get("test_key", value_type=dict)

            # Verify warning was logged
            assert any("Type mismatch" in record.message for record in caplog.records)
            assert any("test_key" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_type_validation_with_int(redis_adapter):
    """Test type validation with int type."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store an int
        mock_data = 12345
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        # Request with correct type
        result = await redis_adapter.get("test_key", value_type=int)

        # Verify result is returned
        assert result == mock_data
        assert isinstance(result, int)


@pytest.mark.asyncio
async def test_type_validation_with_str(redis_adapter):
    """Test type validation with str type."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store a string
        mock_data = "test string"
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        # Request with correct type
        result = await redis_adapter.get("test_key", value_type=str)

        # Verify result is returned
        assert result == mock_data
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_type_validation_mismatch_increments_misses(redis_adapter):
    """Test that type mismatch increments cache miss metric."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store dict but expect list
        mock_data = {"key": "value"}
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        initial_misses = redis_adapter.metrics.misses

        # Request with incorrect type
        await redis_adapter.get("test_key", value_type=list)

        # Verify misses incremented
        assert redis_adapter.metrics.misses == initial_misses + 1


@pytest.mark.asyncio
async def test_no_type_validation_when_value_type_none(redis_adapter):
    """Test that no type validation occurs when value_type is None."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store any type
        mock_data = {"mixed": [1, "two", 3.0]}
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        # Request without value_type (should accept any type)
        result = await redis_adapter.get("test_key")

        # Verify result is returned without validation
        assert result == mock_data


@pytest.mark.asyncio
async def test_type_validation_with_bool(redis_adapter):
    """Test type validation with bool type."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store a bool
        mock_data = True
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        # Request with correct type
        result = await redis_adapter.get("test_key", value_type=bool)

        # Verify result is returned
        assert result is True
        assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_type_validation_with_nested_structures(redis_adapter):
    """Test type validation with nested dict/list structures."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        import json

        # Store nested structure
        mock_data = {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}
        mock_client.get = AsyncMock(return_value=json.dumps(mock_data).encode("utf-8"))
        redis_adapter.client = mock_client

        # Request with correct top-level type
        result = await redis_adapter.get("test_key", value_type=dict)

        # Verify result is returned with correct structure
        assert result == mock_data
        assert isinstance(result, dict)
        assert isinstance(result["users"], list)


@pytest.mark.asyncio
async def test_type_validation_with_none_value(redis_adapter):
    """Test that None value (cache miss) doesn't trigger type validation."""
    with patch.object(redis_adapter, "_ensure_connected", new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = True

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)  # Cache miss
        redis_adapter.client = mock_client

        default_value = []

        # Request with value_type but key doesn't exist
        result = await redis_adapter.get("missing_key", default=default_value, value_type=list)

        # Verify default is returned without type validation attempt
        assert result == default_value
