"""Shared Application Default Credentials (ADC) OAuth2 token helper for GCP APIs.

Used by the TASK-1474 Web Risk, Vision, Natural Language, and Fact Check Tools
clients. Each caller passes the scope it needs (typically
`https://www.googleapis.com/auth/cloud-platform`); credentials are cached in
a module-level dict keyed by scope-tuple to avoid refreshing on every request
while still keeping distinct scopes separate.

Returns `None` on any auth failure so callers can decide whether to raise a
transient error (new-style TASK-1474 slot workers) or short-circuit to an
empty result (existing `known_misinfo.py` pattern).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

_logger = logging.getLogger(__name__)
_creds_lock = threading.RLock()
_cached_credentials: dict[tuple[str, ...], Any] = {}


def get_access_token(scope: str = CLOUD_PLATFORM_SCOPE) -> str | None:
    """Fetch an OAuth2 access token via Application Default Credentials.

    Cached per-scope at module level; refreshed on demand. Returns None on
    any auth failure so callers can raise or swallow as appropriate.
    """
    scope_key: tuple[str, ...] = (scope,)
    try:
        from google.auth import default as google_auth_default  # noqa: PLC0415
        from google.auth.transport.requests import Request as GoogleAuthRequest  # noqa: PLC0415
    except ImportError:
        _logger.warning("google-auth not installed; cannot fetch ADC token")
        return None

    with _creds_lock:
        creds = _cached_credentials.get(scope_key)
        if creds is None:
            try:
                creds, _project = google_auth_default(scopes=[scope])
            except Exception as exc:
                _logger.warning("ADC lookup failed for scope=%s: %s", scope, exc)
                return None
            _cached_credentials[scope_key] = creds

        try:
            if not getattr(creds, "valid", False):
                creds.refresh(GoogleAuthRequest())
        except Exception as exc:
            _logger.warning("ADC token refresh failed for scope=%s: %s", scope, exc)
            return None
        token = getattr(creds, "token", None)
        return token if isinstance(token, str) and token else None


def reset_cached_credentials_for_tests() -> None:
    """Test-only: drop the module-level credential cache."""
    with _creds_lock:
        _cached_credentials.clear()
