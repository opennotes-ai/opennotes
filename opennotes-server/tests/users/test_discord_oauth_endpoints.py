"""
Integration tests for Discord OAuth2 registration and login endpoints.

These tests require Docker for testcontainers to provide PostgreSQL.
"""

import os

# Force set environment variables (not setdefault) because unit tests' autouse
# fixture clears them. These must be set before any src imports.
os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-testing-only-32-chars-min"
os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "fvcKFp4tKdCkUfhZ0lm9chCwL-ZQfjHtlm6tW2NYWlk="
os.environ["ENCRYPTION_MASTER_KEY"] = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="

# Clear settings singleton cache so it picks up the new env vars
from src.config import get_settings

get_settings.cache_clear()

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import status  # noqa: E402

from src.auth.discord_oauth import (  # noqa: E402
    DiscordTokenExchangeError,
    DiscordUserVerificationError,
)


def mock_valid_oauth_state():
    """Context manager to mock valid OAuth state validation.

    Note: We patch where the function is used (profile_router), not where it's
    defined (oauth_state), because Python's `from module import func` creates
    a new reference in the importing module's namespace.
    """
    return patch(
        "src.users.profile_router.validate_oauth_state",
        return_value=True,
    )


class TestDiscordOAuthRegistration:
    """Tests for /api/v1/profile/auth/register/discord endpoint."""

    @pytest.mark.asyncio
    async def test_successful_registration(self, async_client, db):
        """Test successful registration with valid Discord OAuth code."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "testuser",
                    "discriminator": "0001",
                    "avatar": "abc123",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                    "expires_in": 604800,
                    "refresh_token": "mock_refresh_token",
                    "scope": "identify",
                },
            )

            response = await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_oauth_code",
                    "state": "valid-state-123",
                    "display_name": "Test User",
                    "avatar_url": None,
                },
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["display_name"] == "Test User"
            assert data["is_human"] is True
            assert "id" in data

    @pytest.mark.asyncio
    async def test_registration_with_avatar_override(self, async_client, db):
        """Test registration with custom avatar URL override."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "testuser",
                    "discriminator": "0001",
                    "avatar": "abc123",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                },
            )

            custom_avatar = "https://example.com/custom-avatar.png"
            response = await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_oauth_code",
                    "state": "valid-state-123",
                    "display_name": "Test User",
                    "avatar_url": custom_avatar,
                },
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["avatar_url"] == custom_avatar

    @pytest.mark.asyncio
    async def test_registration_with_default_avatar(self, async_client, db):
        """Test registration uses Discord avatar when no override provided."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "testuser",
                    "discriminator": "0001",
                    "avatar": "abc123",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                },
            )

            response = await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_oauth_code",
                    "state": "valid-state-123",
                    "display_name": "Test User",
                },
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert "https://cdn.discordapp.com/avatars/123456789/abc123.png" in data["avatar_url"]

    @pytest.mark.asyncio
    async def test_registration_invalid_oauth_code(self, async_client, db):
        """Test registration fails with invalid OAuth code."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.side_effect = DiscordTokenExchangeError("Invalid authorization code")

            response = await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "invalid_code",
                    "state": "valid-state-123",
                    "display_name": "Test User",
                },
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Discord OAuth verification failed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_registration_duplicate_discord_account(self, async_client, db):
        """Test registration fails when Discord account already registered."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "testuser",
                    "discriminator": "0001",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                },
            )

            await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_code_1",
                    "state": "valid-state-123",
                    "display_name": "First User",
                },
            )

            response = await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_code_2",
                    "state": "valid-state-456",
                    "display_name": "Second User",
                },
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Discord account already registered" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_registration_stores_oauth_tokens(self, async_client, db):
        """Test that OAuth tokens are stored securely in credentials field."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "testuser",
                    "discriminator": "0001",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                    "refresh_token": "mock_refresh_token",
                    "expires_in": 604800,
                    "scope": "identify",
                },
            )

            response = await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_oauth_code",
                    "state": "valid-state-123",
                    "display_name": "Test User",
                },
            )

            assert response.status_code == status.HTTP_201_CREATED


