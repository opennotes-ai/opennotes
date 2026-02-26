from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_dispatch_workflow():
    with patch(
        "src.simulation.playground_jsonapi_router.dispatch_playground_url_extraction",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "playground-urls-test123"
        yield mock


@pytest.mark.asyncio
async def test_create_note_requests_returns_202_with_workflow_id(
    async_client, admin_auth_headers, playground_community_server, mock_dispatch_workflow
):
    response = await async_client.post(
        f"/api/v2/playgrounds/{playground_community_server}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {
                    "urls": ["https://example.com/article1", "https://example.com/article2"],
                },
            }
        },
        headers=admin_auth_headers,
    )

    assert response.status_code == 202
    data = response.json()
    assert data["jsonapi"]["version"] == "1.1"
    assert data["data"]["type"] == "playground-note-request-jobs"
    assert data["data"]["id"] == "playground-urls-test123"
    assert data["data"]["attributes"]["workflow_id"] == "playground-urls-test123"
    assert data["data"]["attributes"]["url_count"] == 2
    assert data["data"]["attributes"]["status"] == "ACCEPTED"

    mock_dispatch_workflow.assert_called_once()
    call_kwargs = mock_dispatch_workflow.call_args
    assert len(call_kwargs.kwargs["urls"]) == 2
    assert call_kwargs.kwargs["community_server_id"] == playground_community_server
    assert call_kwargs.kwargs["requested_by"] == "system-playground"


@pytest.mark.asyncio
async def test_create_note_requests_custom_requested_by(
    async_client, admin_auth_headers, playground_community_server, mock_dispatch_workflow
):
    response = await async_client.post(
        f"/api/v2/playgrounds/{playground_community_server}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {
                    "urls": ["https://example.com/article1"],
                    "requested_by": "custom-user",
                },
            }
        },
        headers=admin_auth_headers,
    )

    assert response.status_code == 202
    mock_dispatch_workflow.assert_called_once()
    assert mock_dispatch_workflow.call_args.kwargs["requested_by"] == "custom-user"


@pytest.mark.asyncio
async def test_auth_required(async_client, playground_community_server):
    response = await async_client.post(
        f"/api/v2/playgrounds/{playground_community_server}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {
                    "urls": ["https://example.com/article"],
                },
            }
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_playground_rejected(async_client, admin_auth_headers, community_server):
    response = await async_client.post(
        f"/api/v2/playgrounds/{community_server}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {
                    "urls": ["https://example.com/article"],
                },
            }
        },
        headers=admin_auth_headers,
    )

    assert response.status_code == 400
    data = response.json()
    assert data["errors"][0]["title"] == "Bad Request"
    assert "not a playground" in data["errors"][0]["detail"]


@pytest.mark.asyncio
async def test_nonexistent_community_server(async_client, admin_auth_headers):
    fake_id = uuid4()
    response = await async_client.post(
        f"/api/v2/playgrounds/{fake_id}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {
                    "urls": ["https://example.com/article"],
                },
            }
        },
        headers=admin_auth_headers,
    )

    assert response.status_code == 404
    data = response.json()
    assert data["errors"][0]["title"] == "Not Found"


@pytest.mark.asyncio
async def test_dispatch_failure_returns_500(
    async_client, admin_auth_headers, playground_community_server
):
    with patch(
        "src.simulation.playground_jsonapi_router.dispatch_playground_url_extraction",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DBOS connection failed"),
    ):
        response = await async_client.post(
            f"/api/v2/playgrounds/{playground_community_server}/note-requests",
            json={
                "data": {
                    "type": "playground-note-requests",
                    "attributes": {
                        "urls": ["https://example.com/article"],
                    },
                }
            },
            headers=admin_auth_headers,
        )

    assert response.status_code == 500
    data = response.json()
    assert data["errors"][0]["title"] == "Internal Server Error"
