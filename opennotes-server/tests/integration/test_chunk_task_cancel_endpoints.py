"""
Integration tests for rechunk job cancel and list endpoints.

Task: task-917 - Add cancel/clear endpoint for rechunk tasks
Task: task-986 - Refactor to use BatchJob infrastructure

These tests verify:
1. DELETE /api/v1/chunks/jobs/{job_id} cancels a job and releases lock
2. GET /api/v1/chunks/jobs lists all rechunk batch jobs
3. GET /api/v1/chunks/jobs/{job_id} gets a specific rechunk batch job
4. Authorization requirements for all endpoints
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.batch_jobs.models import BatchJobStatus
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
    """Create a regular user (not a service account, not an admin)."""
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
    """Create an OpenNotes admin user.

    Note: is_opennotes_admin is on UserProfile, not User. For authorization
    checks that use getattr(user, 'is_opennotes_admin', False), we set it
    directly on the User object after creation.
    """
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
        discord_id="discord_admin_cancel",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    user.is_opennotes_admin = True

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


@pytest.fixture
async def fact_check_batch_job(db):
    """Create a fact check rechunk batch job for testing."""
    from src.batch_jobs.models import BatchJob

    job = BatchJob(
        id=uuid4(),
        job_type="rechunk:fact_check",
        status=BatchJobStatus.IN_PROGRESS.value,
        total_tasks=100,
        completed_tasks=25,
        failed_tasks=0,
        metadata_={"community_server_id": None, "batch_size": 100, "chunk_type": "fact_check"},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@pytest.fixture
async def previously_seen_batch_job(db):
    """Create a previously seen rechunk batch job for testing."""
    from src.batch_jobs.models import BatchJob

    community_id = uuid4()
    job = BatchJob(
        id=uuid4(),
        job_type="rechunk:previously_seen",
        status=BatchJobStatus.IN_PROGRESS.value,
        total_tasks=50,
        completed_tasks=10,
        failed_tasks=2,
        metadata_={
            "community_server_id": str(community_id),
            "batch_size": 100,
            "chunk_type": "previously_seen",
        },
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


class TestCancelRechunkJobEndpoint:
    """Tests for DELETE /api/v1/chunks/jobs/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self):
        """Request without auth token returns 401."""
        job_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(f"/api/v1/chunks/jobs/{job_id}")

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_job_not_found_returns_404(
        self,
        service_account_headers,
    ):
        """Cancel request for non-existent job returns 404."""
        job_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/chunks/jobs/{job_id}",
                headers=service_account_headers,
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_cancel_in_progress_job_success(
        self,
        mock_lock_manager,
        service_account_headers,
        fact_check_batch_job,
    ):
        """Cancel request for in-progress job succeeds."""
        mock_lock_manager.release_lock = AsyncMock(return_value=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/chunks/jobs/{fact_check_batch_job.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 204
            mock_lock_manager.release_lock.assert_called_with("fact_check")

    @pytest.mark.asyncio
    async def test_cancel_completed_job_returns_409(
        self,
        service_account_headers,
        db,
    ):
        """Cancel request for completed job returns 409."""
        from src.batch_jobs.models import BatchJob

        job = BatchJob(
            id=uuid4(),
            job_type="rechunk:fact_check",
            status=BatchJobStatus.COMPLETED.value,
            total_tasks=100,
            completed_tasks=100,
            failed_tasks=0,
            metadata_={"community_server_id": None, "batch_size": 100, "chunk_type": "fact_check"},
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/chunks/jobs/{job.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 409
            assert "cancel" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.verify_community_admin_by_uuid")
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_cancel_previously_seen_job_releases_correct_lock(
        self,
        mock_lock_manager,
        mock_verify_admin,
        service_account_headers,
        previously_seen_batch_job,
    ):
        """Cancel request for previously_seen job releases lock with community_server_id."""
        mock_lock_manager.release_lock = AsyncMock(return_value=True)
        mock_verify_admin.return_value = None

        community_id = previously_seen_batch_job.metadata_["community_server_id"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/chunks/jobs/{previously_seen_batch_job.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 204
            mock_lock_manager.release_lock.assert_called_once_with("previously_seen", community_id)

    @pytest.mark.asyncio
    async def test_regular_user_cannot_cancel_global_job(
        self,
        regular_user_headers,
        fact_check_batch_job,
    ):
        """Regular user cannot cancel global fact_check job (requires OpenNotes admin)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/chunks/jobs/{fact_check_batch_job.id}",
                headers=regular_user_headers,
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cancel_failed_job_returns_409(
        self,
        service_account_headers,
        db,
    ):
        """Cancel request for failed job returns 409."""
        from src.batch_jobs.models import BatchJob

        job = BatchJob(
            id=uuid4(),
            job_type="rechunk:fact_check",
            status=BatchJobStatus.FAILED.value,
            total_tasks=100,
            completed_tasks=50,
            failed_tasks=50,
            metadata_={"community_server_id": None, "batch_size": 100, "chunk_type": "fact_check"},
            error_summary={"error": "Task failed due to timeout"},
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/chunks/jobs/{job.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 409

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.get_profile_by_id")
    @patch("src.fact_checking.chunk_router._get_profile_id_from_user")
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_opennotes_admin_can_cancel_global_job(
        self,
        mock_lock_manager,
        mock_get_profile_id,
        mock_get_profile,
        admin_headers,
        fact_check_batch_job,
    ):
        """OpenNotes admin can cancel global fact_check job."""
        profile_id = uuid4()
        mock_lock_manager.release_lock = AsyncMock(return_value=True)

        mock_get_profile_id.return_value = profile_id
        mock_profile = MagicMock()
        mock_profile.is_opennotes_admin = True
        mock_get_profile.return_value = mock_profile

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/chunks/jobs/{fact_check_batch_job.id}",
                headers=admin_headers,
            )

            assert response.status_code == 204

    @pytest.mark.asyncio
    @patch("src.fact_checking.chunk_router.rechunk_lock_manager")
    async def test_service_account_can_cancel_global_job(
        self,
        mock_lock_manager,
        service_account_headers,
        fact_check_batch_job,
    ):
        """Service account can cancel global fact_check job."""
        mock_lock_manager.release_lock = AsyncMock(return_value=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/chunks/jobs/{fact_check_batch_job.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 204


class TestListRechunkJobsEndpoint:
    """Tests for GET /api/v1/chunks/jobs endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self):
        """Request without auth token returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/chunks/jobs")

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_jobs_empty(
        self,
        service_account_headers,
    ):
        """List jobs returns empty array when no jobs exist."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/chunks/jobs",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_jobs_returns_all_rechunk_jobs(
        self,
        service_account_headers,
        fact_check_batch_job,
        previously_seen_batch_job,
    ):
        """List jobs returns all rechunk batch jobs."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/chunks/jobs",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            job_ids = {job["id"] for job in data}
            assert str(fact_check_batch_job.id) in job_ids
            assert str(previously_seen_batch_job.id) in job_ids

    @pytest.mark.asyncio
    async def test_list_jobs_filters_by_status(
        self,
        service_account_headers,
        fact_check_batch_job,
        db,
    ):
        """List jobs with status filter only returns matching jobs."""
        from src.batch_jobs.models import BatchJob

        completed_job = BatchJob(
            id=uuid4(),
            job_type="rechunk:fact_check",
            status=BatchJobStatus.COMPLETED.value,
            total_tasks=100,
            completed_tasks=100,
            failed_tasks=0,
            metadata_={"community_server_id": None, "batch_size": 100, "chunk_type": "fact_check"},
        )
        db.add(completed_job)
        await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/chunks/jobs?status=in_progress",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_regular_user_can_list_jobs(
        self,
        regular_user_headers,
        fact_check_batch_job,
    ):
        """Regular user can list jobs (read-only operation)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/chunks/jobs",
                headers=regular_user_headers,
            )

            assert response.status_code == 200


class TestGetRechunkJobEndpoint:
    """Tests for GET /api/v1/chunks/jobs/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self):
        """Request without auth token returns 401."""
        job_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/chunks/jobs/{job_id}")

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_job_not_found_returns_404(
        self,
        service_account_headers,
    ):
        """Get request for non-existent job returns 404."""
        job_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/chunks/jobs/{job_id}",
                headers=service_account_headers,
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_job_returns_job_details(
        self,
        service_account_headers,
        fact_check_batch_job,
    ):
        """Get request for existing job returns job details."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/chunks/jobs/{fact_check_batch_job.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(fact_check_batch_job.id)
            assert data["job_type"] == "rechunk:fact_check"
            assert data["status"] == "in_progress"
            assert data["total_tasks"] == 100
            assert data["completed_tasks"] == 25

    @pytest.mark.asyncio
    async def test_get_non_rechunk_job_returns_404(
        self,
        service_account_headers,
        db,
    ):
        """Get request for non-rechunk job type returns 404."""
        from src.batch_jobs.models import BatchJob

        other_job = BatchJob(
            id=uuid4(),
            job_type="import:fact_check",
            status=BatchJobStatus.IN_PROGRESS.value,
            total_tasks=100,
            completed_tasks=0,
            failed_tasks=0,
            metadata_={},
        )
        db.add(other_job)
        await db.commit()
        await db.refresh(other_job)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/chunks/jobs/{other_job.id}",
                headers=service_account_headers,
            )

            assert response.status_code == 404
            assert "not a rechunk job" in response.json()["detail"].lower()
