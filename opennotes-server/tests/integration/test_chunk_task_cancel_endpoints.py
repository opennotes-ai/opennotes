"""
Integration tests for rechunk task cancel and list endpoints.

Task: task-917 - Add cancel/clear endpoint for rechunk tasks

These tests verify:
1. DELETE /api/v1/chunks/tasks/{task_id} cancels a task and releases lock
2. GET /api/v1/chunks/tasks lists all active tasks
3. Authorization requirements for both endpoints
4. Force parameter behavior for DELETE endpoint
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.fact_checking.chunk_task_tracker import get_rechunk_task_tracker
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
        username="chunk-cancel-service-account",
        email="chunk-cancel-service@opennotes.local",
        hashed_password="hashed_password_placeholder",
        role="user",
        is_active=True,
        is_superuser=False,
        is_service_account=True,
        discord_id="discord_chunk_cancel_service",
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
        username="regular_cancel_user",
        email="regular_cancel@example.com",
        hashed_password="hashed_password_placeholder",
        role="user",
        is_active=True,
        is_superuser=False,
        is_service_account=False,
        discord_id="discord_regular_cancel",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"user": user}


@pytest.fixture
async def opennotes_admin_user(db):
    """Create an OpenNotes admin user."""
    from src.users.models import User

    user = User(
        id=uuid4(),
        username="opennotes_admin_cancel",
        email="admin_cancel@opennotes.local",
        hashed_password="hashed_password_placeholder",
        role="admin",
        is_active=True,
        is_superuser=False,
        is_service_account=False,
        is_opennotes_admin=True,
        discord_id="discord_admin_cancel",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"user": user}


@pytest.fixture
def service_account_headers(service_account_user):
    """Auth headers for service account."""
    return _create_auth_headers(service_account_user)


@pytest.fixture
def regular_user_headers(regular_user):
    """Auth headers for regular user."""
    return _create_auth_headers(regular_user)


@pytest.fixture
def admin_headers(opennotes_admin_user):
    """Auth headers for OpenNotes admin."""
    return _create_auth_headers(opennotes_admin_user)


class TestCancelRechunkTaskEndpoint:
    """Tests for DELETE /api/v1/chunks/tasks/{task_id} endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self):
        """Request without auth token returns 401."""
        task_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(f"/api/v1/chunks/tasks/{task_id}")

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_task_not_found_returns_404(
        self,
        service_account_headers,
    ):
        """Cancel request for non-existent task returns 404."""
        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=None)

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            task_id = uuid4()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(
                    f"/api/v1/chunks/tasks/{task_id}",
                    headers=service_account_headers,
                )

                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_cancel_in_progress_task_success(
        self,
        mock_lock_manager,
        service_account_headers,
    ):
        """Cancel request for in-progress task succeeds."""
        from src.fact_checking.chunk_task_schemas import (
            RechunkTaskResponse,
            RechunkTaskStatus,
            RechunkTaskType,
        )

        task_id = uuid4()
        task_response = RechunkTaskResponse(
            task_id=task_id,
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=None,
            batch_size=100,
            status=RechunkTaskStatus.IN_PROGRESS,
            processed_count=25,
            total_count=100,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=task_response)
        mock_tracker.delete_task = AsyncMock(return_value=True)

        mock_lock_manager.release_lock = AsyncMock(return_value=True)

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(
                    f"/api/v1/chunks/tasks/{task_id}",
                    headers=service_account_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["task_id"] == str(task_id)
                assert data["lock_released"] is True
                assert "cancelled" in data["message"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_cancel_completed_task_without_force_returns_400(
        self,
        service_account_headers,
    ):
        """Cancel request for completed task without force returns 400."""
        from src.fact_checking.chunk_task_schemas import (
            RechunkTaskResponse,
            RechunkTaskStatus,
            RechunkTaskType,
        )

        task_id = uuid4()
        task_response = RechunkTaskResponse(
            task_id=task_id,
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=None,
            batch_size=100,
            status=RechunkTaskStatus.COMPLETED,
            processed_count=100,
            total_count=100,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=task_response)

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(
                    f"/api/v1/chunks/tasks/{task_id}",
                    headers=service_account_headers,
                )

                assert response.status_code == 400
                assert "terminal state" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_cancel_completed_task_with_force_succeeds(
        self,
        mock_lock_manager,
        service_account_headers,
    ):
        """Cancel request for completed task with force=true succeeds."""
        from src.fact_checking.chunk_task_schemas import (
            RechunkTaskResponse,
            RechunkTaskStatus,
            RechunkTaskType,
        )

        task_id = uuid4()
        task_response = RechunkTaskResponse(
            task_id=task_id,
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=None,
            batch_size=100,
            status=RechunkTaskStatus.COMPLETED,
            processed_count=100,
            total_count=100,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=task_response)
        mock_tracker.delete_task = AsyncMock(return_value=True)

        mock_lock_manager.release_lock = AsyncMock(return_value=False)

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(
                    f"/api/v1/chunks/tasks/{task_id}?force=true",
                    headers=service_account_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert data["task_id"] == str(task_id)
                assert data["lock_released"] is False
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.verify_community_admin_by_uuid")
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_cancel_previously_seen_task_releases_correct_lock(
        self,
        mock_lock_manager,
        mock_verify_admin,
        service_account_headers,
    ):
        """Cancel request for previously_seen task releases lock with community_server_id."""
        from src.fact_checking.chunk_task_schemas import (
            RechunkTaskResponse,
            RechunkTaskStatus,
            RechunkTaskType,
        )

        task_id = uuid4()
        community_id = uuid4()
        task_response = RechunkTaskResponse(
            task_id=task_id,
            task_type=RechunkTaskType.PREVIOUSLY_SEEN,
            community_server_id=community_id,
            batch_size=100,
            status=RechunkTaskStatus.IN_PROGRESS,
            processed_count=25,
            total_count=100,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=task_response)
        mock_tracker.delete_task = AsyncMock(return_value=True)

        mock_lock_manager.release_lock = AsyncMock(return_value=True)
        mock_verify_admin.return_value = None

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(
                    f"/api/v1/chunks/tasks/{task_id}",
                    headers=service_account_headers,
                )

                assert response.status_code == 200
                mock_lock_manager.release_lock.assert_called_once_with(
                    "previously_seen", str(community_id)
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_regular_user_cannot_cancel_global_task(
        self,
        regular_user_headers,
    ):
        """Regular user cannot cancel global fact_check task (requires OpenNotes admin)."""
        from src.fact_checking.chunk_task_schemas import (
            RechunkTaskResponse,
            RechunkTaskStatus,
            RechunkTaskType,
        )

        task_id = uuid4()
        task_response = RechunkTaskResponse(
            task_id=task_id,
            task_type=RechunkTaskType.FACT_CHECK,
            community_server_id=None,
            batch_size=100,
            status=RechunkTaskStatus.IN_PROGRESS,
            processed_count=25,
            total_count=100,
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_tracker = MagicMock()
        mock_tracker.get_task = AsyncMock(return_value=task_response)

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(
                    f"/api/v1/chunks/tasks/{task_id}",
                    headers=regular_user_headers,
                )

                assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestListRechunkTasksEndpoint:
    """Tests for GET /api/v1/chunks/tasks endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self):
        """Request without auth token returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/chunks/tasks")

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_tasks_empty(
        self,
        service_account_headers,
    ):
        """List tasks returns empty array when no tasks exist."""
        mock_tracker = MagicMock()
        mock_tracker.list_tasks = AsyncMock(return_value=[])

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/chunks/tasks",
                    headers=service_account_headers,
                )

                assert response.status_code == 200
                assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_tasks_returns_all_tasks(
        self,
        service_account_headers,
    ):
        """List tasks returns all tasks."""
        from src.fact_checking.chunk_task_schemas import (
            RechunkTaskResponse,
            RechunkTaskStatus,
            RechunkTaskType,
        )

        task_id_1 = uuid4()
        task_id_2 = uuid4()
        tasks = [
            RechunkTaskResponse(
                task_id=task_id_1,
                task_type=RechunkTaskType.FACT_CHECK,
                community_server_id=None,
                batch_size=100,
                status=RechunkTaskStatus.IN_PROGRESS,
                processed_count=25,
                total_count=100,
                error=None,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
            RechunkTaskResponse(
                task_id=task_id_2,
                task_type=RechunkTaskType.PREVIOUSLY_SEEN,
                community_server_id=uuid4(),
                batch_size=50,
                status=RechunkTaskStatus.PENDING,
                processed_count=0,
                total_count=50,
                error=None,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
        ]

        mock_tracker = MagicMock()
        mock_tracker.list_tasks = AsyncMock(return_value=tasks)

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/chunks/tasks",
                    headers=service_account_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert len(data) == 2
                task_ids = {task["task_id"] for task in data}
                assert str(task_id_1) in task_ids
                assert str(task_id_2) in task_ids
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_tasks_filters_by_status(
        self,
        service_account_headers,
    ):
        """List tasks with status filter only returns matching tasks."""
        from src.fact_checking.chunk_task_schemas import (
            RechunkTaskResponse,
            RechunkTaskStatus,
            RechunkTaskType,
        )

        task_id = uuid4()
        tasks = [
            RechunkTaskResponse(
                task_id=task_id,
                task_type=RechunkTaskType.FACT_CHECK,
                community_server_id=None,
                batch_size=100,
                status=RechunkTaskStatus.IN_PROGRESS,
                processed_count=25,
                total_count=100,
                error=None,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
        ]

        mock_tracker = MagicMock()
        mock_tracker.list_tasks = AsyncMock(return_value=tasks)

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/chunks/tasks?status=in_progress",
                    headers=service_account_headers,
                )

                assert response.status_code == 200
                data = response.json()
                assert len(data) == 1
                assert data[0]["status"] == "in_progress"

                mock_tracker.list_tasks.assert_called_once()
                call_kwargs = mock_tracker.list_tasks.call_args.kwargs
                assert call_kwargs.get("status") == RechunkTaskStatus.IN_PROGRESS
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_regular_user_can_list_own_community_tasks(
        self,
        regular_user_headers,
    ):
        """Regular user can list tasks (read-only operation)."""
        mock_tracker = MagicMock()
        mock_tracker.list_tasks = AsyncMock(return_value=[])

        app.dependency_overrides[get_rechunk_task_tracker] = lambda: mock_tracker
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/chunks/tasks",
                    headers=regular_user_headers,
                )

                assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()
