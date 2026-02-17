"""Tests for claim relevance check JSON:API router."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.claim_relevance_check.router import (
    _get_relevance_service,
    router,
)
from src.claim_relevance_check.schemas import RelevanceOutcome
from src.claim_relevance_check.service import ClaimRelevanceService


@pytest.fixture
def mock_relevance_service():
    """Create a mock ClaimRelevanceService."""
    return AsyncMock(spec=ClaimRelevanceService)


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = "test-user-id"
    return user


@pytest.fixture
def app(mock_relevance_service, mock_user):
    """Create a FastAPI app with the router mounted and dependencies overridden."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v2")

    from src.auth.dependencies import get_current_user_or_api_key
    from src.database import get_db

    test_app.dependency_overrides[get_current_user_or_api_key] = lambda: mock_user
    test_app.dependency_overrides[get_db] = lambda: AsyncMock()
    test_app.dependency_overrides[_get_relevance_service] = lambda: mock_relevance_service

    return test_app


@pytest.fixture
async def client(app):
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_request_body(
    original_message: str = "The earth is flat.",
    matched_content: str = "The Earth is not flat.",
    matched_source: str = "https://snopes.com/flat-earth",
    similarity_score: float = 0.85,
) -> dict:
    return {
        "data": {
            "type": "claim-relevance-checks",
            "attributes": {
                "original_message": original_message,
                "matched_content": matched_content,
                "matched_source": matched_source,
                "similarity_score": similarity_score,
            },
        }
    }


class TestCreateClaimRelevanceCheck:
    """Tests for POST /api/v2/claim-relevance-checks."""

    @pytest.mark.asyncio
    async def test_relevant_outcome_returns_should_flag_true(
        self, client, mock_relevance_service
    ) -> None:
        mock_relevance_service.check_relevance = AsyncMock(
            return_value=(RelevanceOutcome.RELEVANT, "Match is relevant to the claim.")
        )

        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["type"] == "claim-relevance-checks"
        assert body["data"]["attributes"]["outcome"] == "relevant"
        assert body["data"]["attributes"]["should_flag"] is True
        assert body["data"]["attributes"]["reasoning"] == "Match is relevant to the claim."
        assert "id" in body["data"]
        assert body["jsonapi"]["version"] == "1.1"

    @pytest.mark.asyncio
    async def test_not_relevant_outcome_returns_should_flag_false(
        self, client, mock_relevance_service
    ) -> None:
        mock_relevance_service.check_relevance = AsyncMock(
            return_value=(RelevanceOutcome.NOT_RELEVANT, "No claim found in message.")
        )

        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["attributes"]["outcome"] == "not_relevant"
        assert body["data"]["attributes"]["should_flag"] is False

    @pytest.mark.asyncio
    async def test_indeterminate_outcome_returns_should_flag_true(
        self, client, mock_relevance_service
    ) -> None:
        mock_relevance_service.check_relevance = AsyncMock(
            return_value=(RelevanceOutcome.INDETERMINATE, "LLM unavailable")
        )

        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["attributes"]["outcome"] == "indeterminate"
        assert body["data"]["attributes"]["should_flag"] is True

    @pytest.mark.asyncio
    async def test_content_filtered_outcome_returns_should_flag_true(
        self, client, mock_relevance_service
    ) -> None:
        mock_relevance_service.check_relevance = AsyncMock(
            return_value=(RelevanceOutcome.CONTENT_FILTERED, "Message triggered safety filter")
        )

        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["attributes"]["outcome"] == "content_filtered"
        assert body["data"]["attributes"]["should_flag"] is True

    @pytest.mark.asyncio
    async def test_invalid_request_missing_attributes(self, client) -> None:
        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json={"data": {"type": "claim-relevance-checks"}},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_request_wrong_type(self, client) -> None:
        body = _make_request_body()
        body["data"]["type"] = "wrong-type"

        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=body,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_similarity_score_above_1(self, client) -> None:
        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(similarity_score=1.5),
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_similarity_score_below_0(self, client) -> None:
        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(similarity_score=-0.1),
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_service_passes_correct_attributes(self, client, mock_relevance_service) -> None:
        mock_relevance_service.check_relevance = AsyncMock(
            return_value=(RelevanceOutcome.RELEVANT, "Relevant")
        )

        await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(
                original_message="Vaccines cause autism",
                matched_content="Vaccines do not cause autism",
                matched_source="https://example.com/vaccines",
                similarity_score=0.92,
            ),
        )

        mock_relevance_service.check_relevance.assert_called_once()
        call_kwargs = mock_relevance_service.check_relevance.call_args.kwargs
        assert call_kwargs["original_message"] == "Vaccines cause autism"
        assert call_kwargs["matched_content"] == "Vaccines do not cause autism"
        assert call_kwargs["matched_source"] == "https://example.com/vaccines"

    @pytest.mark.asyncio
    async def test_service_exception_returns_500(self, client, mock_relevance_service) -> None:
        mock_relevance_service.check_relevance = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(),
        )

        assert response.status_code == 500
        body = response.json()
        assert "errors" in body
        assert body["errors"][0]["status"] == "500"

    @pytest.mark.asyncio
    async def test_response_content_type_is_jsonapi(self, client, mock_relevance_service) -> None:
        mock_relevance_service.check_relevance = AsyncMock(
            return_value=(RelevanceOutcome.RELEVANT, "Relevant")
        )

        response = await client.post(
            "/api/v2/claim-relevance-checks",
            json=_make_request_body(),
        )

        assert "application/vnd.api+json" in response.headers["content-type"]
