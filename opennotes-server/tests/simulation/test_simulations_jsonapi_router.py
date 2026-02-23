from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.main import app


@pytest.fixture
async def sim_test_user():
    return {
        "username": f"sim_user_{uuid4().hex[:8]}",
        "email": f"sim_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Simulation Test User",
    }


@pytest.fixture
async def sim_registered_user(sim_test_user):
    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=sim_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == sim_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"sim_discord_{uuid4().hex[:8]}"
            user.is_superuser = True

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
async def sim_auth_headers(sim_registered_user):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(sim_registered_user["id"]),
        "username": sim_registered_user["username"],
        "role": sim_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def sim_auth_client(sim_auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(sim_auth_headers)
        yield client


@pytest.fixture
async def playground_community():
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    unique = uuid4().hex[:8]
    async with get_session_maker()() as session:
        cs = CommunityServer(
            platform="playground",
            platform_community_server_id=f"playground-{unique}",
            name=f"Test Playground {unique}",
            is_active=True,
            is_public=True,
        )
        session.add(cs)
        await session.commit()
        await session.refresh(cs)
        return {"id": cs.id, "name": cs.name}


@pytest.fixture
async def non_playground_community():
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    unique = uuid4().hex[:8]
    async with get_session_maker()() as session:
        cs = CommunityServer(
            platform="discord",
            platform_community_server_id=f"discord-{unique}",
            name=f"Test Discord {unique}",
            is_active=True,
            is_public=True,
        )
        session.add(cs)
        await session.commit()
        await session.refresh(cs)
        return {"id": cs.id, "name": cs.name}


@pytest.fixture
async def orchestrator():
    from src.database import get_session_maker
    from src.simulation.models import SimulationOrchestrator

    unique = uuid4().hex[:8]
    async with get_session_maker()() as session:
        orch = SimulationOrchestrator(
            name=f"TestOrch_{unique}",
            turn_cadence_seconds=60,
            max_agents=10,
            removal_rate=0.1,
            max_turns_per_agent=100,
            agent_profile_ids=[],
        )
        session.add(orch)
        await session.commit()
        await session.refresh(orch)
        return {"id": orch.id, "name": orch.name}


@pytest.fixture
async def simulation_run_factory(playground_community, orchestrator):
    from src.database import get_session_maker
    from src.simulation.models import SimulationRun

    async def _create(status_val: str = "pending") -> dict:
        async with get_session_maker()() as session:
            run = SimulationRun(
                orchestrator_id=orchestrator["id"],
                community_server_id=playground_community["id"],
                status=status_val,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return {"id": run.id, "status": run.status}

    return _create


class TestCreateSimulation:
    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_create_simulation_returns_201(
        self, mock_dispatch, sim_auth_client, playground_community, orchestrator
    ):
        mock_dispatch.return_value = "wf-123"

        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {
                    "orchestrator_id": str(orchestrator["id"]),
                    "community_server_id": str(playground_community["id"]),
                },
            }
        }

        response = await sim_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "simulations"
        assert isinstance(data["data"]["id"], str)
        assert data["data"]["attributes"]["status"] == "pending"
        assert data["data"]["attributes"]["orchestrator_id"] == str(orchestrator["id"])
        assert data["data"]["attributes"]["community_server_id"] == str(playground_community["id"])

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_simulation_validates_playground_community(
        self, sim_auth_client, non_playground_community, orchestrator
    ):
        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {
                    "orchestrator_id": str(orchestrator["id"]),
                    "community_server_id": str(non_playground_community["id"]),
                },
            }
        }

        response = await sim_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 422
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_create_simulation_validates_orchestrator_exists(
        self, sim_auth_client, playground_community
    ):
        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {
                    "orchestrator_id": str(uuid4()),
                    "community_server_id": str(playground_community["id"]),
                },
            }
        }

        response = await sim_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_create_simulation_dispatches_workflow(
        self, mock_dispatch, sim_auth_client, playground_community, orchestrator
    ):
        mock_dispatch.return_value = "wf-456"

        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {
                    "orchestrator_id": str(orchestrator["id"]),
                    "community_server_id": str(playground_community["id"]),
                },
            }
        }

        response = await sim_auth_client.post("/api/v2/simulations", json=request_body)
        assert response.status_code == 201

        mock_dispatch.assert_called_once()
        call_args = mock_dispatch.call_args
        assert isinstance(call_args[0][0], UUID)

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DBOS unavailable"),
    )
    async def test_create_simulation_dispatch_failure_sets_failed(
        self, mock_dispatch, sim_auth_client, playground_community, orchestrator
    ):
        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {
                    "orchestrator_id": str(orchestrator["id"]),
                    "community_server_id": str(playground_community["id"]),
                },
            }
        }

        response = await sim_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 500
        data = response.json()
        assert data["data"]["attributes"]["status"] == "failed"
        assert data["data"]["attributes"]["error_message"] is not None


