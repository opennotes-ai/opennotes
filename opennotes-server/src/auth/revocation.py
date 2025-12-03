"""JWT revocation service using Redis blacklist."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from jose import JWTError, jwt

from src.cache.redis_client import redis_client
from src.circuit_breaker import CircuitBreakerError, circuit_breaker_registry
from src.config import settings

logger = logging.getLogger(__name__)


class RevocationCheckFailedError(Exception):
    """Raised when token revocation check fails due to infrastructure issues."""


revocation_circuit_breaker = circuit_breaker_registry.get_breaker(
    name="token_revocation_redis",
    failure_threshold=5,
    timeout=60,
)


async def revoke_token(token: str) -> bool:
    """
    Revoke a JWT by adding its JTI to the Redis blacklist.

    Args:
        token: The JWT token to revoke

    Returns:
        True if revoked successfully, False otherwise
    """
    try:
        # Decode token to get JTI and expiration
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        jti: str | None = payload.get("jti")
        exp: int | None = payload.get("exp")

        if jti is None or exp is None:
            logger.warning("Token missing jti or exp claim, cannot revoke")
            return False

        # Calculate TTL - time until token expires
        exp_datetime = datetime.fromtimestamp(exp, tz=UTC)
        now = datetime.now(UTC)
        ttl_seconds = int((exp_datetime - now).total_seconds())

        # Only store if token hasn't expired yet
        if ttl_seconds <= 0:
            logger.info(f"Token already expired, skipping revocation: jti={jti}")
            return True

        # Store revoked JTI in Redis with TTL matching token expiry
        key = f"revoked_jwt:{jti}"
        success = await redis_client.set(key, "1", ttl=ttl_seconds)

        if success:
            logger.info(f"Token revoked successfully: jti={jti}, ttl={ttl_seconds}s")
        else:
            logger.error(f"Failed to revoke token in Redis: jti={jti}")

        return success

    except JWTError as e:
        logger.error(f"Failed to decode token for revocation: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during token revocation: {e}")
        return False


async def _check_revocation_in_redis(jti: str) -> bool:
    """
    Internal function to check JTI in Redis blacklist.
    Wrapped by circuit breaker for resilience.
    """
    key = f"revoked_jwt:{jti}"
    exists = await redis_client.exists(key)
    return exists > 0


async def is_token_revoked(token: str) -> bool:
    """
    Check if a JWT is revoked by looking up its JTI in Redis.

    SECURITY: This function implements fail-closed behavior. If Redis
    is unavailable or the circuit breaker is open, tokens are treated
    as revoked to prevent potentially compromised tokens from being used.

    Args:
        token: The JWT token to check

    Returns:
        True if revoked or if check failed (fail-closed), False if definitely not revoked

    Raises:
        RevocationCheckFailedError: When Redis check fails (logged at CRITICAL level)
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        jti: str | None = payload.get("jti")

        if jti is None:
            return False

        return await revocation_circuit_breaker.call(_check_revocation_in_redis, jti)

    except JWTError:
        return False
    except CircuitBreakerError as e:
        logger.critical(
            "Token revocation check FAILED - circuit breaker OPEN. "
            "Treating token as revoked (FAIL CLOSED). "
            f"Circuit: {revocation_circuit_breaker.name}, Error: {e}",
            extra={
                "circuit_breaker": revocation_circuit_breaker.name,
                "circuit_state": revocation_circuit_breaker.state.value,
                "failure_count": revocation_circuit_breaker.failure_count,
                "alert": "revocation_check_failed",
            },
        )
        raise RevocationCheckFailedError(
            f"Token revocation check unavailable - circuit breaker open: {e}"
        ) from e
    except Exception as e:
        logger.critical(
            "Token revocation check FAILED - Redis error. "
            "Treating token as revoked (FAIL CLOSED). "
            f"Error: {e}",
            extra={
                "circuit_breaker": revocation_circuit_breaker.name,
                "circuit_state": revocation_circuit_breaker.state.value,
                "failure_count": revocation_circuit_breaker.failure_count,
                "alert": "revocation_check_failed",
            },
        )
        raise RevocationCheckFailedError(
            f"Token revocation check failed due to infrastructure error: {e}"
        ) from e


async def revoke_all_user_tokens(user_id: UUID) -> bool:
    """
    Revoke all tokens for a user by updating their tokens_valid_after timestamp.

    This doesn't use Redis - instead it relies on the tokens_valid_after field
    in the User model which is checked during token verification.

    Args:
        user_id: The user ID whose tokens should be revoked

    Returns:
        True (this is handled by updating the User model directly)
    """
    logger.info(f"Revoking all tokens for user_id={user_id} via tokens_valid_after")
    # This is handled by the caller updating the User.tokens_valid_after field
    return True
