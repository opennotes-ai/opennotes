import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def openapi_client():
    """
    Client with OpenAPI endpoints enabled for testing API documentation.

    The main app disables OpenAPI when DEBUG=False. This fixture creates
    a separate app instance with OpenAPI enabled to test documentation
    availability.
    """
    from src.config import settings
    from src.health import router as health_router
    from src.notes.scoring_jsonapi_router import router as scoring_router

    debug_app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V2_PREFIX}/openapi.json",
        docs_url=f"{settings.API_V2_PREFIX}/docs",
        redoc_url=f"{settings.API_V2_PREFIX}/redoc",
    )
    debug_app.include_router(health_router)
    debug_app.include_router(
        scoring_router, prefix=f"{settings.API_V2_PREFIX}/scoring", tags=["scoring"]
    )

    transport = ASGITransport(app=debug_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


async def test_scoring_health(client: AsyncClient) -> None:
    response = await client.get("/api/v2/scoring/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "scoring"


async def test_score_notes_missing_fields(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v2/scoring/score",
        json={
            "data": {
                "type": "scoring-requests",
                "attributes": {
                    "notes": [],
                    "ratings": [],
                },
            }
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_score_notes_empty_lists(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v2/scoring/score",
        json={
            "data": {
                "type": "scoring-requests",
                "attributes": {
                    "notes": [],
                    "ratings": [],
                    "enrollment": [],
                },
            }
        },
        headers=auth_headers,
    )
    assert response.status_code == 400
    data = response.json()
    assert "errors" in data
    assert any("empty" in str(err.get("detail", "")).lower() for err in data["errors"])


async def test_score_notes_valid_minimal(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    request_data = {
        "data": {
            "type": "scoring-requests",
            "attributes": {
                "notes": [
                    {
                        "noteId": 1,
                        "noteAuthorParticipantId": "author1",
                        "createdAtMillis": 1234567890,
                        "tweetId": "100",
                        "summary": "Test note",
                        "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
                    }
                ],
                "ratings": [
                    {
                        "raterParticipantId": "rater1",
                        "noteId": 1,
                        "createdAtMillis": 1234567900,
                        "helpfulnessLevel": "HELPFUL",
                    }
                ],
                "enrollment": [
                    {
                        "participantId": "author1",
                        "enrollmentState": "EARNED_IN",
                        "successfulRatingNeededToEarnIn": 0,
                        "timestampOfLastStateChange": 1234567890,
                    },
                    {
                        "participantId": "rater1",
                        "enrollmentState": "EARNED_IN",
                        "successfulRatingNeededToEarnIn": 0,
                        "timestampOfLastStateChange": 1234567890,
                    },
                ],
            },
        }
    }

    response = await client.post("/api/v2/scoring/score", json=request_data, headers=auth_headers)

    if response.status_code != 200:
        print(f"Error response: {response.json()}")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert data["data"]["type"] == "scoring-results"
    attrs = data["data"]["attributes"]
    assert "scored_notes" in attrs
    assert "helpful_scores" in attrs
    assert "auxiliary_info" in attrs
    assert isinstance(attrs["scored_notes"], list)
    assert isinstance(attrs["helpful_scores"], list)
    assert isinstance(attrs["auxiliary_info"], list)


async def test_openapi_docs_available_in_debug(openapi_client: AsyncClient) -> None:
    """Test OpenAPI docs UI is available when enabled."""
    response = await openapi_client.get("/api/v2/docs")
    assert response.status_code == 200


async def test_openapi_spec_available_in_debug(openapi_client: AsyncClient) -> None:
    """Test OpenAPI JSON spec is available when enabled."""
    response = await openapi_client.get("/api/v2/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data
