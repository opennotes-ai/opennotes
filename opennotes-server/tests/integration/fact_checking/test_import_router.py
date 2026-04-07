"""
Integration tests for the fact-checking import router endpoints.

Tests for:
- POST /api/v1/fact-checking/import/enqueue-scrapes - starts scrape batch job via DBOS
- POST /api/v1/fact-checking/import/scrape-candidates - starts scrape batch job
- POST /api/v1/fact-checking/import/promote-candidates - starts promotion batch job
- POST /api/v1/fact-checking/import/fact-check-bureau - starts import batch job

All job-creating endpoints should:
- Accept batch_size and dry_run parameters
- Return BatchJobResponse (201 Created)
- Require authentication (Bearer token or X-API-Key)

Note: Rate limiting for concurrent jobs is now handled by DistributedRateLimitMiddleware,
not by the service layer. Rate limiting tests are in test_batch_job_rate_limit_middleware.py.

Task: task-1006.03 - Add scrape and promotion endpoints
Task: task-1414.02 - Rewire /enqueue-scrapes endpoint to DBOS

Fixtures:
- auth_headers: from tests/conftest.py (uses registered_user)
- api_key_headers: from tests/integration/fact_checking/conftest.py
- mock_scrape_job: from tests/integration/fact_checking/conftest.py
- mock_promotion_job: from tests/integration/fact_checking/conftest.py
- cleanup_dependency_overrides: from tests/integration/fact_checking/conftest.py (autouse)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.batch_jobs import PROMOTION_JOB_TYPE, SCRAPE_JOB_TYPE
from src.fact_checking.import_pipeline.router import get_import_service
from src.main import app


@pytest.mark.integration
class TestScrapeCandidatesEndpoint:
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
            assert data["job_type"] == SCRAPE_JOB_TYPE
            assert data["status"] == "pending"

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
            assert data["job_type"] == SCRAPE_JOB_TYPE

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
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/scrape-candidates",
                json={"batch_size": 100, "dry_run": False},
                headers=auth_headers,
            )

            assert response.status_code == 500


@pytest.mark.integration
class TestPromoteCandidatesEndpoint:
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
            assert data["job_type"] == PROMOTION_JOB_TYPE
            assert data["status"] == "pending"

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
            assert data["job_type"] == PROMOTION_JOB_TYPE

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
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/promote-candidates",
                json={"batch_size": 100, "dry_run": False},
                headers=auth_headers,
            )

            assert response.status_code == 500


@pytest.mark.integration
class TestEnqueueScrapesEndpoint:
    """Tests for POST /api/v1/fact-checking/import/enqueue-scrapes endpoint.

    After TASK-1414.02, this endpoint delegates to ImportBatchJobService.start_scrape_job()
    via DBOS instead of TaskIQ's enqueue_scrape_batch. It returns BatchJobResponse (201).
    """

    @pytest.mark.asyncio
    async def test_enqueue_scrapes_returns_201_with_batch_job_response(
        self,
        auth_headers,
        mock_scrape_job,
    ):
        """Authenticated request returns 201 with BatchJobResponse."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_scrape_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/enqueue-scrapes",
                json={"batch_size": 100},
                headers=auth_headers,
            )

            assert response.status_code == 201
            data = response.json()
            assert data["id"] == str(mock_scrape_job.id)
            assert data["job_type"] == SCRAPE_JOB_TYPE
            assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_enqueue_scrapes_passes_base_delay_to_service(
        self,
        auth_headers,
        mock_scrape_job,
    ):
        """base_delay parameter is passed through to service."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_scrape_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/enqueue-scrapes",
                json={"batch_size": 200, "base_delay": 2.5},
                headers=auth_headers,
            )

            assert response.status_code == 201
            call_kwargs = mock_service.start_scrape_job.call_args.kwargs
            assert call_kwargs["batch_size"] == 200
            assert call_kwargs["base_delay"] == 2.5
            assert "user_id" in call_kwargs

    @pytest.mark.asyncio
    async def test_enqueue_scrapes_requires_authentication(self):
        """Request without auth token returns 401."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/enqueue-scrapes",
                json={"batch_size": 100},
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_enqueue_scrapes_uses_default_values(
        self,
        auth_headers,
        mock_scrape_job,
    ):
        """Default values are used when not provided."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_scrape_job)

        app.dependency_overrides[get_import_service] = lambda: mock_service
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/enqueue-scrapes",
                json={},
                headers=auth_headers,
            )

            assert response.status_code == 201
            call_kwargs = mock_service.start_scrape_job.call_args.kwargs
            assert call_kwargs["batch_size"] == 1000
            assert call_kwargs["base_delay"] == 1.0
            assert "user_id" in call_kwargs

    @pytest.mark.asyncio
    async def test_enqueue_scrapes_active_job_returns_429(
        self,
        auth_headers,
    ):
        """ActiveJobExistsError returns 429."""
        from uuid import uuid4

        from src.batch_jobs import ActiveJobExistsError

        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(
            side_effect=ActiveJobExistsError(SCRAPE_JOB_TYPE, uuid4())
        )

        app.dependency_overrides[get_import_service] = lambda: mock_service
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/enqueue-scrapes",
                json={"batch_size": 100},
                headers=auth_headers,
            )

            assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_enqueue_scrapes_service_exception_propagates(
        self,
        auth_headers,
    ):
        """Service exception is propagated (not silently swallowed)."""
        mock_service = MagicMock()
        mock_service.start_scrape_job = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        app.dependency_overrides[get_import_service] = lambda: mock_service
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fact-checking/import/enqueue-scrapes",
                json={"batch_size": 100},
                headers=auth_headers,
            )

            assert response.status_code == 500
