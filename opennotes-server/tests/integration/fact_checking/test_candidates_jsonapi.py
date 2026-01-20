"""Integration tests for fact-check candidates JSON:API endpoints.

Tests the /api/v1/fact-checking/candidates endpoints for:
- Listing candidates with pagination and filtering
- Setting ratings on individual candidates
- Bulk approval from predicted_ratings

Reference: https://jsonapi.org/format/
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.jsonapi import JSONAPI_CONTENT_TYPE
from src.fact_checking.candidate_models import (
    CandidateStatus,
    FactCheckedItemCandidate,
    compute_claim_hash,
)
from src.main import app


@pytest.fixture
async def test_candidates(db_session: AsyncSession) -> list[FactCheckedItemCandidate]:
    """Create test candidates with various statuses and ratings."""
    candidates = []

    candidate1 = FactCheckedItemCandidate(
        id=uuid4(),
        source_url="https://example.com/article-1",
        claim_hash=compute_claim_hash("Claim 1 text"),
        title="Test Article 1",
        content="Full article content for article 1",
        dataset_name="test_dataset",
        dataset_tags=["snopes", "test"],
        status=CandidateStatus.SCRAPED.value,
        rating=None,
        predicted_ratings={"false": 1.0},
    )
    db_session.add(candidate1)
    candidates.append(candidate1)

    candidate2 = FactCheckedItemCandidate(
        id=uuid4(),
        source_url="https://example.com/article-2",
        claim_hash=compute_claim_hash("Claim 2 text"),
        title="Test Article 2",
        content="Full article content for article 2",
        dataset_name="test_dataset",
        dataset_tags=["politifact", "test"],
        status=CandidateStatus.SCRAPED.value,
        rating="true",
        predicted_ratings=None,
    )
    db_session.add(candidate2)
    candidates.append(candidate2)

    candidate3 = FactCheckedItemCandidate(
        id=uuid4(),
        source_url="https://example.com/article-3",
        claim_hash=compute_claim_hash("Claim 3 text"),
        title="Test Article 3",
        content=None,
        dataset_name="other_dataset",
        dataset_tags=["snopes"],
        status=CandidateStatus.PENDING.value,
        rating=None,
        predicted_ratings={"mostly_false": 0.85},
    )
    db_session.add(candidate3)
    candidates.append(candidate3)

    candidate4 = FactCheckedItemCandidate(
        id=uuid4(),
        source_url="https://example.com/article-4",
        claim_hash=compute_claim_hash("Claim 4 text"),
        title="Test Article 4",
        content="Full article content for article 4",
        dataset_name="test_dataset",
        dataset_tags=["snopes", "test"],
        status=CandidateStatus.SCRAPED.value,
        rating=None,
        predicted_ratings={"misleading": 1},
    )
    db_session.add(candidate4)
    candidates.append(candidate4)

    await db_session.commit()
    for c in candidates:
        await db_session.refresh(c)

    return candidates


class TestListCandidatesJSONAPI:
    """Tests for GET /api/v1/fact-checking/candidates endpoint."""

    @pytest.mark.asyncio
    async def test_list_candidates_returns_jsonapi_format(self, api_key_headers, test_candidates):
        """Response follows JSON:API structure with data, jsonapi, links, meta."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/fact-checking/candidates",
                headers=api_key_headers,
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == JSONAPI_CONTENT_TYPE

        data = response.json()
        assert "data" in data
        assert "jsonapi" in data
        assert data["jsonapi"]["version"] == "1.1"
        assert "links" in data
        assert "meta" in data

    @pytest.mark.asyncio
    async def test_list_candidates_pagination(self, api_key_headers, test_candidates):
        """Pagination with page[number] and page[size] works correctly."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/fact-checking/candidates",
                params={"page[number]": 1, "page[size]": 2},
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["meta"]["count"] == 4

    @pytest.mark.asyncio
    async def test_list_candidates_filter_by_status(self, api_key_headers, test_candidates):
        """Filter by status returns only matching candidates."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/fact-checking/candidates",
                params={"filter[status]": "scraped"},
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert all(item["attributes"]["status"] == "scraped" for item in data["data"])
        assert data["meta"]["count"] == 3

    @pytest.mark.asyncio
    async def test_list_candidates_filter_by_dataset_tags(self, api_key_headers, test_candidates):
        """Filter by dataset_tags uses array overlap."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/fact-checking/candidates",
                params={"filter[dataset_tags]": ["politifact"]},
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["count"] == 1
        assert "politifact" in data["data"][0]["attributes"]["dataset_tags"]

    @pytest.mark.asyncio
    async def test_list_candidates_filter_rating_null(self, api_key_headers, test_candidates):
        """Filter rating=null returns candidates without rating."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/fact-checking/candidates",
                params={"filter[rating]": "null"},
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["count"] == 3
        assert all(item["attributes"]["rating"] is None for item in data["data"])

    @pytest.mark.asyncio
    async def test_list_candidates_filter_has_content(self, api_key_headers, test_candidates):
        """Filter has_content=true returns only candidates with content."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/fact-checking/candidates",
                params={"filter[has_content]": "true"},
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["count"] == 3
        assert all(item["attributes"]["content"] is not None for item in data["data"])


class TestSetRatingJSONAPI:
    """Tests for POST /api/v1/fact-checking/candidates/{id}/rating endpoint."""

    @pytest.mark.asyncio
    async def test_set_rating_single_candidate(self, api_key_headers, test_candidates, db_session):
        """Setting rating updates candidate and returns JSON:API response."""
        candidate = test_candidates[0]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/fact-checking/candidates/{candidate.id}/rating",
                json={
                    "data": {
                        "type": "fact-check-candidates",
                        "attributes": {
                            "rating": "false",
                            "rating_details": "misleading_context",
                            "auto_promote": False,
                        },
                    }
                },
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["rating"] == "false"
        assert data["data"]["attributes"]["rating_details"] == "misleading_context"

    @pytest.mark.asyncio
    async def test_set_rating_not_found(self, api_key_headers):
        """Setting rating on nonexistent candidate returns 404."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/fact-checking/candidates/{uuid4()}/rating",
                json={
                    "data": {
                        "type": "fact-check-candidates",
                        "attributes": {"rating": "false"},
                    }
                },
                headers=api_key_headers,
            )

        assert response.status_code == 404


class TestBulkApproveJSONAPI:
    """Tests for POST /api/v1/fact-checking/candidates/approve-predicted endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_approve_from_predictions(
        self, api_key_headers, test_candidates, db_session
    ):
        """Bulk approve sets rating from high-confidence predictions."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/candidates/approve-predicted",
                json={
                    "threshold": 1.0,
                    "auto_promote": False,
                },
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["updated_count"] == 2
        assert data["meta"]["promoted_count"] is None

    @pytest.mark.asyncio
    async def test_bulk_approve_with_filters(self, api_key_headers, test_candidates, db_session):
        """Bulk approve respects filter parameters."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/candidates/approve-predicted",
                json={
                    "threshold": 1.0,
                    "auto_promote": False,
                    "dataset_name": "test_dataset",
                },
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["updated_count"] == 2

    @pytest.mark.asyncio
    async def test_bulk_approve_handles_int_predictions(self, api_key_headers, test_candidates):
        """Bulk approve handles integer prediction values (JSON deserializes 1 as int)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/candidates/approve-predicted",
                json={
                    "threshold": 1.0,
                    "auto_promote": False,
                },
                headers=api_key_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["updated_count"] >= 1
