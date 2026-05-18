from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from src.config import Settings

_TOKEN_URL = "https://api.x.com/oauth2/token"
_EXPIRY_SKEW_SECONDS = 60


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float


_cached: list[_CachedToken | None] = [None]


def clear_x_bearer_cache() -> None:
    _cached[0] = None


def _nonempty(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    return stripped or None


async def get_x_bearer(settings: Settings, http: httpx.AsyncClient) -> str | None:
    explicit = _nonempty(settings.VIBECHECK_X_BEARER_TOKEN)
    if explicit is not None:
        return explicit

    consumer_key = _nonempty(settings.VIBECHECK_X_CONSUMER_KEY)
    secret_key = _nonempty(settings.VIBECHECK_X_SECRET_KEY)
    if consumer_key is None or secret_key is None:
        return None

    now = time.time()
    cached = _cached[0]
    if cached is not None and cached.expires_at > now:
        return cached.access_token

    response = await http.post(
        _TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(consumer_key, secret_key),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code >= 400:
        return None
    payload = response.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return None
    expires_in = payload.get("expires_in")
    ttl = int(expires_in) if isinstance(expires_in, int | str) and str(expires_in).isdigit() else 3600

    _cached[0] = _CachedToken(
        access_token=access_token,
        expires_at=now + max(0, ttl - _EXPIRY_SKEW_SECONDS),
    )
    return access_token
