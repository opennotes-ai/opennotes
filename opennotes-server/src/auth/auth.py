import logging
import secrets
from datetime import datetime
from uuid import UUID

import pendulum
from jose import JWTError, jwt

from src.auth.models import TokenData
from src.auth.revocation import RevocationCheckFailedError, is_token_revoked
from src.config import settings

logger = logging.getLogger(__name__)


async def is_token_revoked_check(token: str) -> bool:
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
            f"Unexpected error in token revocation check - FAIL CLOSED: {e}",
            extra={"alert": "revocation_check_failed"},
        )
        return True


def create_access_token(
    data: dict[str, str | int], expires_delta: pendulum.Duration | None = None
) -> str:
    to_encode = data.copy()

    if expires_delta:
        expire = pendulum.now("UTC") + expires_delta
    else:
        expire = pendulum.now("UTC") + pendulum.duration(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    # Generate unique JWT ID for revocation tracking
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


def create_refresh_token(data: dict[str, str | int]) -> str:
    to_encode = data.copy()
    expire = pendulum.now("UTC") + pendulum.duration(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    # Generate unique JWT ID for revocation tracking
    jti = secrets.token_urlsafe(32)

    to_encode["exp"] = int(expire.timestamp())
    to_encode["iat"] = int(pendulum.now("UTC").timestamp())
    to_encode["jti"] = jti
    to_encode["type"] = "refresh"

    encoded_jwt: str = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


async def verify_token(token: str, tokens_valid_after: datetime | None = None) -> TokenData | None:  # noqa: PLR0911
    try:
        # Check if token is revoked
        if await is_token_revoked_check(token):
            return None

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        user_id_str: str | None = payload.get("sub")
        username: str | None = payload.get("username")
        role: str | None = payload.get("role")
        iat: int | None = payload.get("iat")

        if user_id_str is None or username is None or role is None:
            return None

        # Parse UUID from string
        try:
            user_id = UUID(user_id_str)
        except (ValueError, TypeError):
            return None

        # Validate iat (issued at) claim
        if iat is not None:
            iat_datetime = pendulum.from_timestamp(iat)
            now = pendulum.now("UTC")

            # Reject tokens with future iat
            if iat_datetime > now:
                return None

            # Check max token age if configured
            if settings.MAX_TOKEN_AGE_SECONDS is not None:
                token_age = (now - iat_datetime).total_seconds()
                if token_age > settings.MAX_TOKEN_AGE_SECONDS:
                    return None

            # Check against user's tokens_valid_after if provided
            if tokens_valid_after is not None and iat_datetime < tokens_valid_after:
                return None

        return TokenData(user_id=user_id, username=username, role=role, iat=iat)

    except JWTError:
        return None


async def verify_refresh_token(  # noqa: PLR0911
    token: str, tokens_valid_after: datetime | None = None
) -> TokenData | None:
    try:
        # Check if token is revoked
        if await is_token_revoked_check(token):
            return None

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        if payload.get("type") != "refresh":
            return None

        user_id_str: str | None = payload.get("sub")
        username: str | None = payload.get("username")
        role: str | None = payload.get("role")
        iat: int | None = payload.get("iat")

        if user_id_str is None or username is None or role is None:
            return None

        # Parse UUID from string
        try:
            user_id = UUID(user_id_str)
        except (ValueError, TypeError):
            return None

        # Validate iat (issued at) claim
        if iat is not None:
            iat_datetime = pendulum.from_timestamp(iat)
            now = pendulum.now("UTC")

            # Reject tokens with future iat
            if iat_datetime > now:
                return None

            # Check max token age if configured
            if settings.MAX_TOKEN_AGE_SECONDS is not None:
                token_age = (now - iat_datetime).total_seconds()
                if token_age > settings.MAX_TOKEN_AGE_SECONDS:
                    return None

            # Check against user's tokens_valid_after if provided
            if tokens_valid_after is not None and iat_datetime < tokens_valid_after:
                return None

        return TokenData(user_id=user_id, username=username, role=role, iat=iat)

    except JWTError:
        return None