class TestGetSimulation:
    @pytest.mark.asyncio
    async def test_get_simulation_returns_status_and_metrics(
        self, sim_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("pending")

        response = await sim_auth_client.get(f"/api/v2/simulations/{run['id']}")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "simulations"
        assert data["data"]["id"] == str(run["id"])
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["status"] == "pending"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_simulation_not_found(self, sim_auth_client):
        fake_id = str(uuid4())

        response = await sim_auth_client.get(f"/api/v2/simulations/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_get_soft_deleted_simulation_returns_404(
        self, sim_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("pending")

        from src.database import get_session_maker
        from src.simulation.models import SimulationRun

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run["id"])
            )
            sim_run = result.scalar_one()
            sim_run.soft_delete()
            await session.commit()

        response = await sim_auth_client.get(f"/api/v2/simulations/{run['id']}")
        assert response.status_code == 404


class TestListSimulations:
    @pytest.mark.asyncio
    async def test_list_simulations_with_pagination(self, sim_auth_client, simulation_run_factory):
        await simulation_run_factory("pending")
        await simulation_run_factory("running")

        response = await sim_auth_client.get("/api/v2/simulations?page[number]=1&page[size]=5")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 2
        assert "links" in data
        assert "meta" in data
        assert "count" in data["meta"]

    @pytest.mark.asyncio
    async def test_list_simulations_empty(self, sim_auth_client):
        response = await sim_auth_client.get("/api/v2/simulations")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "jsonapi" in data
        assert data["jsonapi"].get("version") == "1.1"

    @pytest.mark.asyncio
    async def test_list_simulations_excludes_soft_deleted(
        self, sim_auth_client, simulation_run_factory
    ):
        run_visible = await simulation_run_factory("pending")
        run_deleted = await simulation_run_factory("running")

        from src.database import get_session_maker
        from src.simulation.models import SimulationRun

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run_deleted["id"])
            )
            sim_run = result.scalar_one()
            sim_run.soft_delete()
            await session.commit()

        response = await sim_auth_client.get("/api/v2/simulations")
        assert response.status_code == 200
        data = response.json()
        returned_ids = {item["id"] for item in data["data"]}
        assert str(run_visible["id"]) in returned_ids
        assert str(run_deleted["id"]) not in returned_ids


class TestPauseSimulation:
    @pytest.mark.asyncio
    async def test_pause_running_simulation(self, sim_auth_client, simulation_run_factory):
        run = await simulation_run_factory("running")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/pause")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["attributes"]["status"] == "paused"
        assert data["data"]["attributes"]["paused_at"] is not None

    @pytest.mark.asyncio
    async def test_pause_non_running_returns_409(self, sim_auth_client, simulation_run_factory):
        run = await simulation_run_factory("pending")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/pause")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_pause_not_found(self, sim_auth_client):
        fake_id = str(uuid4())

        response = await sim_auth_client.post(f"/api/v2/simulations/{fake_id}/pause")

        assert response.status_code == 404


class TestResumeSimulation:
    @pytest.mark.asyncio
    async def test_resume_paused_simulation(self, sim_auth_client, simulation_run_factory):
        run = await simulation_run_factory("paused")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_resume_non_paused_returns_409(self, sim_auth_client, simulation_run_factory):
        run = await simulation_run_factory("running")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_resume_not_found(self, sim_auth_client):
        fake_id = str(uuid4())

        response = await sim_auth_client.post(f"/api/v2/simulations/{fake_id}/resume")

        assert response.status_code == 404


class TestCancelSimulation:
    @pytest.mark.asyncio
    async def test_cancel_running_simulation(self, sim_auth_client, simulation_run_factory):
        run = await simulation_run_factory("running")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["attributes"]["status"] == "cancelled"
        assert data["data"]["attributes"]["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_cancel_pending_simulation(self, sim_auth_client, simulation_run_factory):
        run = await simulation_run_factory("pending")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_paused_simulation(self, sim_auth_client, simulation_run_factory):
        run = await simulation_run_factory("paused")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_already_completed_returns_409(
        self, sim_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("completed")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_returns_409(
        self, sim_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("cancelled")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_cancel_failed_returns_409(self, sim_auth_client, simulation_run_factory):
        run = await simulation_run_factory("failed")

        response = await sim_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, sim_auth_client):
        fake_id = str(uuid4())

        response = await sim_auth_client.post(f"/api/v2/simulations/{fake_id}/cancel")

        assert response.status_code == 404
