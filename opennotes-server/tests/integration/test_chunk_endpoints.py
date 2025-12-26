"""
Integration tests for chunk re-embedding API endpoints.

These tests verify that:
1. POST /chunks/fact-check/rechunk requires authentication (401 without, success with)
2. POST /chunks/previously-seen/rechunk requires authentication (401 without, success with)
3. Endpoints accept community_server_id and batch_size parameters
4. Background task processing is triggered for large datasets
5. Service accounts can access the endpoints

Task: task-871.04 - Create API endpoints for bulk re-chunking operations
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.main import app


class TestChunkEndpointsFixtures:
    """Fixtures for chunk endpoint testing scenarios."""

    @pytest.fixture
    async def service_account_user(self, db):
        """Create a service account user for testing."""
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="chunk-service-account",
            email="chunk-service@opennotes.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            is_service_account=True,
            discord_id="discord_chunk_service",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return {"user": user}

    @pytest.fixture
    async def regular_user(self, db):
        """Create a regular user (not a service account)."""
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="regular_chunk_user",
            email="regular_chunk@example.com",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            is_service_account=False,
            discord_id="discord_regular_chunk",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return {"user": user}

    @pytest.fixture
    async def community_server_with_data(self, db):
        """Create a community server with fact check items and previously seen messages."""
        from src.fact_checking.models import FactCheckItem
        from src.fact_checking.previously_seen_models import PreviouslySeenMessage
        from src.llm_config.models import CommunityServer
        from src.notes.models import Note
        from src.users.models import User
        from src.users.profile_crud import create_profile_with_identity
        from src.users.profile_schemas import AuthProvider, UserProfileCreate

        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_id=f"test-server-{uuid4().hex[:8]}",
            name="Test Server for Chunking",
            is_active=True,
        )
        db.add(server)
        await db.flush()

        fact_check_items = []
        for i in range(3):
            fact_check = FactCheckItem(
                id=uuid4(),
                dataset_name="test-dataset",
                dataset_tags=["test", "chunking"],
                title=f"Test Fact Check {i}",
                content=f"This is the content for fact check item {i}. It has enough text to be chunked.",
            )
            db.add(fact_check)
            fact_check_items.append(fact_check)

        await db.flush()

        test_user = User(
            id=uuid4(),
            username=f"test_user_{uuid4().hex[:8]}",
            email=f"test_{uuid4().hex[:8]}@example.com",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            discord_id=f"discord_test_{uuid4().hex[:8]}",
        )
        db.add(test_user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="Test Profile",
            avatar_url=None,
            bio=None,
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )
        profile, _identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id=test_user.discord_id,
            credentials=None,
        )
        await db.flush()

        test_note = Note(
            author_participant_id="test_participant",
            author_profile_id=profile.id,
            community_server_id=server.id,
            summary="Test note summary",
            classification="NOT_MISLEADING",
        )
        db.add(test_note)
        await db.flush()

        previously_seen_messages = []
        for _ in range(2):
            prev_seen = PreviouslySeenMessage(
                community_server_id=server.id,
                original_message_id=f"msg_{uuid4().hex[:16]}",
                published_note_id=test_note.id,
            )
            db.add(prev_seen)
            previously_seen_messages.append(prev_seen)

        await db.commit()

        for item in fact_check_items:
            await db.refresh(item)
        for item in previously_seen_messages:
            await db.refresh(item)
        await db.refresh(server)

        return {
            "server": server,
            "fact_check_items": fact_check_items,
            "previously_seen_messages": previously_seen_messages,
        }

    def _create_auth_headers(self, user_data):
        """Create auth headers for a user."""
        user = user_data["user"]
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(token_data)
        return {"Authorization": f"Bearer {access_token}"}

    @pytest.fixture
    def service_account_headers(self, service_account_user):
        """Auth headers for service account."""
        return self._create_auth_headers(service_account_user)

    @pytest.fixture
    def regular_user_headers(self, regular_user):
        """Auth headers for regular user."""
        return self._create_auth_headers(regular_user)


class TestFactCheckRechunkEndpoint(TestChunkEndpointsFixtures):
    """Tests for POST /api/v1/chunks/fact-check/rechunk endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(
        self,
        community_server_with_data,
    ):
        """Request without auth token returns 401."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}"
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    @patch(
        "src.fact_checking.chunk_router.process_fact_check_rechunk_batch", new_callable=AsyncMock
    )
    async def test_service_account_can_initiate_rechunk(
        self,
        mock_rechunk_batch,
        service_account_headers,
        community_server_with_data,
    ):
        """Service account can initiate fact check rechunking."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"
            assert "total_items" in data

    @pytest.mark.asyncio
    @patch(
        "src.fact_checking.chunk_router.process_fact_check_rechunk_batch", new_callable=AsyncMock
    )
    async def test_regular_user_can_initiate_rechunk(
        self,
        mock_rechunk_batch,
        regular_user_headers,
        community_server_with_data,
    ):
        """Regular authenticated user can initiate fact check rechunking."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}",
                headers=regular_user_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"

    @pytest.mark.asyncio
    @patch(
        "src.fact_checking.chunk_router.process_fact_check_rechunk_batch", new_callable=AsyncMock
    )
    async def test_batch_size_parameter_accepted(
        self,
        mock_rechunk_batch,
        service_account_headers,
        community_server_with_data,
    ):
        """Endpoint accepts custom batch_size parameter."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}&batch_size=50",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"

    @pytest.mark.asyncio
    async def test_invalid_batch_size_rejected(
        self,
        service_account_headers,
        community_server_with_data,
    ):
        """Endpoint rejects invalid batch_size values."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}&batch_size=0",
                headers=service_account_headers,
            )

            assert response.status_code == 422

            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}&batch_size=2000",
                headers=service_account_headers,
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_community_server_id_required(
        self,
        service_account_headers,
    ):
        """Endpoint requires community_server_id parameter."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chunks/fact-check/rechunk",
                headers=service_account_headers,
            )

            assert response.status_code == 422


