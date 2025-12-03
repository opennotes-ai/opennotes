"""Simple tests for user CRUD operations to improve coverage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.auth.password import get_password_hash, verify_password
from src.users.models import User


class TestPasswordFunctions:
    """Test password hashing and verification."""

    def test_password_hash_and_verify(self):
        """Test password hashing and verification."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed != password
        is_valid, _ = verify_password(password, hashed)
        assert is_valid
        is_valid, _ = verify_password("wrong_password", hashed)
        assert not is_valid

    def test_password_hash_different_each_time(self):
        """Test that hashing same password produces different hashes."""
        password = "test_password_123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2
        is_valid1, _ = verify_password(password, hash1)
        is_valid2, _ = verify_password(password, hash2)
        assert is_valid1
        assert is_valid2


class TestUserModel:
    """Test User model functionality."""

    def test_user_creation(self):
        """Test creating a user instance."""
        test_user_id = uuid4()
        user = User(
            id=test_user_id,
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_pwd",
            role="user",
            is_active=True,
            is_superuser=False,
        )

        assert user.id == test_user_id
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.is_superuser is False

    def test_user_with_optional_fields(self):
        """Test user with optional fields."""
        test_user_id = uuid4()
        user = User(
            id=test_user_id,
            username="user2",
            email="user2@example.com",
            hashed_password="hashed",
            full_name="User Two",
            discord_id="discord123",
            role="admin",
            is_active=True,
            is_superuser=True,
        )

        assert user.full_name == "User Two"
        assert user.discord_id == "discord123"
        assert user.role == "admin"
        assert user.is_superuser is True


@pytest.mark.asyncio
async def test_simple_user_operations():
    """Test simple user operations to improve coverage."""
    from src.users import crud

    # Create a mock database session
    mock_db = AsyncMock()
    mock_result = MagicMock()

    # Test get_user_by_email
    test_user_id = uuid4()
    user = User(
        id=test_user_id,
        username="test",
        email="test@test.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    result = await crud.get_user_by_email(mock_db, "test@test.com")
    assert result == user

    # Test when user not found
    mock_result.scalar_one_or_none.return_value = None
    result = await crud.get_user_by_email(mock_db, "notfound@test.com")
    assert result is None


@pytest.mark.asyncio
async def test_get_user_by_discord_id():
    """Test getting user by Discord ID."""
    from src.users import crud

    mock_db = AsyncMock()
    mock_result = MagicMock()

    test_user_id = uuid4()
    user = User(
        id=test_user_id,
        username="test",
        email="test@test.com",
        hashed_password="hash",
        discord_id="discord123",
        role="user",
        is_active=True,
    )

    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    result = await crud.get_user_by_discord_id(mock_db, "discord123")
    assert result == user

    # Test when not found
    mock_result.scalar_one_or_none.return_value = None
    result = await crud.get_user_by_discord_id(mock_db, "notfound")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user():
    """Test user authentication."""
    from src.users import crud

    mock_db = AsyncMock()
    mock_result = MagicMock()

    # Create a user with known password
    password = "test_password_123"
    test_user_id = uuid4()
    user = User(
        id=test_user_id,
        username="testuser",
        email="test@test.com",
        hashed_password=get_password_hash(password),
        role="user",
        is_active=True,
    )

    # Test successful authentication
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    result = await crud.authenticate_user(mock_db, "testuser", password)
    assert result == user

    # Test wrong password
    result = await crud.authenticate_user(mock_db, "testuser", "wrong_password")
    assert result is None

    # Test user not found
    mock_result.scalar_one_or_none.return_value = None
    result = await crud.authenticate_user(mock_db, "nonexistent", password)
    assert result is None

    # Test inactive user
    user.is_active = False
    mock_result.scalar_one_or_none.return_value = user
    result = await crud.authenticate_user(mock_db, "testuser", password)
    assert result is None


@pytest.mark.asyncio
async def test_update_user():
    """Test updating user information."""
    from src.auth.models import UserUpdate
    from src.users import crud

    mock_db = AsyncMock()

    test_user_id = uuid4()
    user = User(
        id=test_user_id,
        username="testuser",
        email="old@test.com",
        hashed_password=get_password_hash("old_password"),
        full_name="Old Name",
        role="user",
        is_active=True,
    )

    # Test updating email
    update = UserUpdate(email="new@test.com")
    result = await crud.update_user(mock_db, user, update)
    assert result.email == "new@test.com"

    # Test updating full name
    update = UserUpdate(full_name="New Name")
    result = await crud.update_user(mock_db, user, update)
    assert result.full_name == "New Name"

    # Test updating password
    update = UserUpdate(password="NewPassword123!")
    result = await crud.update_user(mock_db, user, update)
    # Check that password was hashed
    is_valid, _ = verify_password("NewPassword123!", result.hashed_password)
    assert is_valid

    # Test updating multiple fields
    update = UserUpdate(
        email="newest@test.com", full_name="Newest Name", password="NewestPassword123!"
    )
    result = await crud.update_user(mock_db, user, update)
    assert result.email == "newest@test.com"
    assert result.full_name == "Newest Name"
    is_valid, _ = verify_password("NewestPassword123!", result.hashed_password)
    assert is_valid


@pytest.mark.asyncio
async def test_revoke_refresh_token():
    """Test revoking refresh tokens."""
    from src.auth.password import get_password_hash
    from src.users import crud
    from src.users.models import RefreshToken

    mock_db = AsyncMock()

    # Test successful revocation
    test_token_id = uuid4()
    test_user_id = uuid4()
    raw_token = "token123"
    token = RefreshToken(
        id=test_token_id,
        user_id=test_user_id,
        token_hash=get_password_hash(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=7),
        is_revoked=False,
    )

    # Setup mock for get_refresh_token - returns list via scalars().all()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [token]
    mock_db.execute.return_value = mock_result

    result = await crud.revoke_refresh_token(mock_db, raw_token)
    assert result is True
    assert token.is_revoked is True

    # Test token not found
    mock_result.scalars.return_value.all.return_value = []
    mock_db.reset_mock()
    mock_db.execute.return_value = mock_result

    result = await crud.revoke_refresh_token(mock_db, "notfound")
    assert result is False


@pytest.mark.asyncio
async def test_revoke_all_user_refresh_tokens():
    """Test revoking all user refresh tokens."""
    from src.users import crud
    from src.users.models import RefreshToken

    mock_db = AsyncMock()
    mock_result = MagicMock()

    # Create multiple tokens
    test_user_id = uuid4()
    tokens = [
        RefreshToken(id=uuid4(), user_id=test_user_id, token="token1", is_revoked=False),
        RefreshToken(id=uuid4(), user_id=test_user_id, token="token2", is_revoked=False),
        RefreshToken(id=uuid4(), user_id=test_user_id, token="token3", is_revoked=False),
    ]

    mock_result.scalars.return_value.all.return_value = tokens
    mock_db.execute.return_value = mock_result

    await crud.revoke_all_user_refresh_tokens(mock_db, test_user_id)

    # Check all tokens are revoked
    for token in tokens:
        assert token.is_revoked is True

    mock_db.flush.assert_called_once()
