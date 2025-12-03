"""Tests for JSON:API v2 similarity-searches endpoints.

This module contains integration tests for the /api/v2/similarity-searches endpoint
that follows the JSON:API 1.1 specification. These tests verify:
- POST /api/v2/similarity-searches performs semantic similarity search
- Proper JSON:API response envelope structure
- Correct content-type headers (application/vnd.api+json)

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def embeddings_jsonapi_community_server():
    """Create a test community server for embeddings JSON:API tests."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = f"test_guild_embeddings_jsonapi_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_id=platform_id,
            name="Test Guild for Embeddings JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_id": platform_id}


@pytest.fixture
async def embeddings_jsonapi_test_user():
    """Create a unique test user for embeddings JSON:API tests."""
    return {
        "username": f"embeddings_jsonapi_user_{uuid4().hex[:8]}",
        "email": f"embeddings_jsonapi_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Embeddings JSONAPI Test User",
    }


@pytest.fixture
async def embeddings_jsonapi_registered_user(
    embeddings_jsonapi_test_user, embeddings_jsonapi_community_server
):
    """Create a registered user with member role for embeddings JSON:API tests."""
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=embeddings_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == embeddings_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"embeddings_jsonapi_discord_{uuid4().hex[:8]}"

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
                community_id=embeddings_jsonapi_community_server["uuid"],
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
async def embeddings_jsonapi_auth_headers(embeddings_jsonapi_registered_user):
    """Generate auth headers for embeddings JSON:API test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(embeddings_jsonapi_registered_user["id"]),
        "username": embeddings_jsonapi_registered_user["username"],
        "role": embeddings_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def embeddings_jsonapi_auth_client(embeddings_jsonapi_auth_headers):
    """Auth client using embeddings JSON:API test user."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(embeddings_jsonapi_auth_headers)
        yield client


