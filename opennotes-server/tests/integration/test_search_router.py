"""Integration tests for the hybrid search API endpoint.

Tests the /api/v1/fact-check/search endpoint which combines:
- Full-text search (PostgreSQL FTS)
- Semantic search (pgvector embeddings)
using Reciprocal Rank Fusion (RRF) for optimal relevance ranking.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

import src.database
from src.fact_checking.models import FactCheckItem
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.main import app
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

pytestmark = pytest.mark.asyncio


def generate_test_embedding(seed: int = 0) -> list[float]:
    """Generate a deterministic test embedding vector (1536 dimensions)."""
    import math

    base = [math.sin(i * 0.01 + seed * 0.1) for i in range(1536)]
    norm = math.sqrt(sum(x * x for x in base))
    return [x / norm for x in base]


@pytest.fixture
async def search_test_community_server():
    """Create a test community server with OpenAI configuration."""
    async with src.database.async_session_maker() as session:
        community = CommunityServer(
            platform="discord",
            platform_id=f"search_test_{uuid4().hex[:8]}",
            name="Search Test Community",
            is_active=True,
        )
        session.add(community)
        await session.flush()

        llm_config = CommunityServerLLMConfig(
            community_server_id=community.id,
            provider="openai",
            api_key_encrypted=b"test_encrypted_key",
            encryption_key_id="test_key_v1",
            api_key_preview="...test",
            enabled=True,
            settings={"model": "text-embedding-3-small"},
        )
        session.add(llm_config)

        await session.commit()
        await session.refresh(community)

        yield community

        await session.delete(community)
        await session.commit()


@pytest.fixture
async def search_test_user_with_profile():
    """Create a test user with profile and identity."""
    async with src.database.async_session_maker() as session:
        profile = UserProfile(
            display_name="Search Test User",
            is_active=True,
            is_banned=False,
        )
        session.add(profile)
        await session.flush()

        user = User(
            username=f"searchtestuser_{uuid4().hex[:8]}",
            email=f"searchtest_{uuid4().hex[:8]}@example.com",
            hashed_password="hashed",
            discord_id=str(uuid4()),
            is_active=True,
        )
        session.add(user)
        await session.flush()

        identity = UserIdentity(
            profile_id=profile.id,
            provider="discord",
            provider_user_id=user.discord_id,
        )
        session.add(identity)

        await session.commit()
        await session.refresh(profile)
        await session.refresh(user)

        yield {"user": user, "profile": profile}

        await session.delete(user)
        await session.delete(profile)
        await session.commit()


@pytest.fixture
async def search_authorized_member(search_test_user_with_profile, search_test_community_server):
    """Create an active community membership."""
    async with src.database.async_session_maker() as session:
        membership = CommunityMember(
            community_id=search_test_community_server.id,
            profile_id=search_test_user_with_profile["profile"].id,
            role="member",
            is_active=True,
            joined_at=datetime.now(UTC),
        )
        session.add(membership)
        await session.commit()
        await session.refresh(membership)

        yield membership

        await session.delete(membership)
        await session.commit()


@pytest.fixture
async def search_auth_headers(search_test_user_with_profile):
    """Generate auth headers for test user."""
    from src.auth.auth import create_access_token

    user = search_test_user_with_profile["user"]
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def search_test_items():
    """Create test FactCheckItem records with embeddings."""
    item_ids = []

    async with src.database.async_session_maker() as session:
        item1 = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "search-router"],
            title="Did the moon landing really happen?",
            content="NASA landed astronauts on the moon in 1969.",
            summary="Moon landing verification",
            rating="True",
            embedding=generate_test_embedding(seed=1),
        )
        session.add(item1)

        item2 = FactCheckItem(
            dataset_name="test",
            dataset_tags=["test", "search-router"],
            title="Climate change fact check",
            content="Scientific consensus on global warming.",
            summary="Climate fact check",
            rating="True",
            embedding=generate_test_embedding(seed=2),
        )
        session.add(item2)

        await session.commit()
        await session.refresh(item1)
        await session.refresh(item2)

        item_ids = [item1.id, item2.id]

        yield {"moon": item1, "climate": item2}

    async with src.database.async_session_maker() as session:
        from sqlalchemy import select

        for item_id in item_ids:
            result = await session.execute(
                select(FactCheckItem).where(FactCheckItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            if item:
                await session.delete(item)
        await session.commit()


class TestSearchEndpointValidation:
    """Tests for request validation on the search endpoint."""

    async def test_search_endpoint_rejects_empty_query(
        self, search_auth_headers, search_test_community_server, search_authorized_member
    ):
        """Test that empty query strings are rejected with 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(search_auth_headers)

            response = await client.post(
                f"/api/v1/fact-check/search?community_server_id={search_test_community_server.platform_id}",
                json={"query": ""},
            )

            assert response.status_code == 422, "Empty query should return validation error"

    async def test_search_endpoint_rejects_invalid_limit(
        self, search_auth_headers, search_test_community_server, search_authorized_member
    ):
        """Test that invalid limit values are rejected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(search_auth_headers)

            response = await client.post(
                f"/api/v1/fact-check/search?community_server_id={search_test_community_server.platform_id}",
                json={"query": "test query", "limit": 0},
            )

            assert response.status_code == 422, "Limit of 0 should be rejected"

            response = await client.post(
                f"/api/v1/fact-check/search?community_server_id={search_test_community_server.platform_id}",
                json={"query": "test query", "limit": 101},
            )

            assert response.status_code == 422, "Limit > 100 should be rejected"


class TestSearchEndpointAuthentication:
    """Tests for authentication requirements on the search endpoint."""

    async def test_search_endpoint_requires_authentication(self):
        """Test that unauthenticated requests are rejected."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-check/search?community_server_id=test123",
                json={"query": "test query"},
            )

            assert response.status_code == 401, "Unauthenticated request should be rejected"


