"""
Integration tests for the fact-checking import router endpoints.

Tests for:
- POST /api/v1/fact-checking/import/scrape-candidates - starts scrape batch job
- POST /api/v1/fact-checking/import/promote-candidates - starts promotion batch job

Both endpoints should:
- Accept batch_size and dry_run parameters
- Return BatchJobResponse (201 Created)
- Require authentication (Bearer token or X-API-Key)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.auth.models import APIKeyCreate
from src.batch_jobs.import_service import ConcurrentJobError
from src.batch_jobs.models import BatchJob, BatchJobStatus
from src.fact_checking.import_pipeline.router import get_import_service
from src.main import app
from src.users.crud import create_api_key


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
    async def api_key_headers(self, test_user, db):
        """Create API key headers for test user."""
        _, raw_key = await create_api_key(
            db=db,
            user_id=test_user.id,
            api_key_create=APIKeyCreate(name="Test Import API Key", expires_in_days=30),
        )
        await db.commit()
        return {"X-API-Key": raw_key}

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


@pytest.mark.integration
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
                call_kwargs = mock_service.start_scrape_job.call_args.kwargs
                assert call_kwargs["batch_size"] == 50
                assert call_kwargs["dry_run"] is True
                assert "user_id" in call_kwargs
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
                call_kwargs = mock_service.start_scrape_job.call_args.kwargs
                assert call_kwargs["batch_size"] == 1000
                assert call_kwargs["dry_run"] is False
                assert "user_id" in call_kwargs
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_scrape_candidates_with_api_key_authentication(
        self,
        api_key_headers,
        mock_scrape_job,
    ):
        """Request with X-API-Key header returns 201."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_scrape_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/scrape-candidates",
                    json={"batch_size": 100, "dry_run": False},
                    headers=api_key_headers,
                )

                assert response.status_code == 201
                data = response.json()
                assert data["id"] == str(mock_scrape_job.id)
                assert data["job_type"] == "scrape:candidates"
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_scrape_candidates_batch_size_zero_returns_422(self, auth_headers):
        """batch_size=0 returns 422 validation error."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/scrape-candidates",
                json={"batch_size": 0, "dry_run": False},
                headers=auth_headers,
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_scrape_candidates_batch_size_negative_returns_422(self, auth_headers):
        """batch_size=-1 returns 422 validation error."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/scrape-candidates",
                json={"batch_size": -1, "dry_run": False},
                headers=auth_headers,
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_scrape_candidates_batch_size_exceeds_max_returns_422(self, auth_headers):
        """batch_size=10001 (exceeds max 10000) returns 422 validation error."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/scrape-candidates",
                json={"batch_size": 10001, "dry_run": False},
                headers=auth_headers,
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_scrape_candidates_service_exception_propagates(
        self,
        auth_headers,
    ):
        """Service exception is propagated (not silently swallowed)."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/scrape-candidates",
                    json={"batch_size": 100, "dry_run": False},
                    headers=auth_headers,
                )

                assert response.status_code == 500
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_scrape_candidates_returns_409_when_job_already_running(
        self,
        auth_headers,
    ):
        """Returns 409 Conflict when a scrape job is already in progress."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(side_effect=ConcurrentJobError("scrape"))

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/scrape-candidates",
                    json={"batch_size": 100, "dry_run": False},
                    headers=auth_headers,
                )

                assert response.status_code == 409
                data = response.json()
                assert "detail" in data
                assert "scrape" in data["detail"].lower()
                assert "already in progress" in data["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_import_service, None)


@pytest.mark.integration
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
                call_kwargs = mock_service.start_promotion_job.call_args.kwargs
                assert call_kwargs["batch_size"] == 50
                assert call_kwargs["dry_run"] is True
                assert "user_id" in call_kwargs
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
                call_kwargs = mock_service.start_promotion_job.call_args.kwargs
                assert call_kwargs["batch_size"] == 1000
                assert call_kwargs["dry_run"] is False
                assert "user_id" in call_kwargs
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_promote_candidates_with_api_key_authentication(
        self,
        api_key_headers,
        mock_promotion_job,
    ):
        """Request with X-API-Key header returns 201."""
        mock_service = MagicMock()
        mock_service.start_promotion_job = AsyncMock(return_value=mock_promotion_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/promote-candidates",
                    json={"batch_size": 100, "dry_run": False},
                    headers=api_key_headers,
                )

                assert response.status_code == 201
                data = response.json()
                assert data["id"] == str(mock_promotion_job.id)
                assert data["job_type"] == "promote:candidates"
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_promote_candidates_batch_size_zero_returns_422(self, auth_headers):
        """batch_size=0 returns 422 validation error."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/promote-candidates",
                json={"batch_size": 0, "dry_run": False},
                headers=auth_headers,
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_promote_candidates_batch_size_negative_returns_422(self, auth_headers):
        """batch_size=-1 returns 422 validation error."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/promote-candidates",
                json={"batch_size": -1, "dry_run": False},
                headers=auth_headers,
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_promote_candidates_batch_size_exceeds_max_returns_422(self, auth_headers):
        """batch_size=10001 (exceeds max 10000) returns 422 validation error."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/promote-candidates",
                json={"batch_size": 10001, "dry_run": False},
                headers=auth_headers,
            )

            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_promote_candidates_service_exception_propagates(
        self,
        auth_headers,
    ):
        """Service exception is propagated (not silently swallowed)."""
        mock_service = MagicMock()
        mock_service.start_promotion_job = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/promote-candidates",
                    json={"batch_size": 100, "dry_run": False},
                    headers=auth_headers,
                )

                assert response.status_code == 500
        finally:
            app.dependency_overrides.pop(get_import_service, None)

    @pytest.mark.asyncio
    async def test_promote_candidates_returns_409_when_job_already_running(
        self,
        auth_headers,
    ):
        """Returns 409 Conflict when a promotion job is already in progress."""
        mock_service = MagicMock()
        mock_service.start_promotion_job = AsyncMock(side_effect=ConcurrentJobError("promote"))

        app.dependency_overrides[get_import_service] = lambda: mock_service
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/fact-checking/import/promote-candidates",
                    json={"batch_size": 100, "dry_run": False},
                    headers=auth_headers,
                )

                assert response.status_code == 409
                data = response.json()
                assert "detail" in data
                assert "promote" in data["detail"].lower()
                assert "already in progress" in data["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_import_service, None)
