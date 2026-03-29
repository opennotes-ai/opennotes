import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from opentelemetry import baggage, context, trace
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.platform_claims import validate_platform_claims

logger = logging.getLogger(__name__)


class PlatformContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        span = trace.get_current_span()

        platform_type = request.headers.get("x-platform-type")
        platform_claims_token = request.headers.get("x-platform-claims")
        request_id = request.headers.get("x-request-id")

        ctx = context.get_current()

        if platform_type:
            span.set_attribute("platform.type", platform_type)
            ctx = baggage.set_baggage("platform.type", platform_type, ctx)

        if platform_claims_token:
            claims = validate_platform_claims(platform_claims_token)
            if claims:
                user_id = claims.get("sub")
                scope = claims.get("scope")
                community_id = claims.get("community_id")

                if user_id:
                    span.set_attribute("platform.user_id", user_id)
                    ctx = baggage.set_baggage("platform.user_id", user_id, ctx)

                if scope:
                    span.set_attribute("platform.scope", scope)
                    ctx = baggage.set_baggage("platform.scope", scope, ctx)

                if community_id:
                    span.set_attribute("platform.community_id", community_id)
                    ctx = baggage.set_baggage("platform.community_id", community_id, ctx)

        if request_id:
            span.set_attribute("http.request_id", request_id)
            ctx = baggage.set_baggage("request_id", request_id, ctx)

        token = context.attach(ctx)
        try:
            response = await call_next(request)
        finally:
            context.detach(token)

        return response
