"""
Unit tests for UserIdentity schema serialization with email verification fields.

These tests validate that UserIdentity schemas correctly handle email verification
fields, especially ensuring that sensitive fields (credentials, verification tokens)
are excluded from API responses while email_verified status remains visible.

All tests are pure unit tests with no database dependencies for fast execution.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.users.profile_schemas import (
    UserIdentityInDB,
    UserIdentityResponse,
)

# Mark all tests in this module as unit tests (no database required)
pytestmark = pytest.mark.unit


# Mock ORM class that behaves like SQLAlchemy UserIdentity model
@dataclass
class MockUserIdentity:
    """Mock UserIdentity ORM object for testing."""

    id: UUID
    profile_id: UUID
    provider: str
    provider_user_id: str
    credentials: dict | None
    email_verified: bool
    email_verification_token: str | None
    email_verification_token_expires: datetime | None
    created_at: datetime
    updated_at: datetime | None


class TestUserIdentityInDBSerialization:
    """Test UserIdentityInDB schema includes all fields."""

    def test_user_identity_in_db_includes_all_fields(self):
        """
        UserIdentityInDB should include all fields from the database model,
        including email_verified, email_verification_token, and
        email_verification_token_expires.
        """
        # Create mock ORM object with all fields
        identity_id = uuid4()
        profile_id = uuid4()
        expires_at = datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials={"password_hash": "hashed_password_123"},
            email_verified=False,
            email_verification_token="verification_token_abc123",
            email_verification_token_expires=expires_at,
            created_at=created_at,
            updated_at=None,
        )

        # Convert ORM object to Pydantic InDB model
        in_db = UserIdentityInDB.model_validate(mock_orm)

        # Verify all fields are present
        assert in_db.id == identity_id
        assert in_db.profile_id == profile_id
        assert in_db.provider == "email"
        assert in_db.provider_user_id == "user@example.com"
        assert in_db.credentials == {"password_hash": "hashed_password_123"}
        assert in_db.email_verified is False
        assert in_db.email_verification_token == "verification_token_abc123"
        assert in_db.email_verification_token_expires == expires_at
        assert in_db.created_at == created_at
        assert in_db.updated_at is None

    def test_user_identity_in_db_with_verified_email(self):
        """
        UserIdentityInDB should correctly serialize when email is verified
        (token fields are None).
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="verified@example.com",
            credentials={"password_hash": "hashed_password_456"},
            email_verified=True,
            email_verification_token=None,
            email_verification_token_expires=None,
            created_at=created_at,
            updated_at=None,
        )

        in_db = UserIdentityInDB.model_validate(mock_orm)

        # Verify verified email state
        assert in_db.email_verified is True
        assert in_db.email_verification_token is None
        assert in_db.email_verification_token_expires is None
        assert in_db.credentials == {"password_hash": "hashed_password_456"}

    def test_user_identity_in_db_with_oauth_provider(self):
        """
        UserIdentityInDB should work with OAuth providers (Discord, GitHub).
        Email verification fields should be False/None for OAuth.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="discord",
            provider_user_id="123456789012345678",
            credentials={
                "access_token": "discord_access_token",
                "refresh_token": "discord_refresh_token",
                "expires_at": 1704110400,
            },
            email_verified=False,
            email_verification_token=None,
            email_verification_token_expires=None,
            created_at=created_at,
            updated_at=None,
        )

        in_db = UserIdentityInDB.model_validate(mock_orm)

        # Verify OAuth provider data
        assert in_db.provider == "discord"
        assert in_db.provider_user_id == "123456789012345678"
        assert "access_token" in in_db.credentials
        assert in_db.email_verified is False
        assert in_db.email_verification_token is None


class TestUserIdentityResponseExcludesSensitiveFields:
    """Test UserIdentityResponse excludes sensitive fields from API responses."""

    def test_user_identity_response_excludes_credentials(self):
        """
        UserIdentityResponse MUST exclude credentials field for security.
        Credentials contain sensitive data like password hashes or OAuth tokens.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials={"password_hash": "SHOULD_NOT_BE_EXPOSED"},
            email_verified=False,
            email_verification_token="token123",
            email_verification_token_expires=datetime(2024, 12, 31, tzinfo=UTC),
            created_at=created_at,
            updated_at=None,
        )

        # Convert to response schema
        response = UserIdentityResponse.model_validate(mock_orm)

        # Serialize to dict (as returned by API)
        response_dict = response.model_dump()

        # CRITICAL: credentials must NOT be in serialized response
        # (Field exists on object but is excluded from serialization)
        assert "credentials" not in response_dict

    def test_user_identity_response_excludes_verification_token(self):
        """
        UserIdentityResponse MUST exclude email_verification_token for security.
        Exposing verification tokens would allow unauthorized email verification.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials={"password_hash": "hashed"},
            email_verified=False,
            email_verification_token="SECRET_TOKEN_SHOULD_NOT_BE_EXPOSED",
            email_verification_token_expires=datetime(2024, 12, 31, tzinfo=UTC),
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # CRITICAL: verification token must NOT be in serialized response
        assert "email_verification_token" not in response_dict

    def test_user_identity_response_excludes_token_expiry(self):
        """
        UserIdentityResponse MUST exclude email_verification_token_expires.
        Token expiry information is internal implementation detail.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        expires_at = datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials={"password_hash": "hashed"},
            email_verified=False,
            email_verification_token="token123",
            email_verification_token_expires=expires_at,
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # Token expiry must NOT be in serialized response
        assert "email_verification_token_expires" not in response_dict

    def test_user_identity_response_includes_email_verified(self):
        """
        UserIdentityResponse MUST include email_verified field.
        Users need to know if their email is verified.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials={"password_hash": "hashed"},
            email_verified=False,
            email_verification_token="token123",
            email_verification_token_expires=datetime(2024, 12, 31, tzinfo=UTC),
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # email_verified MUST be present and accessible
        assert "email_verified" in response_dict
        assert response.email_verified is False
        assert response_dict["email_verified"] is False


class TestUserIdentityResponseWithVerifiedEmail:
    """Test UserIdentityResponse with verified email (happy path)."""

    def test_user_identity_response_with_verified_email(self):
        """
        UserIdentityResponse should show email_verified=True when email is verified.
        Token fields should be excluded (they are None in database anyway).
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="verified@example.com",
            credentials={"password_hash": "hashed"},
            email_verified=True,
            email_verification_token=None,
            email_verification_token_expires=None,
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # Verify verified email status is visible
        assert response.email_verified is True
        assert response_dict["email_verified"] is True

        # Verify sensitive fields are excluded
        assert "credentials" not in response_dict
        assert "email_verification_token" not in response_dict
        assert "email_verification_token_expires" not in response_dict

        # Verify public fields are present
        assert response_dict["id"] == identity_id
        assert response_dict["profile_id"] == profile_id
        assert response_dict["provider"] == "email"
        assert response_dict["provider_user_id"] == "verified@example.com"


