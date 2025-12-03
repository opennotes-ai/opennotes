import asyncio
import logging
from typing import Any

from fastapi import Request
from jose import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.auth.auth import verify_token
from src.config import settings

logger = logging.getLogger(__name__)


def _get_storage_options() -> dict[str, str]:
    """Get Redis storage options for TLS connections (rediss://).

    For GCP Memorystore with SERVER_AUTHENTICATION:
    Server presents a Google-signed certificate, but we skip verification
    since traffic is VPC-internal via Private Service Access.
    """
    if settings.REDIS_URL and settings.REDIS_URL.startswith("rediss://"):
        return {"ssl_cert_reqs": "none"}

    return {}


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return get_remote_address(request)


def get_user_identifier(request: Request) -> str:
    auth_header = request.headers.get("authorization")

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                payload = jwt.decode(
                    token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                )
                user_id = payload.get("sub")
                if user_id:
                    return f"user:{user_id}"
            else:
                token_data = loop.run_until_complete(verify_token(token))
                if token_data:
                    return f"user:{token_data.user_id}"
        except Exception as e:
            logger.debug(f"Failed to extract user from token for rate limiting: {e}")

    return f"ip:{get_client_ip(request)}"


class RateLimitStorage:
    def __init__(self, storage_uri: str | None) -> None:
        self.storage_uri = storage_uri
        self._fallback_mode = False

    async def check(self, _key: str, _limit: int, _window: int) -> dict[str, Any]:
        if self._fallback_mode or not self.storage_uri:
            logger.warning("Rate limiting fallback mode active - allowing all requests")
            return {"allowed": True, "fallback": True}

        try:
            return {"allowed": True}
        except Exception as e:
            logger.error(f"Rate limit storage error: {e}")
            self._fallback_mode = True
            return {"allowed": True, "fallback": True}


limiter = Limiter(
    key_func=get_user_identifier,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    enabled=settings.RATE_LIMIT_ENABLED,
    storage_uri=settings.REDIS_URL if settings.RATE_LIMIT_ENABLED else None,
    storage_options=_get_storage_options(),
)


def get_rate_limit_for_endpoint(endpoint: str) -> str | None:
    endpoint_limits = {
        "/api/v1/notes/score": "30/minute",
        "/api/v1/webhooks/discord": f"{settings.WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER}/minute",
        "/api/v1/auth/login": "10/minute",
        "/api/v1/auth/register": "5/minute",
    }
    return endpoint_limits.get(endpoint)