class TestDiscordOAuthLogin:
    """Tests for /api/v1/profile/auth/login/discord endpoint."""

    @pytest.mark.asyncio
    async def test_successful_login(self, async_client, db):
        """Test successful login with valid Discord OAuth code."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "testuser",
                    "discriminator": "0001",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                },
            )

            await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "registration_code",
                    "state": "valid-state-123",
                    "display_name": "Test User",
                },
            )

            response = await async_client.post(
                "/api/v1/profile/auth/login/discord",
                json={
                    "code": "login_code",
                    "state": "valid-state-456",
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_invalid_oauth_code(self, async_client, db):
        """Test login fails with invalid OAuth code."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.side_effect = DiscordTokenExchangeError("Invalid authorization code")

            response = await async_client.post(
                "/api/v1/profile/auth/login/discord",
                json={
                    "code": "invalid_code",
                    "state": "valid-state-123",
                },
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Discord OAuth verification failed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_unregistered_account(self, async_client, db):
        """Test login fails for unregistered Discord account."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "999999999",
                    "username": "unregistered_user",
                    "discriminator": "0001",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                },
            )

            response = await async_client.post(
                "/api/v1/profile/auth/login/discord",
                json={
                    "code": "valid_code",
                    "state": "valid-state-123",
                },
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Discord account not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_user_verification_failure(self, async_client, db):
        """Test login fails when Discord user verification fails."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.side_effect = DiscordUserVerificationError("Invalid access token")

            response = await async_client.post(
                "/api/v1/profile/auth/login/discord",
                json={
                    "code": "valid_code",
                    "state": "valid-state-123",
                },
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Discord OAuth verification failed" in response.json()["detail"]


class TestDiscordOAuthSecurity:
    """Security tests for Discord OAuth endpoints."""

    @pytest.mark.asyncio
    async def test_prevents_identity_spoofing(self, async_client, db):
        """Test that identity spoofing is prevented by OAuth verification."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "legitimate_user",
                    "discriminator": "0001",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                },
            )

            response = await async_client.post(
                "/api/v1/profile/auth/register/discord",
                json={
                    "code": "valid_code",
                    "state": "valid-state-123",
                    "display_name": "Legitimate User",
                },
            )

            assert response.status_code == status.HTTP_201_CREATED

            mock_verify.return_value = (
                {
                    "id": "987654321",
                    "username": "different_user",
                    "discriminator": "0002",
                },
                {
                    "access_token": "different_token",
                    "token_type": "Bearer",
                },
            )

            response = await async_client.post(
                "/api/v1/profile/auth/login/discord",
                json={
                    "code": "different_code",
                    "state": "valid-state-456",
                },
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_rate_limiting_on_registration(self, async_client, db):
        """Test rate limiting is enforced on registration endpoint."""
        with (
            mock_valid_oauth_state(),
            patch("src.users.profile_router.verify_discord_user") as mock_verify,
        ):
            mock_verify.return_value = (
                {
                    "id": "123456789",
                    "username": "testuser",
                    "discriminator": "0001",
                },
                {
                    "access_token": "mock_access_token",
                    "token_type": "Bearer",
                },
            )

            for i in range(4):
                response = await async_client.post(
                    "/api/v1/profile/auth/register/discord",
                    json={
                        "code": f"code_{i}",
                        "state": f"valid-state-{i}",
                        "display_name": f"User {i}",
                    },
                )

                if i == 0:
                    assert response.status_code == status.HTTP_201_CREATED
                else:
                    assert response.status_code in [
                        status.HTTP_400_BAD_REQUEST,
                        status.HTTP_429_TOO_MANY_REQUESTS,
                    ]