class TestUserIdentityResponseWithUnverifiedEmail:
    """Test UserIdentityResponse with unverified email."""

    def test_user_identity_response_with_unverified_email(self):
        """
        UserIdentityResponse should show email_verified=False for unverified emails.
        Token fields must be excluded even though they exist in database.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        expires_at = datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="unverified@example.com",
            credentials={"password_hash": "hashed"},
            email_verified=False,
            email_verification_token="secret_token_abc123",
            email_verification_token_expires=expires_at,
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # Verify unverified status is visible
        assert response.email_verified is False
        assert response_dict["email_verified"] is False

        # CRITICAL: Token fields must be excluded for security
        assert "email_verification_token" not in response_dict
        assert "email_verification_token_expires" not in response_dict
        assert "credentials" not in response_dict

        # Verify public fields are present
        assert response_dict["provider"] == "email"
        assert response_dict["provider_user_id"] == "unverified@example.com"


class TestUserIdentityResponseModelConfig:
    """Test UserIdentityResponse model configuration."""

    def test_user_identity_response_uses_exclude_config(self):
        """
        Verify that UserIdentityResponse excludes sensitive fields
        from being serialized (via extra='ignore' config).
        """
        # Check that sensitive fields are NOT defined in UserIdentityResponse
        fields = UserIdentityResponse.model_fields

        # Sensitive fields should not exist in the response schema
        assert "credentials" not in fields
        assert "email_verification_token" not in fields
        assert "email_verification_token_expires" not in fields

        # Verify email_verified IS defined and not excluded
        assert "email_verified" in fields
        assert fields["email_verified"].exclude is not True

    def test_user_identity_response_serialization_modes(self):
        """
        Test different serialization modes (dict, json) to ensure
        sensitive fields are excluded in all modes.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials={"password_hash": "SECRET"},
            email_verified=False,
            email_verification_token="TOKEN",
            email_verification_token_expires=datetime(2024, 12, 31, tzinfo=UTC),
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)

        # Test dict serialization
        dict_output = response.model_dump()
        assert "credentials" not in dict_output
        assert "email_verification_token" not in dict_output
        assert "email_verified" in dict_output

        # Test JSON serialization
        json_output = response.model_dump_json()
        assert "credentials" not in json_output
        assert "email_verification_token" not in json_output
        assert "email_verified" in json_output


