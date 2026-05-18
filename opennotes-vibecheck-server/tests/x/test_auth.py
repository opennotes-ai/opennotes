from __future__ import annotations

import httpx
import pytest

from src.config import Settings
from src.x.auth import clear_x_bearer_cache, get_x_bearer


@pytest.fixture(autouse=True)
def _clear_token_cache() -> None:
    clear_x_bearer_cache()


async def test_get_x_bearer_prefers_explicit_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("token exchange should not run when bearer token is set")

    settings = Settings(VIBECHECK_X_BEARER_TOKEN="explicit-token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        bearer = await get_x_bearer(settings, http)

    assert bearer == "explicit-token"


async def test_get_x_bearer_exchanges_consumer_credentials() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "https://api.x.com/oauth2/token"
        assert request.headers["authorization"].startswith("Basic ")
        assert request.content == b"grant_type=client_credentials"
        return httpx.Response(200, json={"access_token": "exchanged-token", "expires_in": 3600})

    settings = Settings(
        VIBECHECK_X_CONSUMER_KEY="consumer-key",
        VIBECHECK_X_SECRET_KEY="consumer-secret",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        first = await get_x_bearer(settings, http)
        second = await get_x_bearer(settings, http)

    assert first == "exchanged-token"
    assert second == "exchanged-token"
    assert len(requests) == 1


async def test_get_x_bearer_returns_none_without_credentials() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("token exchange should not run without credentials")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        bearer = await get_x_bearer(Settings(), http)

    assert bearer is None
