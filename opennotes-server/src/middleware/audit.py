import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Request, Response
from prometheus_client import Counter
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.auth import verify_token
from src.events.publisher import event_publisher

logger = logging.getLogger(__name__)

audit_events_published_total = Counter(
    "audit_events_published_total",
    "Total number of audit events published to NATS",
    ["status"],
)

audit_publish_failures_total = Counter(
    "audit_publish_failures_total",
    "Total number of failed audit event publishes",
    ["error_type"],
)

audit_publish_timeouts_total = Counter(
    "audit_publish_timeouts_total",
    "Total number of audit event publish timeouts",
)


class AuditMiddleware(BaseHTTPMiddleware):
    MAX_BODY_SIZE = 10240

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = datetime.now(UTC)

        user_id = None
        auth_header = request.headers.get("authorization")
        has_service_auth = request.headers.get("x-api-key") or request.headers.get(
            "x-internal-auth"
        )
        if auth_header and auth_header.startswith("Bearer ") and not has_service_auth:
            token = auth_header.split(" ")[1]
            token_data = await verify_token(token)
            if token_data:
                user_id = token_data.user_id
            else:
                logger.warning(
                    "Token verification failed for request to %s",
                    request.url.path,
                    extra={"path": request.url.path},
                )

        request_body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body_bytes = await request.body()
                if len(body_bytes) <= self.MAX_BODY_SIZE:
                    try:
                        request_body = json.loads(body_bytes.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        request_body = {"_raw": body_bytes[:100].decode("utf-8", errors="ignore")}
                else:
                    request_body = {"_truncated": f"Body size {len(body_bytes)} exceeds limit"}
            except RuntimeError:
                request_body = {"_error": "Body already consumed"}

        response = await call_next(request)

        if request.method in ["POST", "PUT", "PATCH", "DELETE"] and user_id:
            await self._publish_audit_log(request, response, request_body, start_time, user_id)

        return response

    async def _publish_audit_log(
        self,
        request: Request,
        response: Response,
        request_body: Any,
        start_time: datetime,
        user_id: UUID | None,
    ) -> None:
        try:
            details: dict[str, Any] = {"status_code": response.status_code}
            if request_body:
                details["request_body"] = self._truncate_large_arrays(request_body)

            async with asyncio.timeout(5.0):
                await event_publisher.publish_audit_log(
                    user_id=user_id,
                    action=f"{request.method} {request.url.path}",
                    resource=request.url.path.split("/")[-1]
                    if "/" in request.url.path
                    else request.url.path,
                    details=json.dumps(details),
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    created_at=start_time,
                )
            audit_events_published_total.labels(status="success").inc()
        except TimeoutError:
            self._handle_audit_error(
                "Audit event publish timeout after 5s",
                "timeout",
                user_id,
                request.url.path,
            )
        except ConnectionError as e:
            self._handle_audit_error(
                f"Connection error publishing audit event: {e}",
                "connection",
                user_id,
                request.url.path,
            )
        except Exception as e:
            self._handle_audit_error(
                f"Unexpected error publishing audit event: {e}",
                "unknown",
                user_id,
                request.url.path,
                exc_info=True,
            )

    def _handle_audit_error(
        self,
        message: str,
        error_type: str,
        user_id: UUID | None,
        path: str,
        exc_info: bool = False,
    ) -> None:
        if exc_info:
            logger.error(message, extra={"user_id": user_id, "path": path}, exc_info=True)
        else:
            logger.error(message, extra={"user_id": user_id, "path": path})
        if error_type == "timeout":
            audit_publish_timeouts_total.inc()
        audit_publish_failures_total.labels(error_type=error_type).inc()
        audit_events_published_total.labels(status="failure").inc()

    def _truncate_large_arrays(self, obj: Any, max_array_len: int = 10) -> Any:
        """Truncate large arrays in the request body to keep audit log manageable."""
        if isinstance(obj, dict):
            return {k: self._truncate_large_arrays(v, max_array_len) for k, v in obj.items()}
        if isinstance(obj, list):
            if len(obj) > max_array_len and all(isinstance(x, int | float) for x in obj[:10]):
                return [*obj[:max_array_len], f"... ({len(obj) - max_array_len} more items)"]
            return [self._truncate_large_arrays(item, max_array_len) for item in obj]
        return obj
