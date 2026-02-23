import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.monitoring.metrics import (
    cors_preflight_requests_total,
    middleware_execution_duration_seconds,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.time()

        if request.method == "OPTIONS":
            cors_preflight_requests_total.add(
                1,
                {
                    "origin": request.headers.get("origin", "unknown"),
                    "path": request.url.path,
                },
            )

        response = await call_next(request)

        duration = time.time() - start
        middleware_execution_duration_seconds.record(
            duration,
            {"method": request.method, "endpoint": request.url.path},
        )

        return response
