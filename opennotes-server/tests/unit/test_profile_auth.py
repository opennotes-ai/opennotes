"""
Unit tests for profile-based authentication system.

Tests JWT token generation, verification, and profile-based authentication flows.
These tests don't require database access.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from jose import jwt

from src.auth.profile_auth import (
    create_profile_access_token,
    create_profile_refresh_token,
    verify_profile_refresh_token,
    verify_profile_token,
)
from src.config import settings
from src.users.profile_schemas import AuthProvider

pytestmark = pytest.mark.unit


class TestProfileTokenGeneration:
    def test_create_profile_access_token(self):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_access_token(profile_id, display_name, provider)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_profile_access_token_with_custom_expiry(self):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.EMAIL.value
        expires_delta = timedelta(minutes=30)

        token = create_profile_access_token(profile_id, display_name, provider, expires_delta)

        assert token is not None
        assert isinstance(token, str)

    def test_create_profile_refresh_token(self):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.GITHUB.value

        token = create_profile_refresh_token(profile_id, display_name, provider)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0


class TestProfileTokenVerification:
    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_verify_valid_profile_token(self, mock_revoked):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_access_token(profile_id, display_name, provider)
        token_data = await verify_profile_token(token)

        assert token_data is not None
        assert token_data.profile_id == profile_id
        assert token_data.display_name == display_name
        assert token_data.provider == provider

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_verify_invalid_token(self, mock_revoked):
        invalid_token = "invalid.jwt.token"

        token_data = await verify_profile_token(invalid_token)

        assert token_data is None

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_verify_malformed_token(self, mock_revoked):
        malformed_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid"

        token_data = await verify_profile_token(malformed_token)

        assert token_data is None

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_verify_expired_token(self, mock_revoked):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.EMAIL.value
        expires_delta = timedelta(seconds=-1)

        token = create_profile_access_token(profile_id, display_name, provider, expires_delta)
        token_data = await verify_profile_token(token)

        assert token_data is None

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_verify_valid_refresh_token(self, mock_revoked):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        refresh_token = create_profile_refresh_token(profile_id, display_name, provider)
        token_data = await verify_profile_refresh_token(refresh_token)

        assert token_data is not None
        assert token_data.profile_id == profile_id
        assert token_data.display_name == display_name
        assert token_data.provider == provider

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_verify_access_token_as_refresh_fails(self, mock_revoked):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        access_token = create_profile_access_token(profile_id, display_name, provider)
        token_data = await verify_profile_refresh_token(access_token)

        assert token_data is None


class TestProfileTokenPayload:
    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_token_contains_correct_profile_id(self, mock_revoked):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_access_token(profile_id, display_name, provider)
        token_data = await verify_profile_token(token)

        assert token_data is not None
        assert token_data.profile_id == profile_id

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_token_contains_display_name(self, mock_revoked):
        profile_id = uuid4()
        display_name = "alice_wonderland"
        provider = AuthProvider.EMAIL.value

        token = create_profile_access_token(profile_id, display_name, provider)
        token_data = await verify_profile_token(token)

        assert token_data is not None
        assert token_data.display_name == display_name

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_token_contains_provider(self, mock_revoked):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.GITHUB.value

        token = create_profile_access_token(profile_id, display_name, provider)
        token_data = await verify_profile_token(token)

        assert token_data is not None
        assert token_data.provider == provider

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_multiple_providers_maintained_correctly(self, mock_revoked):
        profile_id = uuid4()
        display_name = "test_user"

        discord_token = create_profile_access_token(
            profile_id, display_name, AuthProvider.DISCORD.value
        )
        email_token = create_profile_access_token(
            profile_id, display_name, AuthProvider.EMAIL.value
        )
        github_token = create_profile_access_token(
            profile_id, display_name, AuthProvider.GITHUB.value
        )

        discord_data = await verify_profile_token(discord_token)
        email_data = await verify_profile_token(email_token)
        github_data = await verify_profile_token(github_token)

        assert discord_data.provider == AuthProvider.DISCORD.value
        assert email_data.provider == AuthProvider.EMAIL.value
        assert github_data.provider == AuthProvider.GITHUB.value


class TestProfileAuthProviders:
    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_discord_provider_token(self, mock_revoked):
        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "discord_user", AuthProvider.DISCORD.value)
        token_data = await verify_profile_token(token)

        assert token_data is not None
        assert token_data.provider == AuthProvider.DISCORD.value

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_email_provider_token(self, mock_revoked):
        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "email_user", AuthProvider.EMAIL.value)
        token_data = await verify_profile_token(token)

        assert token_data is not None
        assert token_data.provider == AuthProvider.EMAIL.value

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked", new_callable=AsyncMock, return_value=False)
    async def test_github_provider_token(self, mock_revoked):
        profile_id = uuid4()
        token = create_profile_access_token(profile_id, "github_user", AuthProvider.GITHUB.value)
        token_data = await verify_profile_token(token)

        assert token_data is not None
        assert token_data.provider == AuthProvider.GITHUB.value


class TestProfileTokenJtiClaim:
    def test_access_token_includes_jti_claim(self):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_access_token(profile_id, display_name, provider)

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        assert "jti" in payload
        assert payload["jti"] is not None
        assert isinstance(payload["jti"], str)
        assert len(payload["jti"]) > 0

    def test_refresh_token_includes_jti_claim(self):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_refresh_token(profile_id, display_name, provider)

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        assert "jti" in payload
        assert payload["jti"] is not None
        assert isinstance(payload["jti"], str)
        assert len(payload["jti"]) > 0

    def test_access_tokens_have_unique_jti(self):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token1 = create_profile_access_token(profile_id, display_name, provider)
        token2 = create_profile_access_token(profile_id, display_name, provider)

        payload1 = jwt.decode(token1, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        payload2 = jwt.decode(token2, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        assert payload1["jti"] != payload2["jti"]

    def test_refresh_tokens_have_unique_jti(self):
        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token1 = create_profile_refresh_token(profile_id, display_name, provider)
        token2 = create_profile_refresh_token(profile_id, display_name, provider)

        payload1 = jwt.decode(token1, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        payload2 = jwt.decode(token2, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        assert payload1["jti"] != payload2["jti"]


class TestProfileTokenRevocation:
    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked")
    async def test_verify_profile_token_checks_revocation(self, mock_is_revoked: AsyncMock):
        mock_is_revoked.return_value = False

        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_access_token(profile_id, display_name, provider)
        token_data = await verify_profile_token(token)

        assert token_data is not None
        mock_is_revoked.assert_called_once_with(token)

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked")
    async def test_verify_profile_token_rejects_revoked_token(self, mock_is_revoked: AsyncMock):
        mock_is_revoked.return_value = True

        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_access_token(profile_id, display_name, provider)
        token_data = await verify_profile_token(token)

        assert token_data is None
        mock_is_revoked.assert_called_once_with(token)

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked")
    async def test_verify_profile_refresh_token_checks_revocation(self, mock_is_revoked: AsyncMock):
        mock_is_revoked.return_value = False

        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_refresh_token(profile_id, display_name, provider)
        token_data = await verify_profile_refresh_token(token)

        assert token_data is not None
        mock_is_revoked.assert_called_once_with(token)

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked")
    async def test_verify_profile_refresh_token_rejects_revoked_token(
        self, mock_is_revoked: AsyncMock
    ):
        mock_is_revoked.return_value = True

        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_refresh_token(profile_id, display_name, provider)
        token_data = await verify_profile_refresh_token(token)

        assert token_data is None
        mock_is_revoked.assert_called_once_with(token)

    @pytest.mark.asyncio
    @patch("src.auth.profile_auth.is_token_revoked")
    async def test_verify_profile_token_handles_revocation_check_failure_fail_closed(
        self, mock_is_revoked: AsyncMock
    ):
        """
        SECURITY: When revocation check fails, tokens must be treated as revoked
        (fail-closed behavior) to prevent potentially compromised tokens from
        being used during infrastructure failures.
        """
        mock_is_revoked.side_effect = Exception("Redis connection error")

        profile_id = uuid4()
        display_name = "test_user"
        provider = AuthProvider.DISCORD.value

        token = create_profile_access_token(profile_id, display_name, provider)
        token_data = await verify_profile_token(token)

        assert token_data is None
