from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.monitoring.health import VersionResponse


def _make_app():
    from fastapi import FastAPI

    from src.health import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_version_returns_200_with_correct_structure():
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/version")

    assert resp.status_code == 200
    data = resp.json()
    assert "git_sha" in data
    assert "build_date" in data
    assert "revision" in data


@pytest.mark.asyncio
async def test_version_populated_from_settings():
    mock_settings = MagicMock()
    mock_settings.VCS_REF = "abc123def"
    mock_settings.BUILD_DATE = "2026-02-14T12:00:00Z"
    mock_settings.K_REVISION = "opennotes-server-00042-xyz"

    with patch("src.health.settings", mock_settings):
        app = _make_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/version")

    assert resp.status_code == 200
    data = resp.json()
    assert data["git_sha"] == "abc123def"
    assert data["build_date"] == "2026-02-14T12:00:00Z"
    assert data["revision"] == "opennotes-server-00042-xyz"


@pytest.mark.asyncio
async def test_version_returns_null_when_unset():
    mock_settings = MagicMock()
    mock_settings.VCS_REF = None
    mock_settings.BUILD_DATE = None
    mock_settings.K_REVISION = None

    with patch("src.health.settings", mock_settings):
        app = _make_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/version")

    assert resp.status_code == 200
    data = resp.json()
    assert data["git_sha"] is None
    assert data["build_date"] is None
    assert data["revision"] is None


def test_version_response_model():
    model = VersionResponse(
        git_sha="abc123",
        build_date="2026-01-01T00:00:00Z",
        revision="rev-1",
    )
    assert model.git_sha == "abc123"
    assert model.build_date == "2026-01-01T00:00:00Z"
    assert model.revision == "rev-1"


def test_version_response_model_defaults():
    model = VersionResponse()
    assert model.git_sha is None
    assert model.build_date is None
    assert model.revision is None
