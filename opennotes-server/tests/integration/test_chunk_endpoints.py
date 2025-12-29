"""
Integration tests for chunk re-embedding API endpoints.

These tests verify that:
1. POST /chunks/fact-check/rechunk requires authentication (401 without, success with)
2. POST /chunks/previously-seen/rechunk requires authentication (401 without, success with)
3. Endpoints accept community_server_id and batch_size parameters
4. Background task processing is triggered for large datasets
5. Service accounts can access the endpoints
6. Regular users without admin/moderator role get 403 Forbidden on BOTH endpoints

Authorization Model:
Both rechunk endpoints require elevated permissions. Access is granted to:
- Service accounts (is_service_account=True)
- OpenNotes admins (is_opennotes_admin=True)
- Discord users with Manage Server permission (from signed JWT)
- Community admins/moderators (role='admin'/'moderator')

Regular users without the above permissions receive 403 Forbidden.

Task: task-871.04 - Create API endpoints for bulk re-chunking operations
Task: task-871.10 - Add authorization check to rechunk endpoints
Task: task-871.40 - Refactor test fixture inheritance to module-level fixtures

Note: Fixtures are defined at module-level for better pytest-asyncio reliability.
Class-based fixture inheritance can cause issues with async fixtures.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.main import app


def _create_auth_headers(user_data: dict) -> dict:
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
async def service_account_user(db):
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
async def regular_user(db):
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
async def community_server_with_data(db):
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


@pytest.fixture
def service_account_headers(service_account_user):
    """Auth headers for service account."""
    return _create_auth_headers(service_account_user)


@pytest.fixture
def regular_user_headers(regular_user):
    """Auth headers for regular user."""
    return _create_auth_headers(regular_user)


class TestFactCheckRechunkEndpoint:
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
    @patch("src.fact_checking.chunk_router.process_fact_check_rechunk_task")
    @patch("src.fact_checking.chunk_router.get_rechunk_task_tracker")
    async def test_service_account_can_initiate_rechunk(
        self,
        mock_get_tracker,
        mock_task,
        service_account_headers,
        community_server_with_data,
    ):
        """Service account can initiate fact check rechunking."""
        from unittest.mock import MagicMock
        from uuid import uuid4 as gen_uuid

        from src.fact_checking.chunk_task_schemas import RechunkTaskResponse, RechunkTaskStatus

        mock_task.kiq = AsyncMock()

        mock_tracker = MagicMock()
        task_response = RechunkTaskResponse(
            task_id=gen_uuid(),
            task_type="fact_check",
            community_server_id=community_server_with_data["server"].id,
            batch_size=100,
            status=RechunkTaskStatus.PENDING,
            processed_count=0,
            total_count=3,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        mock_tracker.create_task = AsyncMock(return_value=task_response)
        mock_get_tracker.return_value = mock_tracker

        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"
            assert "total_items" in data
            assert "task_id" in data

            mock_task.kiq.assert_called_once()
            call_kwargs = mock_task.kiq.call_args.kwargs
            assert call_kwargs["task_id"] == data["task_id"]
            assert call_kwargs["community_server_id"] == str(server.id)
            assert call_kwargs["batch_size"] == 100

    @pytest.mark.asyncio
    async def test_regular_user_gets_403_without_community_membership(
        self,
        regular_user_headers,
        community_server_with_data,
    ):
        """Regular user without community membership gets 403 Forbidden."""
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}",
                headers=regular_user_headers,
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.process_fact_check_rechunk_task")
    @patch("src.fact_checking.chunk_router.get_rechunk_task_tracker")
    async def test_batch_size_parameter_accepted(
        self,
        mock_get_tracker,
        mock_task,
        service_account_headers,
        community_server_with_data,
    ):
        """Endpoint accepts custom batch_size parameter."""
        from unittest.mock import MagicMock
        from uuid import uuid4 as gen_uuid

        from src.fact_checking.chunk_task_schemas import RechunkTaskResponse, RechunkTaskStatus

        mock_task.kiq = AsyncMock()

        mock_tracker = MagicMock()
        task_response = RechunkTaskResponse(
            task_id=gen_uuid(),
            task_type="fact_check",
            community_server_id=community_server_with_data["server"].id,
            batch_size=50,
            status=RechunkTaskStatus.PENDING,
            processed_count=0,
            total_count=3,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        mock_tracker.create_task = AsyncMock(return_value=task_response)
        mock_get_tracker.return_value = mock_tracker

        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}&batch_size=50",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"

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


class TestPreviouslySeenRechunkEndpoint:
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
    @patch("src.fact_checking.chunk_router.process_previously_seen_rechunk_task")
    @patch("src.fact_checking.chunk_router.get_rechunk_task_tracker")
    async def test_service_account_can_initiate_rechunk(
        self,
        mock_get_tracker,
        mock_task,
        service_account_headers,
        community_server_with_data,
    ):
        """Service account can initiate previously seen message rechunking."""
        from unittest.mock import MagicMock
        from uuid import uuid4 as gen_uuid

        from src.fact_checking.chunk_task_schemas import RechunkTaskResponse, RechunkTaskStatus

        mock_task.kiq = AsyncMock()

        mock_tracker = MagicMock()
        task_response = RechunkTaskResponse(
            task_id=gen_uuid(),
            task_type="previously_seen",
            community_server_id=community_server_with_data["server"].id,
            batch_size=100,
            status=RechunkTaskStatus.PENDING,
            processed_count=0,
            total_count=2,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        mock_tracker.create_task = AsyncMock(return_value=task_response)
        mock_get_tracker.return_value = mock_tracker

        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"
            assert "total_items" in data
            assert "task_id" in data

            mock_task.kiq.assert_called_once()
            call_kwargs = mock_task.kiq.call_args.kwargs
            assert call_kwargs["task_id"] == data["task_id"]
            assert call_kwargs["community_server_id"] == str(server.id)
            assert call_kwargs["batch_size"] == 100

    @pytest.mark.asyncio
    async def test_regular_user_gets_403_without_community_membership(
        self,
        regular_user_headers,
        community_server_with_data,
    ):
        """Regular user without community membership gets 403 Forbidden.

        Both rechunk endpoints require elevated permissions (service account,
        OpenNotes admin, Discord Manage Server permission, or community
        admin/moderator role). Regular users should receive 403.
        """
        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}",
                headers=regular_user_headers,
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.process_previously_seen_rechunk_task")
    @patch("src.fact_checking.chunk_router.get_rechunk_task_tracker")
    async def test_batch_size_parameter_accepted(
        self,
        mock_get_tracker,
        mock_task,
        service_account_headers,
        community_server_with_data,
    ):
        """Endpoint accepts custom batch_size parameter."""
        from unittest.mock import MagicMock
        from uuid import uuid4 as gen_uuid

        from src.fact_checking.chunk_task_schemas import RechunkTaskResponse, RechunkTaskStatus

        mock_task.kiq = AsyncMock()

        mock_tracker = MagicMock()
        task_response = RechunkTaskResponse(
            task_id=gen_uuid(),
            task_type="previously_seen",
            community_server_id=community_server_with_data["server"].id,
            batch_size=75,
            status=RechunkTaskStatus.PENDING,
            processed_count=0,
            total_count=2,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        mock_tracker.create_task = AsyncMock(return_value=task_response)
        mock_get_tracker.return_value = mock_tracker

        server = community_server_with_data["server"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}&batch_size=75",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"

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


class TestRechunkConcurrencyControl:
    """Tests for rechunk endpoint concurrency control.

    Task: task-871.20 - Add rate limiting and concurrency control for rechunk endpoints

    These tests mock the RechunkLockManager at the module level to test the 409 conflict
    response without requiring real Redis connections.
    """

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.process_fact_check_rechunk_task")
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_fact_check_rechunk_returns_409_when_already_in_progress(
        self,
        mock_lock_manager,
        mock_task,
        service_account_headers,
        community_server_with_data,
    ):
        """Second fact check rechunk request returns 409 when one is in progress."""
        server = community_server_with_data["server"]

        mock_task.kiq = AsyncMock()
        mock_lock_manager.acquire_lock = AsyncMock(return_value=False)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/fact-check/rechunk?community_server_id={server.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 409
            data = response.json()
            assert "already in progress" in data["detail"]

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.process_previously_seen_rechunk_task")
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_previously_seen_rechunk_returns_409_when_already_in_progress(
        self,
        mock_lock_manager,
        mock_task,
        service_account_headers,
        community_server_with_data,
    ):
        """Second previously seen rechunk request returns 409 when one is in progress for same community."""
        server = community_server_with_data["server"]

        mock_task.kiq = AsyncMock()
        mock_lock_manager.acquire_lock = AsyncMock(return_value=False)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 409
            data = response.json()
            assert "already in progress" in data["detail"]

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.process_previously_seen_rechunk_task")
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    @patch("src.fact_checking.chunk_router.get_rechunk_task_tracker")
    async def test_previously_seen_rechunk_different_communities_allowed(
        self,
        mock_get_tracker,
        mock_lock_manager,
        mock_task,
        service_account_headers,
        community_server_with_data,
        db,
    ):
        """Different communities can rechunk previously seen messages concurrently."""
        from unittest.mock import MagicMock
        from uuid import uuid4 as gen_uuid

        from src.fact_checking.chunk_task_schemas import RechunkTaskResponse, RechunkTaskStatus
        from src.llm_config.models import CommunityServer

        mock_task.kiq = AsyncMock()

        server2 = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_id=f"test-server-2-{uuid4().hex[:8]}",
            name="Test Server 2 for Chunking",
            is_active=True,
        )
        db.add(server2)
        await db.commit()
        await db.refresh(server2)

        mock_lock_manager.acquire_lock = AsyncMock(return_value=True)

        mock_tracker = MagicMock()
        task_response = RechunkTaskResponse(
            task_id=gen_uuid(),
            task_type="previously_seen",
            community_server_id=server2.id,
            batch_size=100,
            status=RechunkTaskStatus.PENDING,
            processed_count=0,
            total_count=0,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        mock_tracker.create_task = AsyncMock(return_value=task_response)
        mock_get_tracker.return_value = mock_tracker

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/chunks/previously-seen/rechunk?community_server_id={server2.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"
