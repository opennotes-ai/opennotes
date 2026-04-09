import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from opentelemetry import baggage, context, trace
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.platform_claims import resolve_platform_identity

logger = logging.getLogger(__name__)


class PlatformContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        span = trace.get_current_span()

        platform_type = request.headers.get("x-platform-type")
        request_id = request.headers.get("x-request-id")

        ctx = context.get_current()

        if platform_type:
            span.set_attribute("platform.type", platform_type)
            ctx = baggage.set_baggage("platform.type", platform_type, ctx)

        identity = resolve_platform_identity(request)
        if identity is not None:
            request.state.platform_identity = identity

            span.set_attribute("platform.type", identity.platform)
            ctx = baggage.set_baggage("platform.type", identity.platform, ctx)

            span.set_attribute("platform.user_id", identity.sub)
            ctx = baggage.set_baggage("platform.user_id", identity.sub, ctx)

            span.set_attribute("platform.scope", identity.scope)
            ctx = baggage.set_baggage("platform.scope", identity.scope, ctx)

            span.set_attribute("platform.community_id", identity.community_id)
            ctx = baggage.set_baggage("platform.community_id", identity.community_id, ctx)

        if request_id:
            span.set_attribute("http.request_id", request_id)
            ctx = baggage.set_baggage("request_id", request_id, ctx)

        token = context.attach(ctx)
        try:
            response = await call_next(request)
        finally:
            context.detach(token)

        return response