class TestSearchEndpointWithMockedEmbedding:
    """Tests for search endpoint with mocked embedding service."""

    async def test_search_endpoint_returns_results(
        self,
        search_auth_headers,
        search_test_community_server,
        search_authorized_member,
        search_test_items,
    ):
        """Test that search endpoint returns properly structured results."""
        mock_embedding = generate_test_embedding(seed=1)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(search_auth_headers)

            with patch(
                "src.fact_checking.search_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
                return_value=mock_embedding,
            ):
                response = await client.post(
                    f"/api/v1/fact-check/search?community_server_id={search_test_community_server.platform_id}",
                    json={"query": "moon landing"},
                )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

            data = response.json()
            assert "results" in data, "Response should have results field"
            assert "query" in data, "Response should have query field"
            assert "total" in data, "Response should have total field"
            assert data["query"] == "moon landing", "Query should be echoed back"

    async def test_search_endpoint_respects_limit(
        self,
        search_auth_headers,
        search_test_community_server,
        search_authorized_member,
        search_test_items,
    ):
        """Test that search endpoint respects the limit parameter."""
        mock_embedding = generate_test_embedding(seed=1)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(search_auth_headers)

            with patch(
                "src.fact_checking.search_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
                return_value=mock_embedding,
            ):
                response = await client.post(
                    f"/api/v1/fact-check/search?community_server_id={search_test_community_server.platform_id}",
                    json={"query": "fact check", "limit": 1},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) <= 1, "Should respect limit parameter"

    async def test_search_result_structure(
        self,
        search_auth_headers,
        search_test_community_server,
        search_authorized_member,
        search_test_items,
    ):
        """Test that search results have all expected fields."""
        mock_embedding = generate_test_embedding(seed=1)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(search_auth_headers)

            with patch(
                "src.fact_checking.search_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
                return_value=mock_embedding,
            ):
                response = await client.post(
                    f"/api/v1/fact-check/search?community_server_id={search_test_community_server.platform_id}",
                    json={"query": "moon"},
                )

            assert response.status_code == 200
            data = response.json()

            if len(data["results"]) > 0:
                result = data["results"][0]
                assert "id" in result, "Result should have id"
                assert "title" in result, "Result should have title"
                assert "content" in result, "Result should have content"
                assert "dataset_name" in result, "Result should have dataset_name"
                assert "dataset_tags" in result, "Result should have dataset_tags"
                assert "rating" in result, "Result should have rating"


class TestSearchSchemas:
    """Tests for search request/response Pydantic schemas."""

    def test_hybrid_search_request_validation(self):
        """Test HybridSearchRequest schema validation."""
        from src.fact_checking.search_schemas import HybridSearchRequest

        valid_request = HybridSearchRequest(query="test query")
        assert valid_request.query == "test query"
        assert valid_request.limit == 10

        valid_with_limit = HybridSearchRequest(query="test", limit=50)
        assert valid_with_limit.limit == 50

        with pytest.raises(ValueError, match="String should have at least 1 character"):
            HybridSearchRequest(query="")

        with pytest.raises(ValueError, match="Input should be greater than or equal to 1"):
            HybridSearchRequest(query="test", limit=0)

        with pytest.raises(ValueError, match="Input should be less than or equal to 100"):
            HybridSearchRequest(query="test", limit=101)

    def test_hybrid_search_response_structure(self):
        """Test HybridSearchResponse schema structure."""
        from uuid import uuid4

        from src.fact_checking.search_schemas import (
            FactCheckSearchResult,
            HybridSearchResponse,
        )

        result = FactCheckSearchResult(
            id=uuid4(),
            title="Test Title",
            content="Test content",
            summary=None,
            source_url=None,
            rating="True",
            dataset_name="test",
            dataset_tags=["test"],
            published_date=None,
            author=None,
        )

        response = HybridSearchResponse(
            results=[result],
            query="test query",
            total=1,
        )

        assert len(response.results) == 1
        assert response.query == "test query"
        assert response.total == 1
