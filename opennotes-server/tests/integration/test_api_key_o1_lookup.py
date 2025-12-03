"""
Tests for task-253: Verify API key O(1) lookup performance.

These tests verify that:
1. New format API keys (opk_prefix_secret) use O(1) database lookup
2. Legacy keys fall back to O(n) verification
3. Constant-time dummy verification prevents timing attacks
4. Performance is independent of total API key count
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.auth.models import APIKeyCreate
from src.users.crud import create_api_key, verify_api_key
from src.users.models import APIKey, User


@pytest.fixture
async def test_user(db_session):
    """Create a test user for API key tests."""
    user = User(
        username="testuser_api",
        email="testuser_api@example.com",
        hashed_password="hashed_password_placeholder",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_new_api_key_format_uses_prefix(test_user, db_session):
    """Test that new API keys use the opk_prefix_secret format."""
    # Create a new API key
    api_key, raw_key = await create_api_key(
        db=db_session,
        user_id=test_user.id,
        api_key_create=APIKeyCreate(name="Test API Key", expires_in_days=30),
    )

    # Verify key format
    assert raw_key.startswith("opk_"), "New keys should use opk_ prefix"
    parts = raw_key.split("_", 2)  # Split into max 3 parts: "opk", prefix, secret
    assert len(parts) == 3, "New keys should have format opk_<prefix>_<secret>"
    prefix = parts[1]
    secret = parts[2]
    assert len(prefix) > 0, "Prefix should not be empty"
    assert len(secret) > 0, "Secret should not be empty"

    # Verify key_prefix is stored in database
    assert api_key.key_prefix == prefix, "key_prefix should be stored in database"


@pytest.mark.asyncio
async def test_o1_lookup_uses_key_prefix(test_user, db_session):
    """Test that verify_api_key performs O(1) lookup using key_prefix."""
    # Create API key with new format
    api_key, raw_key = await create_api_key(
        db=db_session,
        user_id=test_user.id,
        api_key_create=APIKeyCreate(name="Test Key", expires_in_days=30),
    )

    # Mock the database query to track what's being queried
    original_execute = db_session.execute
    query_filters = []

    async def track_execute(query):
        # Capture filter conditions
        query_str = str(query)
        query_filters.append(query_str)
        return await original_execute(query)

    db_session.execute = track_execute

    # Verify the key
    result = await verify_api_key(db_session, raw_key)

    # Restore original execute
    db_session.execute = original_execute

    # Verify key was successfully verified
    assert result is not None
    assert result[0].id == api_key.id
    assert result[1].id == test_user.id

    # Verify query used key_prefix (O(1) lookup)
    assert any("key_prefix" in qf for qf in query_filters), "Should query by key_prefix"


@pytest.mark.asyncio
async def test_constant_time_dummy_verification_on_invalid_key(db_session):
    """Test that invalid keys trigger dummy verification to prevent timing attacks."""
    # Create invalid key with correct format but nonexistent prefix
    invalid_key = "opk_nonexistent_secretpart"

    # Mock verify_password to track if it's called
    with patch("src.users.crud.verify_password") as mock_verify:
        mock_verify.return_value = False

        result = await verify_api_key(db_session, invalid_key)

        # Verify result is None (key not found)
        assert result is None

        # Verify dummy verification was called (constant-time operation)
        assert mock_verify.called, "Should perform dummy verification for constant time"


@pytest.mark.asyncio
async def test_performance_independent_of_total_keys(test_user, db_session):
    """Test that verification time is independent of total API key count."""
    # Create multiple API keys for different users
    # This simulates a database with many keys
    for i in range(10):
        other_user = User(
            username=f"other_user_{i}",
            email=f"other_{i}@example.com",
            hashed_password="hashed_password",
            is_active=True,
        )
        db_session.add(other_user)
    await db_session.commit()

    # Get all users
    users_result = await db_session.execute(select(User))
    all_users = users_result.scalars().all()

    # Create API keys for each user
    for user in all_users:
        if user.id != test_user.id:
            await create_api_key(
                db=db_session,
                user_id=user.id,
                api_key_create=APIKeyCreate(name=f"Key for user {user.id}", expires_in_days=30),
            )

    # Now create a key for our test user
    api_key, raw_key = await create_api_key(
        db=db_session,
        user_id=test_user.id,
        api_key_create=APIKeyCreate(name="Test Key", expires_in_days=30),
    )

    # Verify: should still use O(1) lookup regardless of total key count
    import time

    start_time = time.time()
    result = await verify_api_key(db_session, raw_key)
    elapsed_time = time.time() - start_time

    # Verify key was found
    assert result is not None
    assert result[0].id == api_key.id

    # Verification should be fast (< 1 second for O(1) lookup)
    # This is a loose bound since we're not doing precise benchmarking
    assert elapsed_time < 1.0, f"O(1) lookup should be fast, took {elapsed_time}s"


@pytest.mark.asyncio
async def test_backward_compatibility_with_legacy_keys(test_user, db_session):
    """Test that legacy keys (without prefix) still work with fallback verification."""
    # Create a legacy API key (manually, without key_prefix)
    from src.auth.password import get_password_hash

    raw_legacy_key = "legacy_key_without_prefix_format"
    hashed_key = get_password_hash(raw_legacy_key)

    legacy_api_key = APIKey(
        user_id=test_user.id,
        name="Legacy Key",
        key_hash=hashed_key,
        key_prefix=None,  # No prefix for legacy keys
        is_active=True,
    )
    db_session.add(legacy_api_key)
    await db_session.commit()

    # Verify legacy key (should fall back to O(n) verification)
    result = await verify_api_key(db_session, raw_legacy_key)

    # Verify key was found using legacy fallback
    assert result is not None
    assert result[0].id == legacy_api_key.id
    assert result[1].id == test_user.id


@pytest.mark.asyncio
async def test_invalid_key_format_returns_none(db_session):
    """Test that invalid key formats return None gracefully."""
    # Test various invalid formats
    invalid_keys = [
        "not_an_api_key",
        "opk_only_prefix",
        "opk_",
        "",
        "random_string",
    ]

    for invalid_key in invalid_keys:
        result = await verify_api_key(db_session, invalid_key)
        assert result is None, f"Invalid key '{invalid_key}' should return None"


@pytest.mark.asyncio
async def test_expired_key_returns_none(test_user, db_session):
    """Test that expired keys return None even with correct format."""
    from datetime import UTC, datetime, timedelta

    # Create API key that's already expired
    from src.auth.password import get_password_hash

    raw_key = "opk_expiredkey_secretpart"
    hashed_key = get_password_hash(raw_key)

    expired_key = APIKey(
        user_id=test_user.id,
        name="Expired Key",
        key_hash=hashed_key,
        key_prefix="expiredkey",
        expires_at=datetime.now(UTC) - timedelta(days=1),  # Expired yesterday
        is_active=True,
    )
    db_session.add(expired_key)
    await db_session.commit()

    # Attempt to verify expired key
    result = await verify_api_key(db_session, raw_key)

    # Should return None for expired key
    assert result is None, "Expired keys should return None"


@pytest.mark.asyncio
async def test_inactive_key_returns_none(test_user, db_session):
    """Test that inactive keys return None."""
    # Create inactive API key
    api_key, raw_key = await create_api_key(
        db=db_session,
        user_id=test_user.id,
        api_key_create=APIKeyCreate(name="Test Key", expires_in_days=30),
    )

    # Deactivate the key
    api_key.is_active = False
    await db_session.commit()

    # Attempt to verify inactive key
    result = await verify_api_key(db_session, raw_key)

    # Should return None for inactive key
    assert result is None, "Inactive keys should return None"


@pytest.mark.asyncio
async def test_orphaned_api_key_returns_none(db_session):
    """Test that orphaned API keys (user deleted) return None gracefully."""
    from src.auth.password import get_password_hash

    # Create a temporary user and API key, then delete the user
    temp_user = User(
        username="temp_user_orphan",
        email="orphan@example.com",
        hashed_password="hashed_password",
        is_active=True,
    )
    db_session.add(temp_user)
    await db_session.commit()
    await db_session.refresh(temp_user)

    raw_key = "opk_orphanedkey_secretpart"
    hashed_key = get_password_hash(raw_key)

    orphaned_key = APIKey(
        user_id=temp_user.id,
        name="Orphaned Key",
        key_hash=hashed_key,
        key_prefix="orphanedkey",
        is_active=True,
    )
    db_session.add(orphaned_key)
    await db_session.commit()

    # Now delete the user (simulating orphaned key scenario)
    await db_session.delete(temp_user)
    await db_session.commit()

    # Attempt to verify orphaned key
    result = await verify_api_key(db_session, raw_key)

    # Should return None for orphaned key
    assert result is None, "Orphaned keys should return None"
