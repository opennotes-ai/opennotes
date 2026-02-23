from unittest.mock import patch
from uuid import uuid4

import pendulum
import pytest

from src.shared.content_extraction import ExtractedContent


@pytest.fixture
def mock_extract_content():
    with patch("src.simulation.playground_jsonapi_router.extract_content_from_url") as mock:
        mock.return_value = ExtractedContent(
            text="This is extracted article content for testing.",
            url="https://example.com/article",
            domain="example.com",
            extracted_at=pendulum.now("UTC"),
            title="Test Article",
        )
        yield mock


@pytest.mark.asyncio
async def test_create_note_requests_full_flow(
    async_client, auth_headers, playground_community_server, mock_extract_content
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
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["jsonapi"]["version"] == "1.1"
    assert len(data["data"]) == 2
    assert data["meta"]["count"] == 2
    assert data["meta"]["succeeded"] == 2
    assert data["meta"]["failed"] == 0

    for item in data["data"]:
        assert item["type"] == "requests"
        assert item["attributes"]["status"] == "PENDING"
        assert item["attributes"]["community_server_id"] == str(playground_community_server)
        assert item["attributes"]["requested_by"] == "system-playground"
        assert item["attributes"]["request_id"].startswith("playground-")
        assert item["attributes"]["content"] is not None


@pytest.mark.asyncio
async def test_create_note_requests_custom_requested_by(
    async_client, auth_headers, playground_community_server, mock_extract_content
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
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["data"][0]["attributes"]["requested_by"] == "custom-user"


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
async def test_non_playground_rejected(async_client, auth_headers, community_server):
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
        headers=auth_headers,
    )

    assert response.status_code == 400
    data = response.json()
    assert data["errors"][0]["title"] == "Bad Request"
    assert "not a playground" in data["errors"][0]["detail"]


@pytest.mark.asyncio
async def test_nonexistent_community_server(async_client, auth_headers):
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
        headers=auth_headers,
    )

    assert response.status_code == 404
    data = response.json()
    assert data["errors"][0]["title"] == "Not Found"


@pytest.mark.asyncio
async def test_handles_extraction_failure_per_url(
    async_client, auth_headers, playground_community_server
):
    from src.shared.content_extraction import ContentExtractionError

    async def side_effect(url, config=None):
        if "good-article" in str(url):
            return ExtractedContent(
                text="Good content",
                url=url,
                domain="example.com",
                extracted_at=pendulum.now("UTC"),
                title="Good Article",
            )
        raise ContentExtractionError(f"Failed to extract from {url}")

    with patch(
        "src.simulation.playground_jsonapi_router.extract_content_from_url",
        side_effect=side_effect,
    ):
        response = await async_client.post(
            f"/api/v2/playgrounds/{playground_community_server}/note-requests",
            json={
                "data": {
                    "type": "playground-note-requests",
                    "attributes": {
                        "urls": [
                            "https://example.com/good-article",
                            "https://example.com/bad-article",
                        ],
                    },
                }
            },
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["meta"]["succeeded"] == 1
    assert data["meta"]["failed"] == 1

    statuses = [item["attributes"]["status"] for item in data["data"]]
    assert "PENDING" in statuses
    assert "FAILED" in statuses

    failed_item = next(item for item in data["data"] if item["attributes"]["status"] == "FAILED")
    assert failed_item["attributes"]["error"] is not None
