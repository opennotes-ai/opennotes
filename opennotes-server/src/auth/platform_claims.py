from dataclasses import dataclass, field
from typing import Any

import jwt
import pendulum
from fastapi import Request
from opentelemetry import trace

from src.config import settings
from src.monitoring import get_logger

logger = get_logger(__name__)

PLATFORM_CLAIMS_EXPIRY_SECONDS = 300


@dataclass(frozen=True)
class PlatformIdentity:
    platform: str
    scope: str
    sub: str
    community_id: str
    can_administer_community: bool = False
    extra_claims: dict[str, str] = field(default_factory=dict)


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
    for field_name in required_fields:
        if field_name not in payload:
            logger.warning(f"Missing required field '{field_name}' in platform claims JWT")
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


def _has_platform_adapter_scope(request: Request) -> bool:
    api_key = getattr(request.state, "api_key", None)
    if api_key is None:
        return False
    return api_key.has_scope("platform:adapter")


def _resolve_from_adapter_headers(request: Request) -> PlatformIdentity | None:
    if not _has_platform_adapter_scope(request):
        return None

    platform = request.headers.get("x-adapter-platform")
    user_id = request.headers.get("x-adapter-user-id")
    scope = request.headers.get("x-adapter-scope")

    if not platform or not user_id or not scope:
        return None

    admin_str = request.headers.get("x-adapter-admin", "false")
    can_administer = admin_str.lower() == "true"

    extra: dict[str, str] = {}
    username = request.headers.get("x-adapter-username")
    if username:
        extra["username"] = username
    trust_level = request.headers.get("x-adapter-trust-level")
    if trust_level:
        extra["trust_level"] = trust_level
    moderator = request.headers.get("x-adapter-moderator")
    if moderator:
        extra["moderator"] = moderator

    return PlatformIdentity(
        platform=platform,
        scope=scope,
        sub=user_id,
        community_id=scope,
        can_administer_community=can_administer,
        extra_claims=extra,
    )


def _resolve_from_jwt(request: Request) -> PlatformIdentity | None:
    token = request.headers.get("x-platform-claims")
    if not token:
        return None

    claims = validate_platform_claims(token)
    if claims is None:
        return None

    extra: dict[str, str] = {}
    skip_keys = {"platform", "scope", "sub", "community_id", "can_administer_community"}
    for key, value in claims.items():
        if key not in skip_keys:
            extra[key] = str(value) if not isinstance(value, str) else value

    return PlatformIdentity(
        platform=claims.get("platform", ""),
        scope=claims.get("scope", ""),
        sub=claims.get("sub", ""),
        community_id=claims.get("community_id", ""),
        can_administer_community=claims.get("can_administer_community", False),
        extra_claims=extra,
    )


def resolve_platform_identity(request: Request) -> PlatformIdentity | None:
    identity = _resolve_from_adapter_headers(request)
    if identity is None:
        identity = _resolve_from_jwt(request)

    if identity is not None:
        span = trace.get_current_span()
        span.set_attribute("platform.type", identity.platform)
        span.set_attribute("platform.user_id", identity.sub)
        span.set_attribute("platform.scope", identity.scope)
        span.set_attribute("platform.community_id", identity.community_id)

    return identity


def get_platform_admin_status(request: Request) -> bool:
    identity = getattr(request.state, "platform_identity", None)
    if isinstance(identity, PlatformIdentity):
        return identity.can_administer_community

    claims_token = request.headers.get("x-platform-claims", "")

    if not claims_token:
        return False

    claims = validate_platform_claims(claims_token)

    if claims is None:
        return False

    return claims.get("can_administer_community", False)
