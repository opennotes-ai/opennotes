"""
Integration tests for the fact-checking import router endpoints.

Tests for:
- POST /api/v1/fact-checking/import/scrape-candidates - starts scrape batch job
- POST /api/v1/fact-checking/import/promote-candidates - starts promotion batch job

Both endpoints should:
- Accept batch_size and dry_run parameters
- Return BatchJobResponse (201 Created)
- Require authentication
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.batch_jobs.models import BatchJob, BatchJobStatus
from src.fact_checking.import_pipeline.router import get_import_service
from src.main import app


class TestImportRouterFixtures:
    """Fixtures for import router testing scenarios."""

    @pytest.fixture
    async def test_user(self, db):
        """Create a test user for authenticated requests."""
        from src.users.models import User

        user = User(
            id=uuid4(),
            username="import_test_user",
            email="import_test@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_import_test",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @pytest.fixture
    def auth_headers(self, test_user):
        """Create auth headers for test user."""
        token_data = {
            "sub": str(test_user.id),
            "username": test_user.username,
            "role": test_user.role,
        }
        access_token = create_access_token(token_data)
        return {"Authorization": f"Bearer {access_token}"}

    @pytest.fixture
    def mock_scrape_job(self):
        """Create a mock BatchJob for scrape operations."""
        now = datetime.now(UTC)
        return BatchJob(
            id=uuid4(),
            job_type="scrape:candidates",
            status=BatchJobStatus.PENDING,
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            metadata_={"batch_size": 100, "dry_run": False},
            created_at=now,
            updated_at=now,
        )

    @pytest.fixture
    def mock_promotion_job(self):
        """Create a mock BatchJob for promotion operations."""
        now = datetime.now(UTC)
        return BatchJob(
            id=uuid4(),
            job_type="promote:candidates",
            status=BatchJobStatus.PENDING,
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            metadata_={"batch_size": 100, "dry_run": False},
            created_at=now,
            updated_at=now,
        )


class TestScrapeCandidatesEndpoint(TestImportRouterFixtures):
    """Tests for POST /api/v1/fact-checking/import/scrape-candidates endpoint."""

    @pytest.mark.asyncio
    async def test_scrape_candidates_returns_201_with_batch_job_response(
        self,
        auth_headers,
        mock_scrape_job,
    ):
        """Authenticated request returns 201 with BatchJobResponse."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_scrape_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/scrape-candidates",
                    json={"batch_size": 100, "dry_run": False},
                    headers=auth_headers,
                )

                assert response.status_code == 201
                data = response.json()
                assert data["id"] == str(mock_scrape_job.id)
                assert data["job_type"] == "scrape:candidates"
                assert data["status"] == "pending"
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_scrape_candidates_with_dry_run(
        self,
        auth_headers,
        mock_scrape_job,
    ):
        """Dry run parameter is passed to service."""
        mock_scrape_job.metadata_ = {"batch_size": 50, "dry_run": True}

        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_scrape_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/scrape-candidates",
                    json={"batch_size": 50, "dry_run": True},
                    headers=auth_headers,
                )

                assert response.status_code == 201
                mock_service.start_scrape_job.assert_called_once_with(batch_size=50, dry_run=True)
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_scrape_candidates_requires_authentication(self):
        """Request without auth token returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/scrape-candidates",
                json={"batch_size": 100, "dry_run": False},
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_scrape_candidates_uses_default_values(
        self,
        auth_headers,
        mock_scrape_job,
    ):
        """Default values are used when not provided."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_scrape_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/scrape-candidates",
                    json={},
                    headers=auth_headers,
                )

                assert response.status_code == 201
                mock_service.start_scrape_job.assert_called_once_with(
                    batch_size=1000, dry_run=False
                )
        finally:
            app.dependency_overrides.pop(get_import_service, None)


class TestPromoteCandidatesEndpoint(TestImportRouterFixtures):
    """Tests for POST /api/v1/fact-checking/import/promote-candidates endpoint."""

    @pytest.mark.asyncio
    async def test_promote_candidates_returns_201_with_batch_job_response(
        self,
        auth_headers,
        mock_promotion_job,
    ):
        """Authenticated request returns 201 with BatchJobResponse."""
        mock_service = MagicMock()
        mock_service.start_promotion_job = AsyncMock(return_value=mock_promotion_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/promote-candidates",
                    json={"batch_size": 100, "dry_run": False},
                    headers=auth_headers,
                )

                assert response.status_code == 201
                data = response.json()
                assert data["id"] == str(mock_promotion_job.id)
                assert data["job_type"] == "promote:candidates"
                assert data["status"] == "pending"
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_promote_candidates_with_dry_run(
        self,
        auth_headers,
        mock_promotion_job,
    ):
        """Dry run parameter is passed to service."""
        mock_promotion_job.metadata_ = {"batch_size": 50, "dry_run": True}

        mock_service = MagicMock()
        mock_service.start_promotion_job = AsyncMock(return_value=mock_promotion_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/promote-candidates",
                    json={"batch_size": 50, "dry_run": True},
                    headers=auth_headers,
                )

                assert response.status_code == 201
                mock_service.start_promotion_job.assert_called_once_with(
                    batch_size=50, dry_run=True
                )
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_promote_candidates_requires_authentication(self):
        """Request without auth token returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/promote-candidates",
                json={"batch_size": 100, "dry_run": False},
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_promote_candidates_uses_default_values(
        self,
        auth_headers,
        mock_promotion_job,
    ):
        """Default values are used when not provided."""
        mock_service = MagicMock()
        mock_service.start_promotion_job = AsyncMock(return_value=mock_promotion_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/promote-candidates",
                    json={},
                    headers=auth_headers,
                )

                assert response.status_code == 201
                mock_service.start_promotion_job.assert_called_once_with(
                    batch_size=1000, dry_run=False
                )
        finally:
            app.dependency_overrides.pop(get_import_service, None)
