"""Tests for JSON:API v2 hybrid-searches endpoints.

This module contains integration tests for the /api/v2/hybrid-searches endpoint
that follows the JSON:API 1.1 specification. These tests verify:
- POST /api/v2/hybrid-searches performs hybrid search (FTS + semantic)
- Proper JSON:API response envelope structure
- Correct content-type headers (application/vnd.api+json)
- Response includes rrf_score for ranking results

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def hybrid_search_jsonapi_community_server():
    """Create a test community server for hybrid search JSON:API tests."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = f"test_guild_hybrid_jsonapi_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_id=platform_id,
            name="Test Guild for Hybrid Search JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_id": platform_id}


@pytest.fixture
async def hybrid_search_jsonapi_test_user():
    """Create a unique test user for hybrid search JSON:API tests."""
    return {
        "username": f"hybrid_jsonapi_user_{uuid4().hex[:8]}",
        "email": f"hybrid_jsonapi_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Hybrid Search JSONAPI Test User",
    }


@pytest.fixture
async def hybrid_search_jsonapi_registered_user(
    hybrid_search_jsonapi_test_user, hybrid_search_jsonapi_community_server
):
    """Create a registered user with member role for hybrid search JSON:API tests."""
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=hybrid_search_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == hybrid_search_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"hybrid_jsonapi_discord_{uuid4().hex[:8]}"

            profile = UserProfile(
                display_name=user.full_name or user.username,
                is_human=True,
                is_active=True,
            )
            session.add(profile)
            await session.flush()

            identity = UserIdentity(
                profile_id=profile.id,
                provider="discord",
                provider_user_id=user.discord_id,
            )
            session.add(identity)

            member = CommunityMember(
                community_id=hybrid_search_jsonapi_community_server["uuid"],
                profile_id=profile.id,
                role="member",
                is_active=True,
                joined_at=datetime.now(UTC),
            )
            session.add(member)

            await session.commit()
            await session.refresh(user)
            await session.refresh(profile)

            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "discord_id": user.discord_id,
                "profile_id": profile.id,
            }


@pytest.fixture
async def hybrid_search_jsonapi_auth_headers(hybrid_search_jsonapi_registered_user):
    """Generate auth headers for hybrid search JSON:API test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(hybrid_search_jsonapi_registered_user["id"]),
        "username": hybrid_search_jsonapi_registered_user["username"],
        "role": hybrid_search_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def hybrid_search_jsonapi_auth_client(hybrid_search_jsonapi_auth_headers):
    """Auth client using hybrid search JSON:API test user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(hybrid_search_jsonapi_auth_headers)
        yield client


