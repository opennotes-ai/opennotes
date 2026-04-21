from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.auth.dependencies import require_platform_adapter


def _request_with_api_key(api_key: object | None = None) -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/"})
    if api_key is not None:
        request.state.api_key = api_key
    return request


@pytest.mark.asyncio
async def test_require_platform_adapter_rejects_jwt_user_without_api_key() -> None:
    with pytest.raises(HTTPException) as exc:
        await require_platform_adapter(
            current_user=SimpleNamespace(id="user-1"),
            request=_request_with_api_key(),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Platform adapter API key required"


@pytest.mark.asyncio
async def test_require_platform_adapter_rejects_wrong_scope_api_key() -> None:
    api_key = SimpleNamespace(has_scope=lambda scope: False)

    with pytest.raises(HTTPException) as exc:
        await require_platform_adapter(
            current_user=SimpleNamespace(id="user-1"),
            request=_request_with_api_key(api_key),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "API key lacks required scope"


@pytest.mark.asyncio
async def test_require_platform_adapter_returns_user_for_adapter_key() -> None:
    user = SimpleNamespace(id="user-1")
    api_key = SimpleNamespace(has_scope=lambda scope: scope == "platform:adapter")

    result = await require_platform_adapter(
        current_user=user,
        request=_request_with_api_key(api_key),
    )

    assert result is user