class TestUserIdentityResponseOAuthProviders:
    """Test UserIdentityResponse with OAuth providers (Discord, GitHub)."""

    def test_user_identity_response_discord_provider(self):
        """
        UserIdentityResponse should exclude OAuth credentials for Discord.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="discord",
            provider_user_id="123456789012345678",
            credentials={
                "access_token": "DISCORD_ACCESS_TOKEN_SECRET",
                "refresh_token": "DISCORD_REFRESH_TOKEN_SECRET",
                "expires_at": 1704110400,
            },
            email_verified=False,
            email_verification_token=None,
            email_verification_token_expires=None,
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # OAuth credentials must be excluded
        assert "credentials" not in response_dict

        # Public fields should be present
        assert response_dict["provider"] == "discord"
        assert response_dict["provider_user_id"] == "123456789012345678"
        assert response_dict["email_verified"] is False

    def test_user_identity_response_github_provider(self):
        """
        UserIdentityResponse should exclude OAuth credentials for GitHub.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="github",
            provider_user_id="github_user_12345",
            credentials={
                "access_token": "GITHUB_ACCESS_TOKEN_SECRET",
                "token_type": "bearer",
                "scope": "read:user,user:email",
            },
            email_verified=False,
            email_verification_token=None,
            email_verification_token_expires=None,
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # OAuth credentials must be excluded
        assert "credentials" not in response_dict

        # Public fields should be present
        assert response_dict["provider"] == "github"
        assert response_dict["provider_user_id"] == "github_user_12345"


class TestUserIdentityResponseEdgeCases:
    """Test edge cases in UserIdentityResponse serialization."""

    def test_user_identity_response_with_null_credentials(self):
        """
        UserIdentityResponse should handle None credentials gracefully.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials=None,
            email_verified=False,
            email_verification_token="token123",
            email_verification_token_expires=datetime(2024, 12, 31, tzinfo=UTC),
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # Credentials field should still be excluded
        assert "credentials" not in response_dict
        assert response_dict["email_verified"] is False

    def test_user_identity_response_with_empty_credentials(self):
        """
        UserIdentityResponse should handle empty credentials dict.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials={},
            email_verified=True,
            email_verification_token=None,
            email_verification_token_expires=None,
            created_at=created_at,
            updated_at=None,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # Credentials should be excluded even if empty
        assert "credentials" not in response_dict
        assert response_dict["email_verified"] is True

    def test_user_identity_response_with_updated_at(self):
        """
        UserIdentityResponse should include updated_at timestamp.
        """
        identity_id = uuid4()
        profile_id = uuid4()
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        updated_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        mock_orm = MockUserIdentity(
            id=identity_id,
            profile_id=profile_id,
            provider="email",
            provider_user_id="user@example.com",
            credentials={"password_hash": "hashed"},
            email_verified=True,
            email_verification_token=None,
            email_verification_token_expires=None,
            created_at=created_at,
            updated_at=updated_at,
        )

        response = UserIdentityResponse.model_validate(mock_orm)
        response_dict = response.model_dump()

        # Verify timestamps are present
        assert response_dict["created_at"] == created_at
        assert response_dict["updated_at"] == updated_at


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
