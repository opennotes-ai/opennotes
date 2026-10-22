from importlib import import_module
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from src.services.firecrawl_client import FirecrawlError

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.mark.parametrize(
    ("route_name", "dependency", "error"),
    [
        ("frame_compat_route", "frame_compat", httpx.HTTPError("synthetic-private-stack")),
        ("frame_compat_route", "frame_compat", RuntimeError("synthetic-private-stack")),
        ("screenshot_route", "lookup_screenshot", RuntimeError("synthetic-private-stack")),
        ("archive_preview_route", "archive_preview", RuntimeError("synthetic-private-stack")),
        ("archive_preview_route", "archive_preview", FirecrawlError("synthetic-private-stack")),
    ],
)
async def test_upstream_exceptions_are_not_returned(monkeypatch, route_name, dependency, error):
    module = import_module("src.url_content_scan.router")

    monkeypatch.setattr(module, dependency, AsyncMock(side_effect=error))
    monkeypatch.setattr(module, "get_scrape_cache", lambda request: object())
    monkeypatch.setattr(module, "get_screenshot_store", lambda request: object())
    monkeypatch.setattr(module, "_get_optional_scrape_cache", lambda request: None)
    monkeypatch.setattr(
        module, "_resolve_archive_url", AsyncMock(return_value="https://example.com")
    )
    kwargs = {"request": MagicMock(), "url": "https://example.com", "_api_key": MagicMock()}
    if route_name == "frame_compat_route":
        kwargs["job_id"] = None
    elif route_name == "archive_preview_route":
        kwargs.update(job_id=None, generate=False, source_type="url", db=AsyncMock())

    response = await getattr(module, route_name)(**kwargs)

    assert response.status_code == 502
    assert b"synthetic-private-stack" not in response.body
    assert b'"error_code":"upstream_error"' in response.body


async def test_http_server_exception_details_are_not_returned():
    from src.url_content_scan.router import _http_exception_response

    response = _http_exception_response(HTTPException(503, "synthetic-private-stack"))

    assert response.status_code == 503
    assert b"synthetic-private-stack" not in response.body


async def test_safe_client_error_details_and_headers_are_preserved():
    from src.url_content_scan.router import _http_exception_response

    response = _http_exception_response(
        HTTPException(400, "Invalid job_id", headers={"X-Test": "preserved"})
    )

    assert response.status_code == 400
    assert b"Invalid job_id" in response.body
    assert response.headers["X-Test"] == "preserved"


@pytest.mark.parametrize("path", ["frame-compat", "screenshot", "archive-preview"])
async def test_http_response_does_not_expose_upstream_exception(monkeypatch, path):
    module = import_module("src.url_content_scan.router")
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_url_scan_api_key] = lambda: MagicMock()
    app.dependency_overrides[module.get_db] = lambda: AsyncMock()
    monkeypatch.setattr(
        module, "get_scrape_cache", MagicMock(side_effect=RuntimeError("synthetic-private-stack"))
    )
    monkeypatch.setattr(
        module,
        "_get_optional_scrape_cache",
        MagicMock(side_effect=RuntimeError("synthetic-private-stack")),
    )
    monkeypatch.setattr(
        module, "_resolve_archive_url", AsyncMock(return_value="https://example.com")
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/v1/url_scan/{path}", params={"url": "https://example.com"}
        )

    assert response.status_code == 502
    assert response.json()["error_code"] == "upstream_error"
    assert "synthetic-private-stack" not in response.text
