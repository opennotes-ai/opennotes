"""
Tests for Discord OAuth2 authentication service.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.auth.discord_oauth import (
    DiscordTokenExchangeError,
    DiscordUserVerificationError,
    exchange_code_for_token,
    get_user_from_token,
    verify_discord_user,
)

pytestmark = pytest.mark.unit


class TestExchangeCodeForToken:
    """Tests for exchange_code_for_token function."""

    @pytest.mark.asyncio
    async def test_successful_token_exchange(self):
        """Test successful token exchange with valid code."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        # json() is not async, so use MagicMock, not AsyncMock
        from unittest.mock import MagicMock

        mock_response.json = MagicMock(
            return_value={
                "access_token": "mock_access_token",
                "token_type": "Bearer",
                "expires_in": 604800,
                "refresh_token": "mock_refresh_token",
                "scope": "identify",
            }
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value = mock_client_instance

            result = await exchange_code_for_token(
                code="test_code",
                client_id="test_client_id",
                client_secret="test_client_secret",
                redirect_uri="http://localhost:3000/callback",
            )

            assert result["access_token"] == "mock_access_token"
            assert result["token_type"] == "Bearer"
            assert result["expires_in"] == 604800
            assert result["refresh_token"] == "mock_refresh_token"

    @pytest.mark.asyncio
    async def test_token_exchange_invalid_code(self):
        """Test token exchange with invalid authorization code."""
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid authorization code"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value = mock_client_instance

            with pytest.raises(
                DiscordTokenExchangeError, match="Failed to exchange code for token"
            ):
                await exchange_code_for_token(
                    code="invalid_code",
                    client_id="test_client_id",
                    client_secret="test_client_secret",
                    redirect_uri="http://localhost:3000/callback",
                )

    @pytest.mark.asyncio
    async def test_token_exchange_missing_fields(self):
        """Test token exchange with response missing required fields."""
        from unittest.mock import MagicMock

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={
                "expires_in": 604800,
            }
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value = mock_client_instance

            with pytest.raises(DiscordTokenExchangeError, match="Invalid token response"):
                await exchange_code_for_token(
                    code="test_code",
                    client_id="test_client_id",
                    client_secret="test_client_secret",
                    redirect_uri="http://localhost:3000/callback",
                )

    @pytest.mark.asyncio
    async def test_token_exchange_timeout(self):
        """Test token exchange with request timeout."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.post.side_effect = httpx.TimeoutException("Request timeout")
            mock_client.return_value = mock_client_instance

            with pytest.raises(DiscordTokenExchangeError, match="Token exchange request timed out"):
                await exchange_code_for_token(
                    code="test_code",
                    client_id="test_client_id",
                    client_secret="test_client_secret",
                    redirect_uri="http://localhost:3000/callback",
                )


class TestGetUserFromToken:
    """Tests for get_user_from_token function."""

    @pytest.mark.asyncio
    async def test_successful_user_fetch(self):
        """Test successful user information retrieval."""
        from unittest.mock import MagicMock

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={
                "id": "123456789",
                "username": "testuser",
                "discriminator": "0001",
                "avatar": "abc123",
                "email": "test@example.com",
            }
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value = mock_client_instance

            result = await get_user_from_token(
                access_token="mock_access_token",
                token_type="Bearer",
            )

            assert result["id"] == "123456789"
            assert result["username"] == "testuser"
            assert result["discriminator"] == "0001"

    @pytest.mark.asyncio
    async def test_user_fetch_invalid_token(self):
        """Test user fetch with invalid access token."""
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid access token"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value = mock_client_instance

            with pytest.raises(
                DiscordUserVerificationError, match="Invalid or expired access token"
            ):
                await get_user_from_token(
                    access_token="invalid_token",
                    token_type="Bearer",
                )

    @pytest.mark.asyncio
    async def test_user_fetch_missing_id(self):
        """Test user fetch with response missing user ID."""
        from unittest.mock import MagicMock

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={
                "username": "testuser",
            }
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value = mock_client_instance

            with pytest.raises(DiscordUserVerificationError, match="Invalid user response"):
                await get_user_from_token(
                    access_token="mock_access_token",
                    token_type="Bearer",
                )


class TestVerifyDiscordUser:
    """Tests for verify_discord_user function."""

    @pytest.mark.asyncio
    async def test_successful_verification(self):
        """Test successful complete OAuth verification flow."""
        with (
            patch("src.auth.discord_oauth.exchange_code_for_token") as mock_exchange,
            patch("src.auth.discord_oauth.get_user_from_token") as mock_get_user,
        ):
            mock_exchange.return_value = {
                "access_token": "mock_access_token",
                "token_type": "Bearer",
                "expires_in": 604800,
                "refresh_token": "mock_refresh_token",
            }

            mock_get_user.return_value = {
                "id": "123456789",
                "username": "testuser",
                "discriminator": "0001",
            }

            user_data, token_data = await verify_discord_user(
                code="test_code",
                client_id="test_client_id",
                client_secret="test_client_secret",
                redirect_uri="http://localhost:3000/callback",
            )

            assert user_data["id"] == "123456789"
            assert token_data["access_token"] == "mock_access_token"

    @pytest.mark.asyncio
    async def test_verification_with_expected_id_match(self):
        """Test verification with matching expected Discord ID."""
        with (
            patch("src.auth.discord_oauth.exchange_code_for_token") as mock_exchange,
            patch("src.auth.discord_oauth.get_user_from_token") as mock_get_user,
        ):
            mock_exchange.return_value = {
                "access_token": "mock_access_token",
                "token_type": "Bearer",
            }

            mock_get_user.return_value = {
                "id": "123456789",
                "username": "testuser",
            }

            user_data, _token_data = await verify_discord_user(
                code="test_code",
                client_id="test_client_id",
                client_secret="test_client_secret",
                redirect_uri="http://localhost:3000/callback",
                expected_discord_id="123456789",
            )

            assert user_data["id"] == "123456789"

    @pytest.mark.asyncio
    async def test_verification_with_expected_id_mismatch(self):
        """Test verification with mismatched expected Discord ID (identity spoofing attempt)."""
        with (
            patch("src.auth.discord_oauth.exchange_code_for_token") as mock_exchange,
            patch("src.auth.discord_oauth.get_user_from_token") as mock_get_user,
        ):
            mock_exchange.return_value = {
                "access_token": "mock_access_token",
                "token_type": "Bearer",
            }

            mock_get_user.return_value = {
                "id": "123456789",
                "username": "testuser",
            }

            with pytest.raises(
                DiscordUserVerificationError, match="Discord user ID does not match"
            ):
                await verify_discord_user(
                    code="test_code",
                    client_id="test_client_id",
                    client_secret="test_client_secret",
                    redirect_uri="http://localhost:3000/callback",
                    expected_discord_id="987654321",
                )

    @pytest.mark.asyncio
    async def test_verification_token_exchange_failure(self):
        """Test verification when token exchange fails."""
        with patch("src.auth.discord_oauth.exchange_code_for_token") as mock_exchange:
            mock_exchange.side_effect = DiscordTokenExchangeError("Token exchange failed")

            with pytest.raises(DiscordTokenExchangeError):
                await verify_discord_user(
                    code="invalid_code",
                    client_id="test_client_id",
                    client_secret="test_client_secret",
                    redirect_uri="http://localhost:3000/callback",
                )

    @pytest.mark.asyncio
    async def test_verification_user_fetch_failure(self):
        """Test verification when user fetch fails."""
        with (
            patch("src.auth.discord_oauth.exchange_code_for_token") as mock_exchange,
            patch("src.auth.discord_oauth.get_user_from_token") as mock_get_user,
        ):
            mock_exchange.return_value = {
                "access_token": "mock_access_token",
                "token_type": "Bearer",
            }

            mock_get_user.side_effect = DiscordUserVerificationError("User verification failed")

            with pytest.raises(DiscordUserVerificationError):
                await verify_discord_user(
                    code="test_code",
                    client_id="test_client_id",
                    client_secret="test_client_secret",
                    redirect_uri="http://localhost:3000/callback",
                )
