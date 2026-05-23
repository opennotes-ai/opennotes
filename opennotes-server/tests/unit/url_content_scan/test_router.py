"""Tests for url_content_scan router — public and private routes.

Verifies:
- Public /analyses/recent route still uses filtered list_recent
- Private /{prefix}/analyses/recent route returns unfiltered results
- Public route is NOT reachable at the private prefix path
- Without URL_SCAN_PRIVATE_PATH_PREFIX, register_private_url_scan_routes
  returns False and the private route is absent (404)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

SECRET_PREFIX = "test-internal-secret-xyz"

_FAKE_JOB_ID = uuid4()
_FAKE_FINISHED_AT = datetime.now(UTC)

_FAKE_RECENT_ANALYSIS = {
    "job_id": _FAKE_JOB_ID,
    "source_url": "https://example.com/article",
    "page_title": "Article Title",
    "screenshot_url": "https://signed.example/shots/a.png",
    "preview_description": "Short preview",
    "og_thumbnail_url": None,
    "completed_at": _FAKE_FINISHED_AT.isoformat(),
}

_FAKE_INTERNAL_ANALYSIS = {
    "job_id": _FAKE_JOB_ID,
    "source_url": "https://example.com/page?token=secret",
    "page_title": "Page Title",
    "screenshot_url": None,
    "preview_description": None,
    "og_thumbnail_url": None,
    "status": "partial",
    "completed_at": _FAKE_FINISHED_AT.isoformat(),
}


def _make_app_with_prefix(prefix: str | None) -> tuple[FastAPI, TestClient]:
    from src.url_content_scan.router import register_private_url_scan_routes, router

    app = FastAPI()
    app.include_router(router)

    with patch("src.url_content_scan.router.settings") as mock_settings:
        if prefix is not None:
            secret = MagicMock()
            secret.get_secret_value.return_value = prefix
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = secret
        else:
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = None
        register_private_url_scan_routes(app)

    return app, TestClient(app, raise_server_exceptions=False)


class TestPublicRecentRoute:
    def test_public_recent_route_is_registered(self) -> None:
        from src.url_content_scan.router import router

        routes = [r.path for r in router.routes]
        assert "/api/v1/url_scan/analyses/recent" in routes

    @pytest.mark.asyncio
    async def test_public_recent_calls_list_recent(self) -> None:
        from src.url_content_scan.router import router

        app = FastAPI()
        app.include_router(router)

        async def _fake_db():
            return AsyncMock()

        async def _fake_api_key():
            return MagicMock()

        from src.database import get_db
        from src.url_content_scan.auth import get_url_scan_api_key

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_url_scan_api_key] = _fake_api_key

        with (
            patch(
                "src.url_content_scan.router.list_recent",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_list_recent,
            patch("src.url_content_scan.router.get_screenshot_store"),
            TestClient(app) as client,
        ):
            resp = client.get("/api/v1/url_scan/analyses/recent")

        assert resp.status_code == 200
        mock_list_recent.assert_called_once()

    def test_public_recent_route_not_reachable_at_private_prefix(self) -> None:
        _, client = _make_app_with_prefix(SECRET_PREFIX)
        resp = client.get(f"/api/v1/url_scan/{SECRET_PREFIX}/analyses/recent-via-public")
        assert resp.status_code == 404


class TestPrivateRouteRegistration:
    def test_register_returns_false_when_prefix_is_none(self) -> None:
        from fastapi import FastAPI as _FastAPI

        from src.url_content_scan.router import register_private_url_scan_routes

        app = _FastAPI()
        with patch("src.url_content_scan.router.settings") as mock_settings:
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = None
            result = register_private_url_scan_routes(app)

        assert result is False

    def test_register_returns_false_when_prefix_is_empty_string(self) -> None:
        from fastapi import FastAPI as _FastAPI

        from src.url_content_scan.router import register_private_url_scan_routes

        app = _FastAPI()
        with patch("src.url_content_scan.router.settings") as mock_settings:
            secret = MagicMock()
            secret.get_secret_value.return_value = ""
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = secret
            result = register_private_url_scan_routes(app)

        assert result is False

    def test_register_returns_true_when_prefix_is_set(self) -> None:
        from fastapi import FastAPI as _FastAPI

        from src.url_content_scan.router import register_private_url_scan_routes

        app = _FastAPI()
        with patch("src.url_content_scan.router.settings") as mock_settings:
            secret = MagicMock()
            secret.get_secret_value.return_value = SECRET_PREFIX
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = secret
            result = register_private_url_scan_routes(app)

        assert result is True

    def test_private_route_is_404_when_prefix_not_set(self) -> None:
        from fastapi import FastAPI as _FastAPI

        from src.url_content_scan.router import register_private_url_scan_routes, router

        app = _FastAPI()
        app.include_router(router)
        with patch("src.url_content_scan.router.settings") as mock_settings:
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = None
            register_private_url_scan_routes(app)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/url_scan/{SECRET_PREFIX}/analyses/recent")
        assert resp.status_code == 404

    def test_private_route_path_contains_secret_prefix(self) -> None:
        from fastapi import FastAPI as _FastAPI

        from src.url_content_scan.router import register_private_url_scan_routes

        app = _FastAPI()
        with patch("src.url_content_scan.router.settings") as mock_settings:
            secret = MagicMock()
            secret.get_secret_value.return_value = SECRET_PREFIX
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = secret
            register_private_url_scan_routes(app)

        route_paths = [r.path for r in app.routes]
        assert any(SECRET_PREFIX in p for p in route_paths)

    @pytest.mark.asyncio
    async def test_private_route_calls_list_recent_unfiltered(self) -> None:
        from fastapi import FastAPI as _FastAPI

        from src.database import get_db
        from src.url_content_scan.router import register_private_url_scan_routes, router

        app = _FastAPI()
        app.include_router(router)

        async def _fake_db():
            return AsyncMock()

        app.dependency_overrides[get_db] = _fake_db

        with patch("src.url_content_scan.router.settings") as mock_settings:
            secret = MagicMock()
            secret.get_secret_value.return_value = SECRET_PREFIX
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = secret
            register_private_url_scan_routes(app)

        with (
            patch(
                "src.url_content_scan.router.list_recent_unfiltered",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_unfiltered,
            patch("src.url_content_scan.router.get_screenshot_store"),
            TestClient(app) as client,
        ):
            resp = client.get(f"/api/v1/url_scan/{SECRET_PREFIX}/analyses/recent")

        assert resp.status_code == 200
        mock_unfiltered.assert_called_once()

    def test_public_recent_route_not_accessible_at_private_prefix(self) -> None:
        from fastapi import FastAPI as _FastAPI

        from src.url_content_scan.router import register_private_url_scan_routes, router

        app = _FastAPI()
        app.include_router(router)

        with patch("src.url_content_scan.router.settings") as mock_settings:
            secret = MagicMock()
            secret.get_secret_value.return_value = SECRET_PREFIX
            mock_settings.URL_SCAN_PRIVATE_PATH_PREFIX = secret
            register_private_url_scan_routes(app)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/url_scan/{SECRET_PREFIX}/jobs/some-uuid")
        assert resp.status_code == 404
