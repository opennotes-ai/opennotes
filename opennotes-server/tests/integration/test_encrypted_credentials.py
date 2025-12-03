"""
Tests for encrypted credentials field in UserIdentity model.

Verifies that the EncryptedJSONB type correctly encrypts and decrypts
sensitive credential data.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.profile_crud import create_identity, create_profile
from src.users.profile_schemas import AuthProvider, UserIdentityCreate, UserProfileCreate


@pytest.mark.asyncio
class TestEncryptedCredentials:
    async def test_credentials_are_encrypted_in_database(self, db: AsyncSession):
        """Verify that credentials are actually encrypted in the database."""
        profile_create = UserProfileCreate(display_name="encryption_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        test_credentials = {
            "email": "test@example.com",
            "hashed_password": "bcrypt_hash_here",
            "auth_token": "sensitive_token",
        }

        identity_create = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.EMAIL,
            provider_user_id="test@example.com",
            credentials=test_credentials,
        )

        identity = await create_identity(db, identity_create)
        await db.commit()

        result = await db.execute(
            text("SELECT credentials FROM user_identities WHERE id = :id"),
            {"id": identity.id},
        )
        raw_credentials = result.scalar_one()

        assert raw_credentials is not None
        assert isinstance(raw_credentials, dict)
        assert "encrypted" in raw_credentials
        assert "email" not in str(raw_credentials)
        assert "hashed_password" not in str(raw_credentials)
        assert "sensitive_token" not in str(raw_credentials)

    async def test_credentials_decrypt_correctly(self, db: AsyncSession):
        """Verify that encrypted credentials decrypt correctly when read via ORM."""
        profile_create = UserProfileCreate(display_name="decrypt_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        original_credentials = {
            "provider_id": "github123",
            "access_token": "ghp_token_here",
            "refresh_token": "refresh_token_here",
            "nested": {"key": "value", "number": 42},
        }

        identity_create = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.GITHUB,
            provider_user_id="github123",
            credentials=original_credentials,
        )

        identity = await create_identity(db, identity_create)
        await db.commit()

        await db.refresh(identity)

        assert identity.credentials == original_credentials
        assert identity.credentials["provider_id"] == "github123"
        assert identity.credentials["access_token"] == "ghp_token_here"
        assert identity.credentials["nested"]["key"] == "value"
        assert identity.credentials["nested"]["number"] == 42

    async def test_credentials_none_value(self, db: AsyncSession):
        """Verify that None credentials are handled correctly."""
        profile_create = UserProfileCreate(display_name="none_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        identity_create = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.DISCORD,
            provider_user_id="discord999",
            credentials=None,
        )

        identity = await create_identity(db, identity_create)
        await db.commit()

        await db.refresh(identity)

        assert identity.credentials is None

    async def test_credentials_update_encrypts_new_data(self, db: AsyncSession):
        """Verify that updating credentials encrypts the new data."""
        profile_create = UserProfileCreate(display_name="update_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        initial_credentials = {"version": "v1", "token": "token_v1"}

        identity_create = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.EMAIL,
            provider_user_id="update@example.com",
            credentials=initial_credentials,
        )

        identity = await create_identity(db, identity_create)
        await db.commit()

        updated_credentials = {"version": "v2", "token": "token_v2", "new_field": "new_value"}
        identity.credentials = updated_credentials
        await db.commit()
        await db.refresh(identity)

        assert identity.credentials == updated_credentials
        assert identity.credentials["version"] == "v2"
        assert identity.credentials["new_field"] == "new_value"

        result = await db.execute(
            text("SELECT credentials FROM user_identities WHERE id = :id"),
            {"id": identity.id},
        )
        raw_credentials = result.scalar_one()

        assert "encrypted" in raw_credentials
        assert "token_v2" not in str(raw_credentials)

    async def test_empty_dict_credentials(self, db: AsyncSession):
        """Verify that empty dict credentials are handled correctly."""
        profile_create = UserProfileCreate(display_name="empty_dict_test", is_human=True)
        profile = await create_profile(db, profile_create)
        await db.commit()

        identity_create = UserIdentityCreate(
            profile_id=profile.id,
            provider=AuthProvider.DISCORD,
            provider_user_id="discord888",
            credentials={},
        )

        identity = await create_identity(db, identity_create)
        await db.commit()

        await db.refresh(identity)

        assert identity.credentials == {}
