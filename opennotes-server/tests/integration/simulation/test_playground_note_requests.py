from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.auth.auth import create_access_token
from src.users.models import User


@pytest.fixture
def mock_dispatch_workflow():
    with patch(
        "src.simulation.playground_jsonapi_router.dispatch_playground_url_extraction",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "playground-urls-test123"
        yield mock


@pytest.fixture
async def non_admin_user(db):
    user = User(
        id=uuid4(),
        username="sim_regular_user",
        email="sim_regular@opennotes.local",
        hashed_password="hashed_password_placeholder",
        role="user",
        is_active=True,
        is_superuser=False,
        is_service_account=False,
        discord_id=f"discord_sim_regular_{uuid4().hex[:8]}",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def non_admin_auth_headers(non_admin_user):
    token_data = {
        "sub": str(non_admin_user.id),
        "username": non_admin_user.username,
        "role": non_admin_user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


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
async def test_non_admin_returns_403(
    async_client, non_admin_auth_headers, playground_community_server
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
        headers=non_admin_auth_headers,
    )

    assert response.status_code == 403


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
async def test_non_playground_error_does_not_leak_platform(
    async_client, admin_auth_headers, community_server
):
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
    detail = response.json()["errors"][0]["detail"]
    assert "platform=" not in detail


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


@pytest.mark.asyncio
async def test_ssrf_url_returns_422(async_client, admin_auth_headers, playground_community_server):
    with patch(
        "src.simulation.playground_jsonapi_router.validate_url_security",
        side_effect=ValueError("URLs pointing to private or reserved IP ranges are not allowed"),
    ):
        response = await async_client.post(
            f"/api/v2/playgrounds/{playground_community_server}/note-requests",
            json={
                "data": {
                    "type": "playground-note-requests",
                    "attributes": {
                        "urls": ["http://192.168.1.1/internal"],
                    },
                }
            },
            headers=admin_auth_headers,
        )

    assert response.status_code == 422
    data = response.json()
    assert data["errors"][0]["title"] == "URL Validation Failed"
    assert "private or reserved" in data["errors"][0]["detail"]


@pytest.mark.asyncio
async def test_create_note_requests_with_text_only(
    async_client, admin_auth_headers, playground_community_server, db
):
    response = await async_client.post(
        f"/api/v2/playgrounds/{playground_community_server}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {
                    "texts": [
                        "Climate change is accelerating faster than predicted.",
                        "The stock market hit an all-time high today.",
                    ],
                },
            }
        },
        headers=admin_auth_headers,
    )

    assert response.status_code == 202
    data = response.json()
    assert data["jsonapi"]["version"] == "1.1"
    assert data["data"]["type"] == "playground-note-request-jobs"
    assert data["data"]["attributes"]["text_count"] == 2
    assert data["data"]["attributes"]["url_count"] == 0
    assert data["data"]["attributes"]["status"] == "ACCEPTED"
    assert data["data"]["id"] is not None

    from sqlalchemy import select

    from src.notes.models import Request

    result = await db.execute(
        select(Request).where(
            Request.community_server_id == playground_community_server,
        )
    )
    requests = result.scalars().all()
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_create_note_requests_with_text_and_urls(
    async_client,
    admin_auth_headers,
    playground_community_server,
    mock_dispatch_workflow,
):
    response = await async_client.post(
        f"/api/v2/playgrounds/{playground_community_server}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {
                    "urls": ["https://example.com/article1"],
                    "texts": ["Some claim to fact-check."],
                },
            }
        },
        headers=admin_auth_headers,
    )

    assert response.status_code == 202
    data = response.json()
    assert data["data"]["attributes"]["url_count"] == 1
    assert data["data"]["attributes"]["text_count"] == 1

    mock_dispatch_workflow.assert_called_once()
    assert len(mock_dispatch_workflow.call_args.kwargs["urls"]) == 1


@pytest.mark.asyncio
async def test_create_note_requests_text_validation_empty_string(
    async_client, admin_auth_headers, playground_community_server
):
    response = await async_client.post(
        f"/api/v2/playgrounds/{playground_community_server}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {
                    "texts": ["   "],
                },
            }
        },
        headers=admin_auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_note_requests_neither_urls_nor_texts(
    async_client, admin_auth_headers, playground_community_server
):
    response = await async_client.post(
        f"/api/v2/playgrounds/{playground_community_server}/note-requests",
        json={
            "data": {
                "type": "playground-note-requests",
                "attributes": {},
            }
        },
        headers=admin_auth_headers,
    )

    assert response.status_code == 422
