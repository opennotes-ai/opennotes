import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response, status
from jose import jwt

from src.config import settings
from src.middleware.distributed_rate_limiter import DistributedRateLimiter

logger = logging.getLogger(__name__)


class DistributedRateLimitMiddleware:
    def __init__(
        self,
        app: Any,
        rate_limiter: DistributedRateLimiter,
        endpoint_limits: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        self.app = app
        self.rate_limiter = rate_limiter
        self.endpoint_limits = endpoint_limits or {}

    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        method = request.method

        limit_key = f"{method} {path}"

        if limit_key not in self.endpoint_limits:
            return await call_next(request)

        limit, window_seconds = self.endpoint_limits[limit_key]

        identifier = self._get_identifier(request)
        window_key = self._get_window_key(path)

        limit_info = await self.rate_limiter.check_rate_limit(
            identifier=identifier,
            limit=limit,
            window_seconds=window_seconds,
            window_key=window_key,
        )

        if not limit_info.allowed:
            logger.warning(
                f"Rate limit exceeded for {identifier} on {limit_key}",
                extra={
                    "identifier": identifier,
                    "endpoint": limit_key,
                    "limit": limit,
                    "window": window_seconds,
                },
            )

            response = Response(
                content='{"error": "rate_limit_exceeded", "message": "Too many requests"}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )

            if limit_info.retry_after:
                response.headers["Retry-After"] = str(limit_info.retry_after)
                response.headers["X-RateLimit-Reset"] = str(limit_info.reset_at)

            return response

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(limit_info.remaining)
        response.headers["X-RateLimit-Reset"] = str(limit_info.reset_at)

        return response

    def _get_identifier(self, request: Request) -> str:
        auth_header = request.headers.get("authorization")

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(
                    token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                )
                user_id = payload.get("sub")
                if user_id:
                    return f"user:{user_id}"
            except Exception as e:
                logger.debug(f"Failed to extract user from token: {e}")

        if x_api_key := request.headers.get("x-api-key"):
            return f"api_key:{x_api_key[:16]}"

        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return f"ip:{forwarded_for.split(',')[0].strip()}"

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return f"ip:{real_ip.strip()}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    def _get_window_key(self, path: str) -> str:
        return path.replace("/", ":").lstrip(":")
