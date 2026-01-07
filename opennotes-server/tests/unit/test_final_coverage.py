"""Final tests to reach 70% coverage target."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_users_crud_api_key_functions():
    """Test API key related functions."""
    from src.auth.models import APIKeyCreate
    from src.users import crud
    from src.users.models import APIKey

    mock_db = AsyncMock()
    test_user_id = uuid4()
    test_key_id = uuid4()

    # Test create_api_key
    api_key_create = APIKeyCreate(name="Test Key", expires_in_days=30)

    # Mock the refresh
    async def mock_refresh(key):
        key.id = test_key_id
        key.created_at = datetime.now(UTC)

    mock_db.refresh = mock_refresh

    # Mock APIKey.generate_key
    with patch.object(APIKey, "generate_key", return_value=("test_raw_key_123", "test_prefix")):
        api_key, raw_key = await crud.create_api_key(mock_db, test_user_id, api_key_create)

        assert api_key.user_id == test_user_id
        assert api_key.name == "Test Key"
        assert api_key.is_active is True
        assert raw_key == "test_raw_key_123"
        assert mock_db.add.call_count == 2

    # Test create_api_key without expiry
    api_key_create_no_exp = APIKeyCreate(name="Permanent Key")
    mock_db.reset_mock()

    with patch.object(APIKey, "generate_key", return_value=("test_raw_key_456", "test_prefix2")):
        api_key, raw_key = await crud.create_api_key(mock_db, test_user_id, api_key_create_no_exp)

        assert api_key.expires_at is None
        assert raw_key == "test_raw_key_456"


@pytest.mark.asyncio
async def test_users_crud_revoke_api_key():
    """Test revoking API keys."""
    from src.users import crud
    from src.users.models import APIKey

    mock_db = AsyncMock()
    mock_result = MagicMock()

    test_user_id1 = uuid4()
    test_user_id2 = uuid4()
    test_key_id1 = uuid4()
    test_key_id2 = uuid4()

    # Test successful revocation
    api_key = APIKey(
        id=test_key_id1, user_id=test_user_id1, name="Test Key", key_hash="hash", is_active=True
    )
    mock_result.scalar_one_or_none.return_value = api_key
    mock_db.execute.return_value = mock_result

    result = await crud.revoke_api_key(mock_db, test_key_id1, test_user_id1)
    assert result is True
    assert api_key.is_active is False

    # Test wrong user ID
    api_key2 = APIKey(
        id=test_key_id2, user_id=test_user_id2, name="Test Key", key_hash="hash", is_active=True
    )
    mock_result.scalar_one_or_none.return_value = api_key2
    mock_db.reset_mock()

    result = await crud.revoke_api_key(mock_db, test_key_id2, test_user_id1)  # Wrong user
    assert result is False
    assert api_key2.is_active is True  # Should remain active

    # Test key not found
    mock_result.scalar_one_or_none.return_value = None
    mock_db.reset_mock()

    result = await crud.revoke_api_key(mock_db, uuid4(), test_user_id1)
    assert result is False


@pytest.mark.asyncio
async def test_users_crud_verify_api_key():
    """Test API key verification."""
    from src.auth.password import get_password_hash
    from src.users import crud
    from src.users.models import APIKey, User

    mock_db = AsyncMock()

    # Create test data
    raw_key = "test_api_key_123"
    test_user_id = uuid4()
    test_key_id = uuid4()

    user = User(
        id=test_user_id,
        username="test",
        email="test@test.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    api_key = APIKey(
        id=test_key_id,
        user_id=test_user_id,
        name="Test Key",
        key_hash=get_password_hash(raw_key),
        is_active=True,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )

    # Test successful verification
    # Create a call counter
    call_count = [0]

    async def mock_execute_factory(query):
        call_count[0] += 1
        mock_result = MagicMock()

        # First call: select APIKey (returns list via scalars().all())
        if call_count[0] == 1:
            mock_result.scalars.return_value.all.return_value = [api_key]
        # Second call: get_user_by_id (returns single user)
        else:
            mock_result.scalar_one_or_none.return_value = user

        return mock_result

    mock_db.execute = AsyncMock(side_effect=mock_execute_factory)
    mock_db.flush = AsyncMock()

    result = await crud.verify_api_key(mock_db, raw_key)
    assert result is not None
    key, verified_user = result
    assert key == api_key
    assert verified_user == user

    # Test with wrong key
    mock_db.reset_mock()
    mock_result1 = MagicMock()
    mock_result1.scalars.return_value.all.return_value = [api_key]
    mock_db.execute = AsyncMock(return_value=mock_result1)
    mock_db.flush = AsyncMock()

    result = await crud.verify_api_key(mock_db, "wrong_key")
    assert result is None

    # Test with expired key
    api_key.expires_at = datetime.now(UTC) - timedelta(days=1)  # Expired
    mock_db.reset_mock()
    mock_result1.scalars.return_value.all.return_value = [api_key]
    mock_db.execute = AsyncMock(return_value=mock_result1)
    mock_db.flush = AsyncMock()

    result = await crud.verify_api_key(mock_db, raw_key)
    assert result is None

    # Test with inactive user
    api_key.expires_at = datetime.now(UTC) + timedelta(days=30)  # Valid again
    user.is_active = False
    mock_db.reset_mock()

    call_count = [0]

    async def mock_execute_factory_inactive(query):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            mock_result.scalars.return_value.all.return_value = [api_key]
        else:
            mock_result.scalar_one_or_none.return_value = user
        return mock_result

    mock_db.execute = AsyncMock(side_effect=mock_execute_factory_inactive)
    mock_db.flush = AsyncMock()

    result = await crud.verify_api_key(mock_db, raw_key)
    assert result is None


@pytest.mark.asyncio
async def test_create_user():
    """Test user creation."""
    from src.auth.models import UserCreate
    from src.users import crud

    mock_db = AsyncMock()

    # Mock refresh to set ID
    async def mock_refresh(user):
        user.id = uuid4()
        user.created_at = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)

    mock_db.refresh = mock_refresh

    user_create = UserCreate(
        username="newuser",
        email="new@example.com",
        password="TestPassword123!",
        full_name="New User",
    )

    user = await crud.create_user(mock_db, user_create)

    assert user.username == "newuser"
    assert user.email == "new@example.com"
    assert user.full_name == "New User"
    assert user.role == "user"
    assert user.is_active is True
    assert user.is_superuser is False

    assert mock_db.add.call_count == 2
    assert mock_db.flush.call_count == 2
