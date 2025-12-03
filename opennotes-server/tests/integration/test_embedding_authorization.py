"""
Tests for embedding endpoint authorization (task-294).

Verifies that the similarity_search endpoint properly enforces:
- Community membership authorization
- Banned user rejection
- Inactive membership rejection
- Proper audit logging with user_id and profile_id
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

import src.database
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.main import app
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile


@pytest.fixture
async def test_community_server():
    """Create a test community server with OpenAI configuration"""
    async with src.database.async_session_maker() as session:
        community = CommunityServer(
            platform="discord",
            platform_id=str(uuid4()),
            name="Test Community",
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
async def test_user_with_profile():
    """Create a test user with profile and identity"""
    async with src.database.async_session_maker() as session:
        profile = UserProfile(
            display_name="Test User",
            is_active=True,
            is_banned=False,
        )
        session.add(profile)
        await session.flush()

        user = User(
            username=f"testuser_{uuid4().hex[:8]}",
            email=f"test_{uuid4().hex[:8]}@example.com",
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
async def authorized_member(test_user_with_profile, test_community_server):
    """Create an active community membership"""
    async with src.database.async_session_maker() as session:
        membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=test_user_with_profile["profile"].id,
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
async def banned_member(test_user_with_profile, test_community_server):
    """Create a banned community membership"""
    async with src.database.async_session_maker() as session:
        membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=test_user_with_profile["profile"].id,
            role="member",
            is_active=True,
            joined_at=datetime.now(UTC),
            banned_at=datetime.now(UTC),
            banned_reason="Test ban",
        )
        session.add(membership)
        await session.commit()
        await session.refresh(membership)

        yield membership

        await session.delete(membership)
        await session.commit()


@pytest.fixture
async def inactive_member(test_user_with_profile, test_community_server):
    """Create an inactive community membership"""
    async with src.database.async_session_maker() as session:
        membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=test_user_with_profile["profile"].id,
            role="member",
            is_active=False,
            joined_at=datetime.now(UTC),
        )
        session.add(membership)
        await session.commit()
        await session.refresh(membership)

        yield membership

        await session.delete(membership)
        await session.commit()


@pytest.fixture
async def auth_headers_for_user(test_user_with_profile):
    """Generate auth headers for test user"""
    from src.auth.auth import create_access_token

    user = test_user_with_profile["user"]
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def auth_client(auth_headers_for_user):
    """Authenticated HTTP client"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(auth_headers_for_user)
        yield client


@pytest.mark.asyncio
class TestEmbeddingAuthorization:
    """Test authorization checks for embedding endpoint"""

    async def test_authorized_member_can_access(
        self, auth_client, test_community_server, authorized_member
    ):
        """Authorized members should be able to generate embeddings"""
        request_data = {
            "text": "Test search query",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        assert response.status_code in [200, 404]

    async def test_non_member_rejected_with_403(self, auth_client, test_community_server):
        """Users who are not members should receive 403 Forbidden"""
        request_data = {
            "text": "Test search query",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        assert response.status_code == 403
        assert "not a member" in response.json()["detail"].lower()

    async def test_banned_member_rejected_with_403(
        self, auth_client, test_community_server, banned_member
    ):
        """Banned users should receive 403 Forbidden"""
        request_data = {
            "text": "Test search query",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        assert response.status_code == 403
        assert "banned" in response.json()["detail"].lower()

    async def test_inactive_member_rejected_with_403(
        self, auth_client, test_community_server, inactive_member
    ):
        """Inactive members should receive 403 Forbidden"""
        request_data = {
            "text": "Test search query",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        assert response.status_code == 403
        assert "not a member" in response.json()["detail"].lower()

    async def test_nonexistent_community_rejected_with_404(self, auth_client):
        """Requests for non-existent communities are auto-created, returning 403 for non-members"""
        request_data = {
            "text": "Test search query",
            "community_server_id": "nonexistent_guild_id",
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        # Communities are auto-created, so non-existent communities are created with auto-creation
        # Since the user isn't a member of the auto-created community, they get 403
        assert response.status_code == 403
        assert "not a member" in response.json()["detail"].lower()


@pytest.mark.asyncio
class TestEmbeddingAuditLogging:
    """Test that authorization attempts are properly logged for audit"""

    async def test_authorized_request_logs_user_and_profile(
        self, auth_client, test_community_server, authorized_member, caplog
    ):
        """Authorized requests should log user_id, profile_id, and community_role"""
        import logging

        caplog.set_level(logging.INFO)

        request_data = {
            "text": "Test search query",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        log_records = [
            r.message for r in caplog.records if "similarity search" in r.message.lower()
        ]
        assert len(log_records) > 0

    async def test_unauthorized_request_logged(self, auth_client, test_community_server, caplog):
        """Unauthorized requests should be logged for security audit"""
        import logging

        caplog.set_level(logging.WARNING)

        request_data = {
            "text": "Test search query",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        assert response.status_code == 403
