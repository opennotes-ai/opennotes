from __future__ import annotations

import asyncio

import google.auth
import google.auth.transport.requests

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


async def get_access_token() -> str | None:
    def _load_token() -> str | None:
        credentials, _project = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
        credentials.refresh(google.auth.transport.requests.Request())
        return getattr(credentials, "token", None)

    return await asyncio.to_thread(_load_token)
