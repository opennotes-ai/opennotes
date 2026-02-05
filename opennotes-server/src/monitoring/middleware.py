import time
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.monitoring.errors import record_span_error
from src.monitoring.instance import InstanceMetadata
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
        instance_id = InstanceMetadata.get_instance_id()
        active_requests.labels(instance_id=instance_id).inc()
        start_time = time.time()

        try:
            response = await call_next(request)

            duration = time.time() - start_time
            method = request.method
            path = self._get_route_path(request)
            status = response.status_code

            http_requests_total.labels(
                method=method, endpoint=path, status=status, instance_id=instance_id
            ).inc()
            http_request_duration_seconds.labels(
                method=method, endpoint=path, instance_id=instance_id
            ).observe(duration)

            return response

        except Exception as e:
            duration = time.time() - start_time
            method = request.method
            path = self._get_route_path(request)

            http_requests_total.labels(
                method=method, endpoint=path, status=500, instance_id=instance_id
            ).inc()
            http_request_duration_seconds.labels(
                method=method, endpoint=path, instance_id=instance_id
            ).observe(duration)
            errors_total.labels(
                error_type=type(e).__name__, endpoint=path, instance_id=instance_id
            ).inc()

            record_span_error(e)
            raise

        finally:
            active_requests.labels(instance_id=instance_id).dec()

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
