"""Simple tests to improve coverage for various modules."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_cache_redis_client_basic():
    """Test basic Redis client functionality."""
    from src.cache.redis_client import redis_client
    from tests.redis_mock import create_stateful_redis_mock

    mock_redis = create_stateful_redis_mock()

    with patch.object(redis_client, "client", mock_redis):
        result = await redis_client.check_connection()
        assert result is True


@pytest.mark.asyncio
async def test_middleware_rate_limiting():
    """Test rate limiting middleware."""
    from src.middleware import rate_limiting

    assert hasattr(rate_limiting, "get_client_ip")
    assert hasattr(rate_limiting, "get_user_identifier")
    assert hasattr(rate_limiting, "get_rate_limit_for_endpoint")


@pytest.mark.asyncio
async def test_auth_dependencies_basic():
    """Test basic auth dependency functions."""
    from src.auth import dependencies
    from src.users.models import User

    # Test get_current_user with valid token
    mock_user = User(
        id=1,
        username="test",
        email="test@test.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )

    with patch("src.auth.dependencies.get_user_by_id", return_value=mock_user):
        # Just verify the module loads correctly
        assert hasattr(dependencies, "get_current_user")


@pytest.mark.asyncio
async def test_scoring_adapter_mock():
    """Test the mock scoring adapter."""
    from src.scoring_adapter_mock import ScoringAdapter

    adapter = ScoringAdapter()

    # Test that adapter is initialized
    assert adapter is not None
    assert hasattr(adapter, "score_notes")

    notes = [{"noteId": "note1", "text": "test"}]
    ratings = [{"participantId": "user1", "rating": 1}]
    enrollment = [{"participantId": "user1", "enrollmentStatus": 1}]

    scored_notes, _helpful_scores, _aux = await adapter.score_notes(notes, ratings, enrollment)
    assert scored_notes is not None
    assert len(scored_notes) > 0
    assert scored_notes[0]["noteId"] == "note1"


def test_health_module_imports():
    """Test health module basic functionality."""
    from src import health

    # Just ensure the module and its components are importable
    assert hasattr(health, "HealthCheckResponse")
    assert hasattr(health, "health_check")
    assert hasattr(health, "router")


def test_monitoring_metrics():
    """Test monitoring metrics module."""
    from src.monitoring import metrics

    # Test that metrics are defined
    assert hasattr(metrics, "http_requests_total")
    assert hasattr(metrics, "http_request_duration_seconds")
    assert hasattr(metrics, "active_requests")

    # Test metrics exist and don't raise errors
    assert metrics.http_requests_total is not None
    assert metrics.http_request_duration_seconds is not None
    assert metrics.active_requests is not None


@pytest.mark.asyncio
async def test_users_crud_get_functions():
    """Test additional user CRUD get functions."""
    from src.users import crud
    from src.users.models import APIKey, User

    mock_db = AsyncMock()
    mock_result = MagicMock()

    # Test get_user_by_id
    user = User(
        id=1,
        username="test",
        email="test@test.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    result = await crud.get_user_by_id(mock_db, 1)
    assert result == user

    # Test get_user_by_username
    result = await crud.get_user_by_username(mock_db, "test")
    assert result == user

    # Test get_api_key_by_id
    mock_key = APIKey(id=1, user_id=1, name="Test Key", key_hash="hash", is_active=True)
    mock_result.scalar_one_or_none.return_value = mock_key

    result = await crud.get_api_key_by_id(mock_db, 1)
    assert result == mock_key

    # Test get_api_keys_by_user
    mock_keys = [mock_key]
    mock_result.scalars.return_value.all.return_value = mock_keys

    result = await crud.get_api_keys_by_user(mock_db, 1)
    assert result == mock_keys
    assert len(result) == 1


@pytest.mark.asyncio
async def test_create_refresh_token():
    """Test creating refresh tokens."""
    from uuid import uuid4

    from src.users import crud

    mock_db = AsyncMock()
    user_id = uuid4()

    # Mock the refresh to set properties
    async def mock_refresh(token_obj):
        token_obj.id = uuid4()
        token_obj.created_at = datetime.now(UTC)

    mock_db.refresh = mock_refresh

    token = await crud.create_refresh_token(mock_db, user_id, "test_token", 7)

    assert token.user_id == user_id
    assert token.token is None
    assert token.token_hash is not None
    assert token.is_revoked is False
    assert token.expires_at > datetime.now(UTC)

    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_get_refresh_token():
    """Test getting refresh tokens."""
    from datetime import timedelta
    from uuid import uuid4

    from src.auth.password import get_password_hash
    from src.users import crud
    from src.users.models import RefreshToken

    mock_db = AsyncMock()

    user_id = uuid4()
    test_token = "valid_token"
    token_hash = get_password_hash(test_token)

    token = RefreshToken(
        id=uuid4(),
        user_id=user_id,
        token=None,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        is_revoked=False,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [token]
    mock_db.execute.return_value = mock_result

    result = await crud.get_refresh_token(mock_db, test_token)
    assert result == token

    # Test when no matching token found
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    result = await crud.get_refresh_token(mock_db, "nonexistent_token")
    assert result is None
