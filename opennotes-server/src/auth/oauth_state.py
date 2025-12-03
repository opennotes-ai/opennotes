"""
OAuth2 state parameter management for CSRF protection.

This module provides functions to generate, store, and validate OAuth2 state
parameters to prevent cross-site request forgery (CSRF) attacks during the
OAuth flow.

The state parameter is:
1. Generated as a cryptographically random value before OAuth redirect
2. Stored in Redis with a TTL (default 10 minutes)
3. Validated on callback - must match and be consumed (one-time use)

Security considerations:
- State values use 32 bytes (256 bits) of entropy from secrets module
- States are automatically expired via Redis TTL
- States are deleted immediately after successful validation (one-time use)
- If Redis is unavailable, OAuth requests fail-closed (rejected)
"""

import logging
import secrets
from urllib.parse import quote, urlencode

from src.cache.redis_client import redis_client
from src.config import settings

logger = logging.getLogger(__name__)

OAUTH_STATE_PREFIX = "oauth:state:"
DEFAULT_STATE_TTL = 600


class OAuthStateError(Exception):
    """Raised when OAuth state operations fail."""


def generate_oauth_state() -> str:
    """
    Generate a cryptographically secure random state value.

    Returns:
        URL-safe base64 encoded string with 256 bits of entropy
    """
    return secrets.token_urlsafe(32)


async def store_oauth_state(state: str, ttl: int = DEFAULT_STATE_TTL) -> None:
    """
    Store OAuth state in Redis with TTL.

    Args:
        state: The state value to store
        ttl: Time to live in seconds (default: 600 = 10 minutes)

    Raises:
        OAuthStateError: If Redis is unavailable
    """
    if redis_client.client is None:
        logger.error("OAuth state storage failed: Redis not available")
        raise OAuthStateError("Redis not available for OAuth state storage")

    key = f"{OAUTH_STATE_PREFIX}{state}"
    await redis_client.client.setex(key, ttl, "1")
    logger.debug(f"Stored OAuth state with key {key}, TTL {ttl}s")


async def validate_oauth_state(state: str | None) -> bool:
    """
    Validate and consume an OAuth state parameter.

    The state is deleted after successful validation to ensure one-time use.

    Args:
        state: The state value to validate

    Returns:
        True if state is valid and was consumed, False otherwise

    Raises:
        OAuthStateError: If Redis is unavailable
    """
    if not state:
        logger.warning("OAuth state validation failed: empty or None state")
        return False

    if redis_client.client is None:
        logger.error("OAuth state validation failed: Redis not available")
        raise OAuthStateError("Redis not available for OAuth state validation")

    key = f"{OAUTH_STATE_PREFIX}{state}"

    exists = await redis_client.client.exists(key)
    if not exists:
        logger.warning("OAuth state validation failed: state not found or expired")
        return False

    await redis_client.client.delete(key)
    logger.debug(f"OAuth state validated and consumed: {key}")
    return True


async def create_oauth_state_with_url(
    scopes: list[str] | None = None,
) -> tuple[str, str]:
    """
    Generate OAuth state, store it, and return Discord authorization URL.

    Args:
        scopes: OAuth scopes to request (default: ["identify"])

    Returns:
        Tuple of (state, authorization_url)

    Raises:
        OAuthStateError: If state storage fails
    """
    if scopes is None:
        scopes = ["identify"]

    state = generate_oauth_state()
    await store_oauth_state(state)

    params = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "redirect_uri": settings.DISCORD_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
    }

    base_url = "https://discord.com/oauth2/authorize"
    query_string = urlencode(params, quote_via=quote)
    authorization_url = f"{base_url}?{query_string}"

    logger.info("Created OAuth authorization URL with state parameter")
    return state, authorization_url
