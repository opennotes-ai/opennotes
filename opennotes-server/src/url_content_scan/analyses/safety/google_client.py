from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

_logger = logging.getLogger(__name__)
_creds_lock = threading.RLock()
_cached_credentials: dict[tuple[str, ...], Any] = {}


def _load_access_token(scope: str) -> str | None:
    scope_key = (scope,)
    try:
        from google.auth import default as google_auth_default  # noqa: PLC0415
        from google.auth.transport.requests import Request as GoogleAuthRequest  # noqa: PLC0415
    except ImportError:
        _logger.warning("google-auth not installed; cannot fetch ADC token")
        return None

    with _creds_lock:
        credentials = _cached_credentials.get(scope_key)
        if credentials is None:
            try:
                credentials, _project = google_auth_default(scopes=[scope])
            except Exception as exc:
                _logger.warning("ADC lookup failed for scope=%s: %s", scope, exc)
                return None
            _cached_credentials[scope_key] = credentials

        try:
            if not getattr(credentials, "valid", False):
                credentials.refresh(GoogleAuthRequest())
        except Exception as exc:
            _logger.warning("ADC token refresh failed for scope=%s: %s", scope, exc)
            return None
        token = getattr(credentials, "token", None)
        return token if isinstance(token, str) and token else None


async def get_access_token(scope: str = CLOUD_PLATFORM_SCOPE) -> str | None:
    return await asyncio.to_thread(_load_access_token, scope)


def reset_cached_credentials_for_tests() -> None:
    with _creds_lock:
        _cached_credentials.clear()
