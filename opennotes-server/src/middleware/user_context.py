"""
Middleware to extract authenticated user context and set trace span attributes.

This middleware extracts user information from JWT tokens or API keys and adds them
as attributes to the current OpenTelemetry span for distributed tracing visibility.

The middleware is designed to run early in the request pipeline to capture user context
before any route handlers execute. It extracts user info directly from the Authorization
header without triggering full authentication (which requires database access).

Span Attributes Set:
- enduser.id: Standard OTel semantic convention for user identification (UUID)
- enduser.role: User's role from JWT claims
- user.username: Application-specific username

Baggage Propagation:
- enduser.id and user.username are propagated via W3C Baggage for downstream services

Note: For Discord-specific user context (from Discord bot requests), see discord_context.py
which handles X-Discord-* headers. This middleware handles JWT/API key auth paths.
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from jose import jwt
from opentelemetry import baggage, context, trace
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings

logger = logging.getLogger(__name__)


class AuthenticatedUserContextMiddleware(BaseHTTPMiddleware):
    """Extract authenticated user context from JWT and set span attributes and baggage.

    This middleware runs early in the request pipeline to capture user context from
    JWT tokens. It performs lightweight JWT decoding (signature verification only,
    no database lookups) to extract user claims.

    For API key authentication, user context must be captured at the route handler level
    since API key → user mapping requires a database lookup.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        span = trace.get_current_span()
        ctx = context.get_current()

        user_id, username, role = self._extract_jwt_claims(request)

        if user_id:
            span.set_attribute("enduser.id", user_id)
            ctx = baggage.set_baggage("enduser.id", user_id, ctx)

        if username:
            span.set_attribute("user.username", username)
            ctx = baggage.set_baggage("user.username", username, ctx)

        if role:
            span.set_attribute("enduser.role", role)

        token = context.attach(ctx)
        try:
            response = await call_next(request)
        finally:
            context.detach(token)

        return response

    def _extract_jwt_claims(self, request: Request) -> tuple[str | None, str | None, str | None]:
        """Extract user claims from JWT token in Authorization header.

        Performs lightweight JWT decoding to extract:
        - sub (user_id): UUID string
        - username: User's username
        - role: User's role

        Returns:
            Tuple of (user_id, username, role), any of which may be None if not available.
        """
        auth_header = request.headers.get("authorization")
        if not auth_header:
            return None, None, None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None, None, None

        token = parts[1]

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )

            user_id = payload.get("sub")
            username = payload.get("username")
            role = payload.get("role")

            return user_id, username, role

        except Exception:
            return None, None, None
