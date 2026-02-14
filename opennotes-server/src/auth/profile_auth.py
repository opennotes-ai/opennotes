"""
Profile-based JWT authentication module.

This module provides JWT token generation and verification for the refactored
authentication system using UserProfile IDs instead of User IDs.

Token payload structure:
    - sub: profile_id (UUID as string)
    - display_name: User's display name
    - provider: Authentication provider used (discord, github, email)
    - iat: Issued at timestamp
    - exp: Expiration timestamp
    - jti: Unique JWT ID for revocation support
    - type: Token type (omitted for access tokens, "refresh" for refresh tokens)
"""

import logging
import secrets
from uuid import UUID

import pendulum
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from src.auth.revocation import RevocationCheckFailedError, is_token_revoked
from src.config import settings

logger = logging.getLogger(__name__)


class ProfileTokenData(BaseModel):
    profile_id: UUID = Field(..., description="User profile identifier")
    display_name: str = Field(..., description="User's display name")
    provider: str = Field(..., description="Authentication provider")


def create_profile_access_token(
    profile_id: UUID,
    display_name: str,
    provider: str,
    expires_delta: pendulum.Duration | None = None,
) -> str:
    to_encode: dict[str, str | int] = {
        "sub": str(profile_id),
        "display_name": display_name,
        "provider": provider,
    }

    if expires_delta:
        expire = pendulum.now("UTC") + expires_delta
    else:
        expire = pendulum.now("UTC") + pendulum.duration(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    jti = secrets.token_urlsafe(32)

    to_encode["exp"] = int(expire.timestamp())
    to_encode["iat"] = int(pendulum.now("UTC").timestamp())
    to_encode["jti"] = jti

    encoded_jwt: str = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def create_profile_refresh_token(profile_id: UUID, display_name: str, provider: str) -> str:
    to_encode: dict[str, str | int] = {
        "sub": str(profile_id),
        "display_name": display_name,
        "provider": provider,
        "type": "refresh",
    }

    expire = pendulum.now("UTC") + pendulum.duration(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    jti = secrets.token_urlsafe(32)

    to_encode["exp"] = int(expire.timestamp())
    to_encode["iat"] = int(pendulum.now("UTC").timestamp())
    to_encode["jti"] = jti

    encoded_jwt: str = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


async def _is_token_revoked_check(token: str) -> bool:
    """
    Check if token is revoked.

    SECURITY: Implements fail-closed behavior. If the revocation check
    fails (e.g., Redis unavailable), returns True to treat the token
    as revoked. This prevents potentially compromised tokens from being
    used when infrastructure is degraded.
    """
    try:
        return await is_token_revoked(token)
    except RevocationCheckFailedError:
        return True
    except Exception as e:
        logger.critical(
            f"Unexpected error in profile token revocation check - FAIL CLOSED: {e}",
            extra={"alert": "revocation_check_failed"},
        )
        return True


async def verify_profile_token(token: str) -> ProfileTokenData | None:
    try:
        if await _is_token_revoked_check(token):
            return None

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        profile_id_str: str | None = payload.get("sub")
        display_name: str | None = payload.get("display_name")
        provider: str | None = payload.get("provider")

        if profile_id_str is None or display_name is None or provider is None:
            return None

        profile_id = UUID(profile_id_str)

        return ProfileTokenData(profile_id=profile_id, display_name=display_name, provider=provider)

    except (JWTError, ValueError):
        return None


async def verify_profile_refresh_token(token: str) -> ProfileTokenData | None:
    try:
        if await _is_token_revoked_check(token):
            return None

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        if payload.get("type") != "refresh":
            return None

        profile_id_str: str | None = payload.get("sub")
        display_name: str | None = payload.get("display_name")
        provider: str | None = payload.get("provider")

        if profile_id_str is None or display_name is None or provider is None:
            return None

        profile_id = UUID(profile_id_str)

        return ProfileTokenData(profile_id=profile_id, display_name=display_name, provider=provider)

    except (JWTError, ValueError):
        return None
