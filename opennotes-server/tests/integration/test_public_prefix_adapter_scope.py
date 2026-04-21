"""Authorization contract tests for the /api/public/v1 adapter surface."""

from __future__ import annotations

import importlib
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from tests.fixtures.principal_factory import make_human_user, make_jwt_headers

DISCOURSE_DEV_API_KEY = "opk_discourse_dev_platform_adapter_2026"
PLAYGROUND_DEV_API_KEY = "opk_playground_dev_readonly_access_key_2024"


@pytest.fixture(autouse=True)
async def ensure_app_started() -> None:
    app.state.startup_complete = True


@pytest.fixture
async def seeded_api_keys(db_session) -> None:
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")
    await seed_mod.seed_playground_api_key(db_session)
    await seed_mod.seed_discourse_api_key(db_session)
    await db_session.commit()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_playground_key_rejected_on_public_prefix(
    seeded_api_keys: None,
    client: AsyncClient,
) -> None:
    headers = {"X-API-Key": PLAYGROUND_DEV_API_KEY}

    public_resp = await client.get("/api/public/v1/notes", headers=headers)
    legacy_resp = await client.get("/api/v2/notes", headers=headers)

    assert public_resp.status_code == 403
    assert legacy_resp.status_code == 200


@pytest.mark.asyncio
async def test_jwt_user_rejected_on_public_prefix(db_session, client: AsyncClient) -> None:
    user = await make_human_user(db_session)
    await db_session.commit()
    headers = make_jwt_headers(user)

    public_resp = await client.get("/api/public/v1/notes", headers=headers)
    legacy_resp = await client.get("/api/v2/notes", headers=headers)

    assert public_resp.status_code == 403
    assert legacy_resp.status_code == 200


@pytest.mark.asyncio
async def test_adapter_key_accepted_on_public_prefix(
    seeded_api_keys: None,
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/public/v1/notes",
        headers={"X-API-Key": DISCOURSE_DEV_API_KEY},
    )

    assert response.status_code < 500
    assert response.status_code != 403
