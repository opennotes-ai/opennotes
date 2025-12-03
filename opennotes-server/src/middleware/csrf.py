import secrets
from collections.abc import Awaitable, Callable
from typing import ClassVar

from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_403_FORBIDDEN
from starlette.types import ASGIApp

from src.config import settings


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware using double-submit cookie pattern.

    This middleware protects against Cross-Site Request Forgery attacks by:
    1. Setting a CSRF token cookie on GET requests
    2. Validating token matches on state-changing operations (POST/PUT/PATCH/DELETE)
    3. Exempting health checks, metrics, and other read-only endpoints

    For session-based authentication, this provides protection against CSRF attacks
    where an attacker tricks a user's browser into making authenticated requests.

    Note: JWT bearer token authentication is inherently CSRF-safe since tokens
    must be explicitly included in headers (not sent automatically like cookies).
    """

    # Exempt paths that don't need CSRF protection
    EXEMPT_PATHS: ClassVar[set[str]] = {
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/auth/register",
    }

    # Methods that require CSRF protection (state-changing operations)
    PROTECTED_METHODS: ClassVar[set[str]] = {"POST", "PUT", "PATCH", "DELETE"}

    # Cookie and header names
    CSRF_COOKIE_NAME: ClassVar[str] = "csrf_token"
    CSRF_HEADER_NAME: ClassVar[str] = "X-CSRF-Token"

    def __init__(self, app: ASGIApp, secret_key: str | None = None) -> None:
        super().__init__(app)
        self.secret_key = secret_key or settings.JWT_SECRET_KEY
        self.enabled = settings.ENVIRONMENT == "production"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Skip CSRF protection if disabled (dev/test environments)
        if not self.enabled:
            return await call_next(request)

        # Check if path is exempt
        if self._is_path_exempt(request.url.path):
            return await call_next(request)

        # Check if using JWT bearer token (CSRF-safe authentication)
        if self._is_bearer_token_auth(request):
            return await call_next(request)

        # Generate/retrieve CSRF token
        csrf_token = request.cookies.get(self.CSRF_COOKIE_NAME)

        # Validate CSRF token on state-changing operations
        if request.method in self.PROTECTED_METHODS and not self._validate_csrf_token(
            request, csrf_token
        ):
            return JSONResponse(
                status_code=HTTP_403_FORBIDDEN,
                content={
                    "detail": "CSRF token validation failed. Include X-CSRF-Token header matching the csrf_token cookie."
                },
            )

        # Process request
        response = await call_next(request)

        # Set or refresh CSRF token cookie on successful requests
        if not csrf_token and response.status_code < 400:
            csrf_token = self._generate_csrf_token()
            self._set_csrf_cookie(response, csrf_token)

        return response

    def _is_path_exempt(self, path: str) -> bool:
        """Check if path is exempt from CSRF protection."""
        # Exact match
        if path in self.EXEMPT_PATHS:
            return True

        # Prefix match for health/metrics endpoints
        exempt_prefixes = ("/health", "/metrics")
        return any(path.startswith(prefix) for prefix in exempt_prefixes)

    def _is_bearer_token_auth(self, request: Request) -> bool:
        """
        Check if request uses JWT bearer token authentication.

        Bearer tokens are CSRF-safe because they must be explicitly included
        in the Authorization header and are not sent automatically by browsers.
        """
        auth_header = request.headers.get("Authorization", "")
        return auth_header.startswith("Bearer ")

    def _validate_csrf_token(self, request: Request, cookie_token: str | None) -> bool:
        """
        Validate CSRF token using double-submit cookie pattern.

        The token in the cookie must match the token in the header.
        This prevents CSRF because attackers cannot read cookies from
        the target domain due to same-origin policy.
        """
        if not cookie_token:
            return False

        header_token = request.headers.get(self.CSRF_HEADER_NAME)
        if not header_token:
            return False

        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(cookie_token, header_token)

    def _generate_csrf_token(self) -> str:
        """Generate a cryptographically secure CSRF token."""
        return secrets.token_urlsafe(32)

    def _set_csrf_cookie(self, response: Response, token: str) -> None:
        """Set CSRF token cookie with secure attributes."""
        # Use MutableHeaders to properly set cookie
        headers = MutableHeaders(response.headers)

        # Build cookie with security attributes
        cookie_parts = [
            f"{self.CSRF_COOKIE_NAME}={token}",
            "Path=/",
            "SameSite=Lax",  # Lax allows GET requests from external sites
            "HttpOnly",  # Prevent JavaScript access
        ]

        # Add Secure flag in production
        if settings.ENVIRONMENT == "production":
            cookie_parts.append("Secure")

        # Set max age (match session duration or use reasonable default)
        cookie_parts.append(f"Max-Age={60 * 60 * 24}")  # 24 hours

        headers.append("Set-Cookie", "; ".join(cookie_parts))
        response.headers.update(headers)