class TestPreviouslySeenRechunkEndpoint(TestChunkEndpointsFixtures):
    """Tests for POST /api/v1/chunks/previously-seen/rechunk endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(
        self,
        community_server_with_data,
    ):
        """Request without auth token returns 401."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}"
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    @patch(
        "src.fact_checking.chunk_router.process_previously_seen_rechunk_batch",
        new_callable=AsyncMock,
    )
    async def test_service_account_can_initiate_rechunk(
        self,
        mock_rechunk_batch,
        service_account_headers,
        community_server_with_data,
    ):
        """Service account can initiate previously seen message rechunking."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"
            assert "total_items" in data

    @pytest.mark.asyncio
    @patch(
        "src.fact_checking.chunk_router.process_previously_seen_rechunk_batch",
        new_callable=AsyncMock,
    )
    async def test_regular_user_can_initiate_rechunk(
        self,
        mock_rechunk_batch,
        regular_user_headers,
        community_server_with_data,
    ):
        """Regular authenticated user can initiate previously seen message rechunking."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}",
                headers=regular_user_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"

    @pytest.mark.asyncio
    @patch(
        "src.fact_checking.chunk_router.process_previously_seen_rechunk_batch",
        new_callable=AsyncMock,
    )
    async def test_batch_size_parameter_accepted(
        self,
        mock_rechunk_batch,
        service_account_headers,
        community_server_with_data,
    ):
        """Endpoint accepts custom batch_size parameter."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}&batch_size=75",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"

    @pytest.mark.asyncio
    async def test_invalid_batch_size_rejected(
        self,
        service_account_headers,
        community_server_with_data,
    ):
        """Endpoint rejects invalid batch_size values."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}&batch_size=-1",
                headers=service_account_headers,
            )

            assert response.status_code == 422

            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}&batch_size=1500",
                headers=service_account_headers,
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_community_server_id_required(
        self,
        service_account_headers,
    ):
        """Endpoint requires community_server_id parameter."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chunks/previously-seen/rechunk",
                headers=service_account_headers,
            )

            assert response.status_code == 422
