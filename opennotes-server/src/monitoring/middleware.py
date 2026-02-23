import time
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.monitoring.errors import record_span_error
from src.monitoring.metrics import (
    active_requests,
    errors_total,
    http_request_duration_seconds,
    http_requests_total,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        active_requests.add(1)
        start_time = time.time()

        try:
            response = await call_next(request)

            duration = time.time() - start_time
            method = request.method
            path = self._get_route_path(request)
            status = response.status_code

            http_requests_total.add(1, {"method": method, "endpoint": path, "status": str(status)})
            http_request_duration_seconds.record(duration, {"method": method, "endpoint": path})

            return response

        except Exception as e:
            duration = time.time() - start_time
            method = request.method
            path = self._get_route_path(request)

            http_requests_total.add(1, {"method": method, "endpoint": path, "status": "500"})
            http_request_duration_seconds.record(duration, {"method": method, "endpoint": path})
            errors_total.add(1, {"error_type": type(e).__name__, "endpoint": path})

            record_span_error(e)
            raise

        finally:
            active_requests.add(-1)

    def _get_route_path(self, request: Request) -> str:
        try:
            if hasattr(request, "scope") and "route" in request.scope:
                route = request.scope["route"]
                if hasattr(route, "path"):
                    return cast(str, route.path)
                if hasattr(route, "path_format"):
                    return cast(str, route.path_format)
        except Exception:
            pass

        return "unknown"