class TestHybridSearchJSONAPI:
    """Tests for POST /api/v2/hybrid-searches."""

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_response_structure(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns proper JSON:API structure.

        JSON:API 1.1 action endpoint requirements:
        - Response with 200 OK status (or error if service unavailable)
        - 'data' object containing result resource
        - Resource has 'type', 'id', and 'attributes'
        - Proper content-type header

        Note: This test verifies the endpoint exists and returns valid JSON:API format.
        The actual search may fail due to missing OpenAI configuration in tests.
        """
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "Is the earth flat?",
                    "community_server_id": platform_id,
                    "limit": 5,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Expected JSON:API content type, got: {content_type}"
        )

        data = response.json()

        if response.status_code == 200:
            assert "data" in data, "Success response must contain 'data' key"
            assert data["data"]["type"] == "hybrid-search-results", (
                f"Expected type 'hybrid-search-results', got: {data['data'].get('type')}"
            )
            assert "id" in data["data"], "Resource must have 'id'"
            assert "attributes" in data["data"], "Resource must have 'attributes'"
            assert "jsonapi" in data, "Response must contain 'jsonapi' key"
            assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

            attrs = data["data"]["attributes"]
            assert "matches" in attrs, "Attributes must contain 'matches'"
            assert "query_text" in attrs, "Attributes must contain 'query_text'"
            assert "total_matches" in attrs, "Attributes must contain 'total_matches'"
        else:
            assert "errors" in data, "Error response must contain 'errors' array"
            assert isinstance(data["errors"], list), "'errors' must be a list"

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_invalid_type(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches rejects invalid resource type."""
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "wrong-type",
                "attributes": {
                    "text": "Test query",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for invalid type, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_missing_text(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns 422 for missing text field."""
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "community_server_id": platform_id,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for missing text, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_missing_community_server_id(
        self,
        hybrid_search_jsonapi_auth_client,
    ):
        """Test POST /api/v2/hybrid-searches returns 422 for missing community_server_id."""
        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "Test query",
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for missing community_server_id, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_unknown_community_server(
        self,
        hybrid_search_jsonapi_auth_client,
    ):
        """Test POST /api/v2/hybrid-searches returns 404 for unknown community server."""
        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "Test query about fact checking",
                    "community_server_id": "nonexistent_guild_id_12345",
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code in [403, 404], (
            f"Expected 403 or 404 for unknown community server, got {response.status_code}"
        )

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_empty_text(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns 422 for empty text."""
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for empty text, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_query_too_short_single_char(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns 422 for single character query.

        Single character queries like "a" waste API credits and return poor results.
        The minimum query length should be 3 characters.
        """
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "a",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for single char query, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_query_too_short_two_chars(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns 422 for two character query.

        Two character queries like "ab" waste API credits and return poor results.
        The minimum query length should be 3 characters.
        """
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "ab",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for two char query, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_query_minimum_valid_length(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches accepts 3+ character queries.

        Three character queries like "abc" should pass validation.
        Note: The request may fail for other reasons (e.g., no OpenAI config),
        but should NOT fail with 422 for text length validation.
        """
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "abc",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        if response.status_code == 422:
            data = response.json()
            error_details = str(data.get("detail", ""))
            assert "at least 3" not in error_details.lower(), (
                f"3-character query should pass length validation, got: {error_details}"
            )

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_default_values(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches applies default values.

        Note: This test may result in an error if OpenAI is not configured,
        but it verifies the endpoint exists and accepts minimal valid input.
        """
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "Is climate change real?",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_invalid_limit(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches rejects invalid limit values."""
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "Test query",
                    "community_server_id": platform_id,
                    "limit": 100,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for invalid limit, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_invalid_limit_zero(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches rejects limit of 0."""
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "hybrid-searches",
                "attributes": {
                    "text": "Test query",
                    "community_server_id": platform_id,
                    "limit": 0,
                },
            }
        }

        response = await hybrid_search_jsonapi_auth_client.post(
            "/api/v2/hybrid-searches", json=request_body
        )

        assert response.status_code == 422, f"Expected 422 for limit=0, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_requires_auth(self):
        """Test POST /api/v2/hybrid-searches requires authentication."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = {
                "data": {
                    "type": "hybrid-searches",
                    "attributes": {
                        "text": "Test query",
                        "community_server_id": "some_guild_id",
                    },
                }
            }

            response = await client.post("/api/v2/hybrid-searches", json=request_body)

            assert response.status_code == 401, (
                f"Expected 401 without auth, got {response.status_code}"
            )


class TestHybridSearchJSONAPIWithMockedService:
    """Tests with mocked embedding service for full response verification."""

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_success_with_matches(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns matches with rrf_score when found.

        This test mocks the embedding service and repository to verify the complete
        response structure including matches with rrf_score field.
        """
        from dataclasses import dataclass
        from datetime import datetime
        from uuid import uuid4

        @dataclass
        class MockFactCheckItem:
            id: uuid4
            dataset_name: str
            dataset_tags: list[str]
            title: str
            content: str
            summary: str
            rating: str
            source_url: str
            published_date: datetime
            author: str

        @dataclass
        class MockHybridSearchResult:
            item: MockFactCheckItem
            rrf_score: float

        mock_item_1 = MockFactCheckItem(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["health", "science"],
            title="Is the COVID vaccine safe?",
            content="Extensive testing has shown COVID vaccines are safe and effective.",
            summary="COVID vaccines have undergone rigorous safety testing.",
            rating="True",
            source_url="https://snopes.com/fact-check/covid-vaccine-safe",
            published_date=datetime(2024, 1, 15, tzinfo=UTC),
            author="Dr. Smith",
        )

        mock_item_2 = MockFactCheckItem(
            id=uuid4(),
            dataset_name="politifact",
            dataset_tags=["health"],
            title="Vaccine effectiveness claim",
            content="Claims about vaccine effectiveness have been verified.",
            summary="Vaccine claims verified.",
            rating="Mostly True",
            source_url="https://politifact.com/vaccine-claim",
            published_date=datetime(2024, 2, 20, tzinfo=UTC),
            author="Jane Doe",
        )

        mock_results = [
            MockHybridSearchResult(item=mock_item_1, rrf_score=0.0325),
            MockHybridSearchResult(item=mock_item_2, rrf_score=0.0287),
        ]

        mock_embedding = [0.1] * 1536

        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        with (
            patch(
                "src.llm_config.usage_tracker.LLMUsageTracker.check_limits",
                new_callable=AsyncMock,
            ) as mock_check_limits,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
            ) as mock_generate,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.hybrid_search",
                new_callable=AsyncMock,
            ) as mock_search,
        ):
            mock_check_limits.return_value = (True, None)
            mock_generate.return_value = mock_embedding
            mock_search.return_value = mock_results

            request_body = {
                "data": {
                    "type": "hybrid-searches",
                    "attributes": {
                        "text": "Is the vaccine safe?",
                        "community_server_id": platform_id,
                        "limit": 10,
                    },
                }
            }

            response = await hybrid_search_jsonapi_auth_client.post(
                "/api/v2/hybrid-searches", json=request_body
            )

            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

            data = response.json()

            assert "data" in data
            assert data["data"]["type"] == "hybrid-search-results"
            assert "id" in data["data"]

            assert "jsonapi" in data
            assert data["jsonapi"]["version"] == "1.1"

            attrs = data["data"]["attributes"]
            assert attrs["query_text"] == "Is the vaccine safe?"
            assert attrs["total_matches"] == 2
            assert isinstance(attrs["matches"], list)
            assert len(attrs["matches"]) == 2

            match_1 = attrs["matches"][0]
            assert match_1["id"] == str(mock_item_1.id)
            assert match_1["dataset_name"] == "snopes"
            assert match_1["dataset_tags"] == ["health", "science"]
            assert match_1["title"] == "Is the COVID vaccine safe?"
            assert (
                match_1["content"]
                == "Extensive testing has shown COVID vaccines are safe and effective."
            )
            assert match_1["summary"] == "COVID vaccines have undergone rigorous safety testing."
            assert match_1["rating"] == "True"
            assert match_1["source_url"] == "https://snopes.com/fact-check/covid-vaccine-safe"
            assert match_1["author"] == "Dr. Smith"
            assert "rrf_score" in match_1
            assert match_1["rrf_score"] == pytest.approx(0.0325, rel=1e-4)
            assert match_1["rrf_score"] >= 0.0

            match_2 = attrs["matches"][1]
            assert match_2["id"] == str(mock_item_2.id)
            assert "rrf_score" in match_2
            assert match_2["rrf_score"] == pytest.approx(0.0287, rel=1e-4)

            content_type = response.headers.get("content-type", "")
            assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_empty_results(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns empty matches list when no results."""
        mock_embedding = [0.1] * 1536

        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        with (
            patch(
                "src.llm_config.usage_tracker.LLMUsageTracker.check_limits",
                new_callable=AsyncMock,
            ) as mock_check_limits,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
            ) as mock_generate,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.hybrid_search",
                new_callable=AsyncMock,
            ) as mock_search,
        ):
            mock_check_limits.return_value = (True, None)
            mock_generate.return_value = mock_embedding
            mock_search.return_value = []

            request_body = {
                "data": {
                    "type": "hybrid-searches",
                    "attributes": {
                        "text": "xyznonexistentterm123456",
                        "community_server_id": platform_id,
                        "limit": 10,
                    },
                }
            }

            response = await hybrid_search_jsonapi_auth_client.post(
                "/api/v2/hybrid-searches", json=request_body
            )

            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

            data = response.json()

            assert data["data"]["type"] == "hybrid-search-results"
            attrs = data["data"]["attributes"]
            assert attrs["total_matches"] == 0
            assert attrs["matches"] == []
            assert attrs["query_text"] == "xyznonexistentterm123456"

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_links_included(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches includes links in response."""
        mock_embedding = [0.1] * 1536

        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        with (
            patch(
                "src.llm_config.usage_tracker.LLMUsageTracker.check_limits",
                new_callable=AsyncMock,
            ) as mock_check_limits,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
            ) as mock_generate,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.hybrid_search",
                new_callable=AsyncMock,
            ) as mock_search,
        ):
            mock_check_limits.return_value = (True, None)
            mock_generate.return_value = mock_embedding
            mock_search.return_value = []

            request_body = {
                "data": {
                    "type": "hybrid-searches",
                    "attributes": {
                        "text": "test query",
                        "community_server_id": platform_id,
                    },
                }
            }

            response = await hybrid_search_jsonapi_auth_client.post(
                "/api/v2/hybrid-searches", json=request_body
            )

            assert response.status_code == 200

            data = response.json()
            assert "links" in data
            assert "self" in data["links"]
            assert "/api/v2/hybrid-searches" in data["links"]["self"]

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_rate_limit_exceeded(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns 429 when OpenAI rate limit exceeded."""
        import httpx
        from openai import RateLimitError

        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        mock_request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
        mock_response = httpx.Response(429, request=mock_request)

        with (
            patch(
                "src.llm_config.usage_tracker.LLMUsageTracker.check_limits",
                new_callable=AsyncMock,
            ) as mock_check_limits,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
            ) as mock_generate,
        ):
            mock_check_limits.return_value = (True, None)
            mock_generate.side_effect = RateLimitError(
                message="Rate limit exceeded",
                response=mock_response,
                body=None,
            )

            request_body = {
                "data": {
                    "type": "hybrid-searches",
                    "attributes": {
                        "text": "test query",
                        "community_server_id": platform_id,
                    },
                }
            }

            response = await hybrid_search_jsonapi_auth_client.post(
                "/api/v2/hybrid-searches", json=request_body
            )

            assert response.status_code == 429

            data = response.json()
            assert "errors" in data
            assert len(data["errors"]) > 0
            assert data["errors"][0]["status"] == "429"
            assert "Rate Limit" in data["errors"][0]["title"]

            content_type = response.headers.get("content-type", "")
            assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_community_rate_limit_exceeded(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
    ):
        """Test POST /api/v2/hybrid-searches returns 429 when community rate limit exceeded."""
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        with patch(
            "src.llm_config.usage_tracker.LLMUsageTracker.check_limits",
            new_callable=AsyncMock,
        ) as mock_check_limits:
            mock_check_limits.return_value = (False, "Monthly usage limit exceeded")

            request_body = {
                "data": {
                    "type": "hybrid-searches",
                    "attributes": {
                        "text": "test query",
                        "community_server_id": platform_id,
                    },
                }
            }

            response = await hybrid_search_jsonapi_auth_client.post(
                "/api/v2/hybrid-searches", json=request_body
            )

            assert response.status_code == 429

            data = response.json()
            assert "errors" in data
            assert len(data["errors"]) > 0
            assert data["errors"][0]["status"] == "429"
            assert "Rate Limit Exceeded" in data["errors"][0]["title"]
            assert "Monthly usage limit exceeded" in data["errors"][0]["detail"]

            content_type = response.headers.get("content-type", "")
            assert "application/vnd.api+json" in content_type


class TestHybridSearchJSONAPIPerformanceMetrics:
    """Tests for performance monitoring metrics in hybrid search JSON:API endpoint."""

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_logs_timing_metrics(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
        caplog,
    ):
        """Test POST /api/v2/hybrid-searches logs timing metrics for monitoring.

        The endpoint should log total_duration_ms, embedding_duration_ms, and
        search_duration_ms to help identify performance bottlenecks.
        """
        import logging

        mock_embedding = [0.1] * 1536
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        with (
            patch(
                "src.llm_config.usage_tracker.LLMUsageTracker.check_limits",
                new_callable=AsyncMock,
            ) as mock_check_limits,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
            ) as mock_generate,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.hybrid_search",
                new_callable=AsyncMock,
            ) as mock_search,
            caplog.at_level(
                logging.INFO, logger="src.fact_checking.hybrid_searches_jsonapi_router"
            ),
        ):
            mock_check_limits.return_value = (True, None)
            mock_generate.return_value = mock_embedding
            mock_search.return_value = []

            request_body = {
                "data": {
                    "type": "hybrid-searches",
                    "attributes": {
                        "text": "test timing query",
                        "community_server_id": platform_id,
                        "limit": 5,
                    },
                }
            }

            response = await hybrid_search_jsonapi_auth_client.post(
                "/api/v2/hybrid-searches", json=request_body
            )

            assert response.status_code == 200

        found_total = False
        found_embedding = False
        found_search = False

        for record in caplog.records:
            if hasattr(record, "total_duration_ms"):
                found_total = True
                assert isinstance(record.total_duration_ms, (int, float))
                assert record.total_duration_ms >= 0
            if hasattr(record, "embedding_duration_ms"):
                found_embedding = True
                assert isinstance(record.embedding_duration_ms, (int, float))
                assert record.embedding_duration_ms >= 0
            if hasattr(record, "search_duration_ms"):
                found_search = True
                assert isinstance(record.search_duration_ms, (int, float))
                assert record.search_duration_ms >= 0

        assert found_total, "Should log total_duration_ms"
        assert found_embedding, "Should log embedding_duration_ms"
        assert found_search, "Should log search_duration_ms"

    @pytest.mark.asyncio
    async def test_hybrid_search_jsonapi_timing_metrics_are_reasonable(
        self,
        hybrid_search_jsonapi_auth_client,
        hybrid_search_jsonapi_community_server,
        caplog,
    ):
        """Test that timing metrics are within reasonable bounds.

        All timing metrics should be positive and less than 30 seconds
        for normal operations. The breakdown should sum approximately to total.
        """
        import logging

        mock_embedding = [0.1] * 1536
        platform_id = hybrid_search_jsonapi_community_server["platform_id"]

        with (
            patch(
                "src.llm_config.usage_tracker.LLMUsageTracker.check_limits",
                new_callable=AsyncMock,
            ) as mock_check_limits,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.EmbeddingService.generate_embedding",
                new_callable=AsyncMock,
            ) as mock_generate,
            patch(
                "src.fact_checking.hybrid_searches_jsonapi_router.hybrid_search",
                new_callable=AsyncMock,
            ) as mock_search,
            caplog.at_level(
                logging.INFO, logger="src.fact_checking.hybrid_searches_jsonapi_router"
            ),
        ):
            mock_check_limits.return_value = (True, None)
            mock_generate.return_value = mock_embedding
            mock_search.return_value = []

            request_body = {
                "data": {
                    "type": "hybrid-searches",
                    "attributes": {
                        "text": "test timing validation",
                        "community_server_id": platform_id,
                    },
                }
            }

            await hybrid_search_jsonapi_auth_client.post(
                "/api/v2/hybrid-searches", json=request_body
            )

        for record in caplog.records:
            if "Hybrid search completed successfully" in record.message:
                total = getattr(record, "total_duration_ms", None)
                embedding = getattr(record, "embedding_duration_ms", None)
                search = getattr(record, "search_duration_ms", None)

                if total is not None:
                    assert 0 <= total < 30000, f"Total duration should be < 30s: {total}"

                if embedding is not None:
                    assert 0 <= embedding < 30000, (
                        f"Embedding duration should be < 30s: {embedding}"
                    )

                if search is not None:
                    assert 0 <= search < 30000, f"Search duration should be < 30s: {search}"
