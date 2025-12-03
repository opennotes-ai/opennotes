import asyncio
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.config import settings
from src.monitoring import get_logger
from src.monitoring.instance import InstanceMetadata
from src.monitoring.metrics import errors_total

logger = get_logger(__name__)


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, timeout_seconds: float | None = None) -> None:
        super().__init__(app)
        self.timeout_seconds = timeout_seconds or settings.REQUEST_TIMEOUT

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout_seconds)
        except TimeoutError:
            logger.warning(
                f"Request timeout after {self.timeout_seconds}s",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "timeout_seconds": self.timeout_seconds,
                },
            )
            instance_id = InstanceMetadata.get_instance_id()
            errors_total.labels(
                error_type="timeout", endpoint=request.url.path, instance_id=instance_id
            ).inc()

            return Response(
                content='{"detail":"Request timeout"}',
                status_code=504,
                media_type="application/json",
            )