class TestSimilaritySearchJSONAPI:
    """Tests for POST /api/v2/similarity-searches."""

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_response_structure(
        self,
        embeddings_jsonapi_auth_client,
        embeddings_jsonapi_community_server,
    ):
        """Test POST /api/v2/similarity-searches returns proper JSON:API structure.

        JSON:API 1.1 action endpoint requirements:
        - Response with 200 OK status (or error if service unavailable)
        - 'data' object containing result resource
        - Resource has 'type', 'id', and 'attributes'
        - Proper content-type header

        Note: This test verifies the endpoint exists and returns valid JSON:API format.
        The actual search may fail due to missing OpenAI configuration in tests.
        """
        platform_id = embeddings_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "text": "Is the earth flat?",
                    "community_server_id": platform_id,
                    "dataset_tags": ["snopes"],
                    "similarity_threshold": 0.5,
                    "limit": 5,
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Expected JSON:API content type, got: {content_type}"
        )

        data = response.json()

        if response.status_code == 200:
            assert "data" in data, "Success response must contain 'data' key"
            assert data["data"]["type"] == "similarity-search-results", (
                f"Expected type 'similarity-search-results', got: {data['data'].get('type')}"
            )
            assert "id" in data["data"], "Resource must have 'id'"
            assert "attributes" in data["data"], "Resource must have 'attributes'"
            assert "jsonapi" in data, "Response must contain 'jsonapi' key"
            assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

            attrs = data["data"]["attributes"]
            assert "matches" in attrs, "Attributes must contain 'matches'"
            assert "query_text" in attrs, "Attributes must contain 'query_text'"
            assert "dataset_tags" in attrs, "Attributes must contain 'dataset_tags'"
            assert "similarity_threshold" in attrs, "Attributes must contain 'similarity_threshold'"
            assert "total_matches" in attrs, "Attributes must contain 'total_matches'"
        else:
            assert "errors" in data, "Error response must contain 'errors' array"
            assert isinstance(data["errors"], list), "'errors' must be a list"

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_invalid_type(
        self,
        embeddings_jsonapi_auth_client,
        embeddings_jsonapi_community_server,
    ):
        """Test POST /api/v2/similarity-searches rejects invalid resource type."""
        platform_id = embeddings_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "wrong-type",
                "attributes": {
                    "text": "Test query",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for invalid type, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_missing_text(
        self,
        embeddings_jsonapi_auth_client,
        embeddings_jsonapi_community_server,
    ):
        """Test POST /api/v2/similarity-searches returns 422 for missing text field."""
        platform_id = embeddings_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "community_server_id": platform_id,
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for missing text, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_missing_community_server_id(
        self,
        embeddings_jsonapi_auth_client,
    ):
        """Test POST /api/v2/similarity-searches returns 422 for missing community_server_id."""
        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "text": "Test query",
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for missing community_server_id, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_unknown_community_server(
        self,
        embeddings_jsonapi_auth_client,
    ):
        """Test POST /api/v2/similarity-searches returns 404 for unknown community server."""
        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "text": "Test query about fact checking",
                    "community_server_id": "nonexistent_guild_id_12345",
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        assert response.status_code in [403, 404], (
            f"Expected 403 or 404 for unknown community server, got {response.status_code}"
        )

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_empty_text(
        self,
        embeddings_jsonapi_auth_client,
        embeddings_jsonapi_community_server,
    ):
        """Test POST /api/v2/similarity-searches returns 422 for empty text."""
        platform_id = embeddings_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "text": "",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for empty text, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_default_values(
        self,
        embeddings_jsonapi_auth_client,
        embeddings_jsonapi_community_server,
    ):
        """Test POST /api/v2/similarity-searches applies default values.

        Note: This test may result in an error if OpenAI is not configured,
        but it verifies the endpoint exists and accepts minimal valid input.
        """
        platform_id = embeddings_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "text": "Is climate change real?",
                    "community_server_id": platform_id,
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_invalid_threshold(
        self,
        embeddings_jsonapi_auth_client,
        embeddings_jsonapi_community_server,
    ):
        """Test POST /api/v2/similarity-searches rejects invalid threshold values."""
        platform_id = embeddings_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "text": "Test query",
                    "community_server_id": platform_id,
                    "similarity_threshold": 1.5,
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for invalid threshold, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_invalid_limit(
        self,
        embeddings_jsonapi_auth_client,
        embeddings_jsonapi_community_server,
    ):
        """Test POST /api/v2/similarity-searches rejects invalid limit values."""
        platform_id = embeddings_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "text": "Test query",
                    "community_server_id": platform_id,
                    "limit": 100,
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        assert response.status_code == 422, (
            f"Expected 422 for invalid limit, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_similarity_search_jsonapi_requires_auth(self):
        """Test POST /api/v2/similarity-searches requires authentication."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = {
                "data": {
                    "type": "similarity-searches",
                    "attributes": {
                        "text": "Test query",
                        "community_server_id": "some_guild_id",
                    },
                }
            }

            response = await client.post("/api/v2/similarity-searches", json=request_body)

            assert response.status_code == 401, (
                f"Expected 401 without auth, got {response.status_code}"
            )


class TestSimilaritySearchJSONAPIWithMockedService:
    """Tests with mocked embedding service for full response verification."""

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Full similarity search requires OpenAI configuration. "
        "Testing complete flow requires LLM config setup which is done in integration tests."
    )
    async def test_similarity_search_jsonapi_with_matches(
        self,
        embeddings_jsonapi_auth_client,
        embeddings_jsonapi_community_server,
    ):
        """Test POST /api/v2/similarity-searches returns matches when found.

        Note: Requires LLM config for embedding generation.
        This would be fully tested in integration tests with mocked OpenAI.
        """
        platform_id = embeddings_jsonapi_community_server["platform_id"]

        request_body = {
            "data": {
                "type": "similarity-searches",
                "attributes": {
                    "text": "Is the vaccine safe?",
                    "community_server_id": platform_id,
                    "dataset_tags": ["snopes", "politifact"],
                    "similarity_threshold": 0.7,
                    "limit": 10,
                },
            }
        }

        response = await embeddings_jsonapi_auth_client.post(
            "/api/v2/similarity-searches", json=request_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "similarity-search-results"

        attrs = data["data"]["attributes"]
        assert attrs["query_text"] == "Is the vaccine safe?"
        assert attrs["dataset_tags"] == ["snopes", "politifact"]
        assert attrs["similarity_threshold"] == 0.7
        assert isinstance(attrs["matches"], list)
        assert isinstance(attrs["total_matches"], int)

        for match in attrs["matches"]:
            assert "id" in match
            assert "dataset_name" in match
            assert "title" in match
            assert "content" in match
            assert "similarity_score" in match
            assert 0.0 <= match["similarity_score"] <= 1.0
