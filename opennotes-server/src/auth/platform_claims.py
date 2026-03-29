from typing import Any

import jwt
import pendulum
from fastapi import Request

from src.config import settings
from src.monitoring import get_logger

logger = get_logger(__name__)

PLATFORM_CLAIMS_EXPIRY_SECONDS = 300


CORE_CLAIM_KEYS = frozenset(
    {
        "platform",
        "scope",
        "sub",
        "community_id",
        "can_administer_community",
        "type",
        "iat",
        "exp",
    }
)


def create_platform_claims_token(
    platform: str,
    scope: str,
    sub: str,
    community_id: str,
    can_administer_community: bool = False,
    expires_delta: pendulum.Duration | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    if expires_delta is None:
        expires_delta = pendulum.duration(seconds=PLATFORM_CLAIMS_EXPIRY_SECONDS)

    now = pendulum.now("UTC")
    expire = now + expires_delta

    payload: dict[str, Any] = {
        "platform": platform,
        "scope": scope,
        "sub": sub,
        "community_id": community_id,
        "can_administer_community": can_administer_community,
        "type": "platform_claims",
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        collisions = set(extra_claims.keys()) & CORE_CLAIM_KEYS
        if collisions:
            logger.warning(f"Ignoring extra_claims that collide with core claims: {collisions}")
        for key, value in extra_claims.items():
            if key not in CORE_CLAIM_KEYS:
                payload[key] = value

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def validate_platform_claims(token: str) -> dict[str, Any] | None:
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        logger.debug("Platform claims JWT has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid platform claims JWT: {e}")
        return None

    validation_failed = False

    if payload.get("type") != "platform_claims":
        logger.warning("Invalid token type in platform claims JWT")
        validation_failed = True

    required_fields = ["platform", "scope", "sub", "community_id", "can_administer_community"]
    for field in required_fields:
        if field not in payload:
            logger.warning(f"Missing required field '{field}' in platform claims JWT")
            validation_failed = True

    type_checks: list[tuple[str, type]] = [
        ("sub", str),
        ("platform", str),
        ("community_id", str),
        ("can_administer_community", bool),
    ]
    for field_name, expected_type in type_checks:
        if not isinstance(payload.get(field_name), expected_type):
            logger.warning(f"{field_name} must be {expected_type.__name__} in platform claims JWT")
            validation_failed = True

    if validation_failed:
        return None

    result: dict[str, Any] = {}
    skip_keys = {"iat", "exp", "type"}
    for key, value in payload.items():
        if key not in skip_keys:
            result[key] = value
    return result


def get_platform_admin_status(request: Request) -> bool:
    claims_token = request.headers.get("x-platform-claims", "")

    if not claims_token:
        return False

    claims = validate_platform_claims(claims_token)

    if claims is None:
        return False

    return claims.get("can_administer_community", False)
