"""
Discord OAuth2 service for user authentication and verification.

This module provides functions to:
- Exchange authorization codes for access tokens
- Verify Discord user identity via OAuth2
- Fetch user information from Discord API
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DiscordOAuthError(Exception):
    """Base exception for Discord OAuth errors."""


class DiscordTokenExchangeError(DiscordOAuthError):
    """Raised when token exchange fails."""


class DiscordUserVerificationError(DiscordOAuthError):
    """Raised when user verification fails."""


async def exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Exchange authorization code for Discord OAuth2 access token.

    Args:
        code: Authorization code from Discord OAuth2 flow
        client_id: Discord application client ID
        client_secret: Discord application client secret
        redirect_uri: Redirect URI used in authorization request
        timeout: Request timeout in seconds

    Returns:
        Token response containing access_token, token_type, expires_in, refresh_token, scope

    Raises:
        DiscordTokenExchangeError: If token exchange fails
    """
    url = "https://discord.com/api/v10/oauth2/token"

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                data=data,
                headers=headers,
                auth=(client_id, client_secret),
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(
                    f"Discord token exchange failed: {response.status_code} - {error_detail}"
                )
                raise DiscordTokenExchangeError(
                    f"Failed to exchange code for token: {response.status_code}"
                )

            token_data: dict[str, Any] = response.json()

            required_fields = ["access_token", "token_type"]
            if not all(field in token_data for field in required_fields):
                raise DiscordTokenExchangeError("Invalid token response: missing required fields")

            return token_data

    except httpx.TimeoutException as e:
        logger.error(f"Discord token exchange timeout: {e}")
        raise DiscordTokenExchangeError("Token exchange request timed out") from e
    except httpx.RequestError as e:
        logger.error(f"Discord token exchange request error: {e}")
        raise DiscordTokenExchangeError(f"Token exchange request failed: {e}") from e
    except Exception as e:
        logger.exception(f"Unexpected error during token exchange: {e}")
        raise DiscordTokenExchangeError(f"Unexpected error: {e}") from e


async def get_user_from_token(
    access_token: str,
    token_type: str = "Bearer",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch Discord user information using OAuth2 access token.

    Args:
        access_token: Discord OAuth2 access token
        token_type: Token type (usually "Bearer")
        timeout: Request timeout in seconds

    Returns:
        User object containing id, username, discriminator, avatar, etc.

    Raises:
        DiscordUserVerificationError: If user verification fails
    """
    url = "https://discord.com/api/v10/users/@me"

    headers = {
        "Authorization": f"{token_type} {access_token}",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 401:
                logger.error("Discord access token invalid or expired")
                raise DiscordUserVerificationError("Invalid or expired access token")

            if response.status_code != 200:
                error_detail = response.text
                logger.error(
                    f"Discord user verification failed: {response.status_code} - {error_detail}"
                )
                raise DiscordUserVerificationError(
                    f"Failed to fetch user information: {response.status_code}"
                )

            user_data: dict[str, Any] = response.json()

            if "id" not in user_data:
                raise DiscordUserVerificationError("Invalid user response: missing user ID")

            return user_data

    except httpx.TimeoutException as e:
        logger.error(f"Discord user verification timeout: {e}")
        raise DiscordUserVerificationError("User verification request timed out") from e
    except httpx.RequestError as e:
        logger.error(f"Discord user verification request error: {e}")
        raise DiscordUserVerificationError(f"User verification request failed: {e}") from e
    except DiscordUserVerificationError:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during user verification: {e}")
        raise DiscordUserVerificationError(f"Unexpected error: {e}") from e


async def verify_discord_user(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    expected_discord_id: str | None = None,
    timeout: float = 30.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Complete Discord OAuth2 verification flow.

    Exchanges authorization code for access token, then fetches user information.
    Optionally verifies that the user ID matches expected value.

    Args:
        code: Authorization code from Discord OAuth2 flow
        client_id: Discord application client ID
        client_secret: Discord application client secret
        redirect_uri: Redirect URI used in authorization request
        expected_discord_id: Optional Discord user ID to verify against
        timeout: Request timeout in seconds

    Returns:
        Tuple of (user_data, token_data)

    Raises:
        DiscordTokenExchangeError: If token exchange fails
        DiscordUserVerificationError: If user verification fails or ID mismatch
    """
    token_data = await exchange_code_for_token(
        code=code,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        timeout=timeout,
    )

    user_data = await get_user_from_token(
        access_token=token_data["access_token"],
        token_type=token_data.get("token_type", "Bearer"),
        timeout=timeout,
    )

    if expected_discord_id and user_data["id"] != expected_discord_id:
        logger.warning(
            f"Discord ID mismatch: expected {expected_discord_id}, got {user_data['id']}"
        )
        raise DiscordUserVerificationError("Discord user ID does not match expected value")

    return user_data, token_data
