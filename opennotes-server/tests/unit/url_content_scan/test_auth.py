from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.users.models import APIKey

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _make_request() -> MagicMock:
    request = MagicMock()
    request.state = SimpleNamespace()
    return request


def _make_api_key(scopes: list[str]) -> APIKey:
    api_key = MagicMock(spec=APIKey)
    api_key.scopes = scopes
    api_key.has_scope.side_effect = lambda scope: scope in scopes
    return api_key


async def test_get_url_scan_api_key_rejects_missing_credentials():
    from src.url_content_scan.auth import UrlScanAuthError, get_url_scan_api_key

    with pytest.raises(UrlScanAuthError) as exc_info:
        await get_url_scan_api_key(
            request=_make_request(),
            credentials=None,
            x_api_key=None,
            db=AsyncMock(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "unauthorized"
    assert exc_info.value.message == "Missing API key credentials"


async def test_get_url_scan_api_key_rejects_jwt_without_invoking_jwt_or_user_loader():
    from src.url_content_scan.auth import get_url_scan_api_key

    request = _make_request()
    bearer = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake.payload",
    )

    with (
        patch("src.url_content_scan.auth.verify_api_key", new=AsyncMock()) as mock_verify_api_key,
        patch(
            "src.auth.auth.verify_token",
            new=AsyncMock(side_effect=AssertionError("JWT verification path invoked")),
        ),
        patch(
            "src.users.crud.get_user_by_id",
            new=AsyncMock(side_effect=AssertionError("user loader path invoked")),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_url_scan_api_key(
            request=request,
            credentials=bearer,
            x_api_key=None,
            db=AsyncMock(),
        )

    assert exc_info.value.status_code == 401
    mock_verify_api_key.assert_not_awaited()


async def test_get_url_scan_api_key_rejects_key_missing_scope():
    from src.url_content_scan.auth import UrlScanAuthError, get_url_scan_api_key

    request = _make_request()
    api_key = _make_api_key(scopes=["notes:read"])

    with (
        patch(
            "src.url_content_scan.auth.verify_api_key",
            new=AsyncMock(return_value=(api_key, MagicMock())),
        ),
        pytest.raises(UrlScanAuthError) as exc_info,
    ):
        await get_url_scan_api_key(
            request=request,
            credentials=None,
            x_api_key="opk_vibecheck_missing_scope_secret",
            db=AsyncMock(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "forbidden"
    assert exc_info.value.message == "API key lacks required scope"


async def test_get_url_scan_api_key_accepts_scoped_key_and_attaches_it_to_request():
    from src.url_content_scan.auth import VIBECHECK_SUBMIT_SCOPE, get_url_scan_api_key

    request = _make_request()
    api_key = _make_api_key(scopes=[VIBECHECK_SUBMIT_SCOPE])

    with (
        patch(
            "src.url_content_scan.auth.verify_api_key",
            new=AsyncMock(return_value=(api_key, MagicMock())),
        ),
    ):
        result = await get_url_scan_api_key(
            request=request,
            credentials=None,
            x_api_key="opk_vibecheck_submit_secret",
            db=AsyncMock(),
        )

    assert result is api_key
    assert request.state.api_key is api_key
    assert request.state.url_scan_api_key is api_key
