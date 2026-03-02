from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import get_current_user_or_api_key
from src.database import get_db
from src.main import app
from src.simulation.schemas import DetailedNoteData, DetailedRequestData


def _mock_admin_user():
    user = MagicMock()
    user.id = uuid4()
    user.username = "admin_test"
    user.role = "admin"
    user.is_superuser = True
    user.is_active = True
    return user


def _mock_regular_user():
    user = MagicMock()
    user.id = uuid4()
    user.username = "regular_test"
    user.role = "user"
    user.is_superuser = False
    user.is_service_account = False
    user.is_active = True
    return user


def _mock_db_session(run_exists: bool = True):
    mock_db = AsyncMock()
    run_result = MagicMock()
    if run_exists:
        run = MagicMock()
        run.id = uuid4()
        run.deleted_at = None
        run_result.scalar_one_or_none.return_value = run
    else:
        run_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=run_result)
    return mock_db


@pytest.fixture
def override_deps():
    original_overrides = app.dependency_overrides.copy()
    yield app.dependency_overrides
    app.dependency_overrides = original_overrides


@pytest.mark.unit
class TestDetailedAnalysisEndpointAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v2/simulations/{uuid4()}/analysis/detailed")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, override_deps):
        regular_user = _mock_regular_user()
        mock_db = _mock_db_session(run_exists=True)

        override_deps[get_current_user_or_api_key] = lambda: regular_user
        override_deps[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v2/simulations/{uuid4()}/analysis/detailed")
            assert response.status_code == 403


@pytest.mark.unit
class TestDetailedAnalysisEndpointNotFound:
    @pytest.mark.asyncio
    async def test_nonexistent_simulation_returns_404(self, override_deps):
        admin_user = _mock_admin_user()
        mock_db = _mock_db_session(run_exists=False)

        override_deps[get_current_user_or_api_key] = lambda: admin_user
        override_deps[get_db] = lambda: mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v2/simulations/{uuid4()}/analysis/detailed")
            assert response.status_code == 404
            data = response.json()
            assert data["errors"][0]["title"] == "Not Found"


@pytest.mark.unit
class TestDetailedAnalysisEndpointHappyPath:
    @pytest.mark.asyncio
    async def test_empty_simulation_returns_empty_data(self, override_deps):
        admin_user = _mock_admin_user()
        mock_db = _mock_db_session(run_exists=True)

        override_deps[get_current_user_or_api_key] = lambda: admin_user
        override_deps[get_db] = lambda: mock_db

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.compute_detailed_notes",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
            patch(
                "src.simulation.simulations_jsonapi_router.compute_request_variance",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/v2/simulations/{uuid4()}/analysis/detailed")

            assert response.status_code == 200
            data = response.json()
            assert data["jsonapi"]["version"] == "1.1"
            assert data["data"] == []
            assert data["meta"]["count"] == 0
            assert data["meta"]["request_variance"]["total_requests"] == 0

    @pytest.mark.asyncio
    async def test_returns_notes_with_variance_meta(self, override_deps):
        admin_user = _mock_admin_user()
        mock_db = _mock_db_session(run_exists=True)

        override_deps[get_current_user_or_api_key] = lambda: admin_user
        override_deps[get_db] = lambda: mock_db

        note_data = DetailedNoteData(
            note_id="note-001",
            summary="Test note text",
            classification="NOT_MISLEADING",
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=80,
            author_agent_name="Agent Alpha",
            author_agent_instance_id="inst-001",
            request_id="req-001",
            ratings=[],
        )
        variance_data = DetailedRequestData(
            request_id="req-001",
            content="Some claim",
            content_type="text",
            note_count=1,
            variance_score=0.0,
        )

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.compute_detailed_notes",
                new_callable=AsyncMock,
                return_value=([note_data], 1),
            ),
            patch(
                "src.simulation.simulations_jsonapi_router.compute_request_variance",
                new_callable=AsyncMock,
                return_value=[variance_data],
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/v2/simulations/{uuid4()}/analysis/detailed")

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["type"] == "simulation-detailed-notes"
            assert data["data"][0]["id"] == "note-001"
            assert data["data"][0]["attributes"]["summary"] == "Test note text"
            assert data["data"][0]["attributes"]["helpfulness_score"] == 80
            assert data["data"][0]["attributes"]["author_agent_name"] == "Agent Alpha"
            assert data["meta"]["count"] == 1
            variance = data["meta"]["request_variance"]
            assert variance["total_requests"] == 1
            assert variance["requests"][0]["request_id"] == "req-001"
            assert variance["requests"][0]["content"] == "Some claim"


@pytest.mark.unit
class TestDetailedAnalysisEndpointPagination:
    @pytest.mark.asyncio
    async def test_pagination_links_present(self, override_deps):
        admin_user = _mock_admin_user()
        mock_db = _mock_db_session(run_exists=True)

        override_deps[get_current_user_or_api_key] = lambda: admin_user
        override_deps[get_db] = lambda: mock_db

        notes = [
            DetailedNoteData(
                note_id=f"note-{i}",
                summary=f"Note {i}",
                classification="NOT_MISLEADING",
                status="NEEDS_MORE_RATINGS",
                helpfulness_score=0,
                author_agent_name="Agent",
                author_agent_instance_id="inst",
            )
            for i in range(5)
        ]

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.compute_detailed_notes",
                new_callable=AsyncMock,
                return_value=(notes, 25),
            ),
            patch(
                "src.simulation.simulations_jsonapi_router.compute_request_variance",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    f"/api/v2/simulations/{uuid4()}/analysis/detailed",
                    params={"page[number]": 1, "page[size]": 5},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["links"] is not None
            assert data["links"]["self"] is not None
            assert data["links"]["first"] is not None
            assert data["links"]["last"] is not None
            assert data["links"]["next"] is not None
            assert data["meta"]["count"] == 25

    @pytest.mark.asyncio
    async def test_last_page_has_no_next_link(self, override_deps):
        admin_user = _mock_admin_user()
        mock_db = _mock_db_session(run_exists=True)

        override_deps[get_current_user_or_api_key] = lambda: admin_user
        override_deps[get_db] = lambda: mock_db

        notes = [
            DetailedNoteData(
                note_id="note-last",
                summary="Last note",
                classification="NOT_MISLEADING",
                status="NEEDS_MORE_RATINGS",
                helpfulness_score=0,
                author_agent_name="Agent",
                author_agent_instance_id="inst",
            )
        ]

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.compute_detailed_notes",
                new_callable=AsyncMock,
                return_value=(notes, 3),
            ),
            patch(
                "src.simulation.simulations_jsonapi_router.compute_request_variance",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    f"/api/v2/simulations/{uuid4()}/analysis/detailed",
                    params={"page[number]": 1, "page[size]": 20},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["links"]["next"] is None
