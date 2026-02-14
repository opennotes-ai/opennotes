"""
Discord claims JWT creation and validation.

This module provides secure, signed JWT tokens for Discord-related claims
such as the "Manage Server" permission. This replaces the insecure pattern
of trusting raw X-Discord-* headers from clients.

Security fix for task-682: Authentication bypass via X-Discord-Has-Manage-Server header

Usage:
    Discord bot creates a signed JWT with claims:
        token = create_discord_claims_token(user_id, guild_id, has_manage_server=True)

    Server validates the JWT before trusting claims:
        claims = validate_discord_claims(token)
        if claims and claims.get("has_manage_server"):
            # User has manage server permission
"""

from typing import Any

import jwt
import pendulum

from src.config import settings
from src.monitoring import get_logger

logger = get_logger(__name__)

DISCORD_CLAIMS_EXPIRY_SECONDS = 300


def create_discord_claims_token(
    user_id: str,
    guild_id: str,
    has_manage_server: bool = False,
    expires_delta: pendulum.Duration | None = None,
) -> str:
    """
    Create a signed JWT containing Discord claims.

    This token should be created by the Discord bot and passed to the server
    in the X-Discord-Claims header. The server will validate the signature
    before trusting the claims.

    Args:
        user_id: Discord user ID (snowflake)
        guild_id: Discord guild ID (snowflake)
        has_manage_server: Whether the user has Manage Server permission
        expires_delta: Optional custom expiry. Defaults to 5 minutes.

    Returns:
        Signed JWT token string
    """
    if expires_delta is None:
        expires_delta = pendulum.duration(seconds=DISCORD_CLAIMS_EXPIRY_SECONDS)

    now = pendulum.now("UTC")
    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "user_id": user_id,
        "guild_id": guild_id,
        "has_manage_server": has_manage_server,
        "iat": now,
        "exp": expire,
        "type": "discord_claims",
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def validate_discord_claims(token: str) -> dict[str, Any] | None:
    """
    Validate a Discord claims JWT and return the claims if valid.

    Args:
        token: JWT token string from X-Discord-Claims header

    Returns:
        Dictionary of claims if token is valid, None otherwise.
        Claims include: user_id, guild_id, has_manage_server
    """
    if not token:
        return None

    validation_failed = False
    payload: dict[str, Any] = {}

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        logger.debug("Discord claims JWT has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid Discord claims JWT: {e}")
        return None

    if payload.get("type") != "discord_claims":
        logger.warning("Invalid token type in Discord claims JWT")
        validation_failed = True

    required_fields = ["user_id", "guild_id", "has_manage_server"]
    for field in required_fields:
        if field not in payload:
            logger.warning(f"Missing required field '{field}' in Discord claims JWT")
            validation_failed = True

    if not isinstance(payload.get("user_id"), str):
        logger.warning("user_id must be string in Discord claims JWT")
        validation_failed = True

    if not isinstance(payload.get("guild_id"), str):
        logger.warning("guild_id must be string in Discord claims JWT")
        validation_failed = True

    if not isinstance(payload.get("has_manage_server"), bool):
        logger.warning("has_manage_server must be boolean in Discord claims JWT")
        validation_failed = True

    if validation_failed:
        return None

    return {
        "user_id": payload["user_id"],
        "guild_id": payload["guild_id"],
        "has_manage_server": payload["has_manage_server"],
    }


def get_discord_manage_server_from_request(headers: dict[str, str]) -> bool:
    """
    Extract and validate the has_manage_server claim from request headers.

    This function:
    1. Checks for X-Discord-Claims header with signed JWT
    2. Validates the JWT signature
    3. Returns the has_manage_server claim if valid

    Raw X-Discord-Has-Manage-Server headers are IGNORED for security.
    Only signed JWT claims are trusted.

    Args:
        headers: Request headers dictionary

    Returns:
        True if user has verified Manage Server permission, False otherwise
    """
    claims_token = headers.get("x-discord-claims", "")

    if not claims_token:
        return False

    claims = validate_discord_claims(claims_token)

    if claims is None:
        return False

    return claims.get("has_manage_server", False)
