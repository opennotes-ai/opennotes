from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.config import settings
from src.monitoring import get_logger
from src.monitoring.metrics import errors_total

logger = get_logger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.default_max_size = settings.MAX_REQUEST_SIZE_BYTES
        self.note_max_size = settings.MAX_NOTE_SIZE_BYTES
        self.webhook_max_size = settings.MAX_WEBHOOK_SIZE_BYTES

    def _get_max_size_for_path(self, path: str) -> int:
        if "/notes" in path:
            return int(self.note_max_size)
        if "/webhooks" in path:
            return int(self.webhook_max_size)
        return int(self.default_max_size)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        content_length = request.headers.get("content-length")

        if content_length:
            content_length_int = int(content_length)
            max_size = self._get_max_size_for_path(request.url.path)

            if content_length_int > max_size:
                logger.warning(
                    f"Request body too large: {content_length_int} bytes (max: {max_size} bytes)",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "content_length": content_length_int,
                        "max_size": max_size,
                    },
                )
                errors_total.labels(error_type="payload_too_large", endpoint=request.url.path).inc()

                return Response(
                    content='{"detail":"Request payload too large"}',
                    status_code=413,
                    media_type="application/json",
                )

        return await call_next(request)
