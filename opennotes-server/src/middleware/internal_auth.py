"""
Internal service authentication middleware.

This middleware validates X-Platform-* headers to prevent authentication bypass attacks.
It ensures that headers containing platform user information only come from trusted
internal services (like platform adapter bots), not from external clients.

Security Model:
    - External requests: X-Platform-* headers are stripped (cannot impersonate users)
    - Internal requests: Headers are preserved if X-Internal-Auth matches INTERNAL_SERVICE_SECRET
    - Uses constant-time comparison to prevent timing attacks

Headers Protected:
    - Any header starting with X-Platform-* (except X-Platform-Claims)
    - X-Internal-Auth (always stripped after validation)

Note: X-Adapter-* headers are NOT stripped by this middleware. They are
validated via API key scope (platform:adapter) in resolve_platform_identity().

Usage:
    This middleware should be registered early in the middleware chain (before
    any other middleware that reads platform headers).

    Platform adapters must include the X-Internal-Auth header with the shared secret
    when making requests to the API server.

Related:
    - task-686: Fix profile tracking middleware authentication bypass
    - community_dependencies.py (reads platform admin status from JWT)
"""

import logging
import secrets

from starlette.types import ASGIApp, Receive, Scope, Send

from src.config import settings

logger = logging.getLogger(__name__)

PROTECTED_HEADER_PREFIXES = (b"x-platform-",)

PROTECTED_HEADERS = {
    b"x-internal-auth",
}

ALLOWED_PLATFORM_HEADERS = {
    b"x-platform-claims",
}


def _is_protected_header(header_name: bytes) -> bool:
    """
    Check if a header should be protected (stripped from untrusted requests).

    Headers that are allowed through even from untrusted sources:
    - X-Platform-Claims: Contains signed JWT that is validated separately
                         (see src/auth/platform_claims.py)
    """
    lower_name = header_name.lower()

    if lower_name in ALLOWED_PLATFORM_HEADERS:
        return False

    if lower_name in PROTECTED_HEADERS:
        return True
    return any(lower_name.startswith(prefix) for prefix in PROTECTED_HEADER_PREFIXES)


def _validate_internal_auth(headers: list[tuple[bytes, bytes]]) -> bool:
    """
    Validate that the request has a valid internal auth header.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        headers: List of (name, value) header tuples

    Returns:
        True if the X-Internal-Auth header matches INTERNAL_SERVICE_SECRET
    """
    if not settings.INTERNAL_SERVICE_SECRET:
        return False

    for name, value in headers:
        if name.lower() == b"x-internal-auth":
            try:
                provided_secret = value.decode("utf-8")
                return secrets.compare_digest(provided_secret, settings.INTERNAL_SERVICE_SECRET)
            except (UnicodeDecodeError, AttributeError):
                return False
    return False


class InternalHeaderValidationMiddleware:
    """
    ASGI middleware that validates internal service authentication.

    This middleware strips X-Platform-* headers from requests unless they are
    accompanied by a valid X-Internal-Auth header. This prevents external
    clients from spoofing platform user identity headers.

    The X-Internal-Auth header is also stripped after validation to prevent
    leaking the secret to the application layer.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        is_internal = _validate_internal_auth(headers)

        if is_internal:
            filtered_headers = [
                (name, value) for name, value in headers if name.lower() != b"x-internal-auth"
            ]
        else:
            filtered_headers = [
                (name, value) for name, value in headers if not _is_protected_header(name)
            ]

        scope = dict(scope)
        scope["headers"] = filtered_headers

        await self.app(scope, receive, send)
