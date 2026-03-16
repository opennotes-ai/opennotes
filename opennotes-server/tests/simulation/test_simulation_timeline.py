from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def completed_sim(simulation_run_factory):
    return await simulation_run_factory(status_val="completed")


@pytest.mark.asyncio
async def test_timeline_endpoint_returns_buckets(
    admin_auth_client: AsyncClient,
    completed_sim,
):
    response = await admin_auth_client.get(
        f"/api/v2/simulations/{completed_sim['id']}/analysis/timeline"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["jsonapi"]["version"] == "1.1"
    assert body["data"]["type"] == "simulation-timeline"
    attrs = body["data"]["attributes"]
    assert "buckets" in attrs
    assert "bucket_size" in attrs
    assert isinstance(attrs["total_notes"], int)
    assert isinstance(attrs["total_ratings"], int)


@pytest.mark.asyncio
async def test_timeline_endpoint_respects_bucket_size_param(
    admin_auth_client: AsyncClient,
    completed_sim,
):
    response = await admin_auth_client.get(
        f"/api/v2/simulations/{completed_sim['id']}/analysis/timeline?bucket_size=hour"
    )
    assert response.status_code == 200
    attrs = response.json()["data"]["attributes"]
    assert attrs["bucket_size"] == "hour"


@pytest.mark.asyncio
async def test_timeline_endpoint_404_for_nonexistent(
    admin_auth_client: AsyncClient,
):
    fake_id = str(uuid4())
    response = await admin_auth_client.get(f"/api/v2/simulations/{fake_id}/analysis/timeline")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_timeline_endpoint_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v2/simulations/{uuid4()}/analysis/timeline")
        assert response.status_code == 401
