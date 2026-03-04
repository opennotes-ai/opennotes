from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from src.main import app


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


class TestSimulationsUnauthenticated:
    @pytest.mark.asyncio
    async def test_create_simulation_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = {
                "data": {
                    "type": "simulations",
                    "attributes": {
                        "orchestrator_id": str(uuid4()),
                        "community_server_id": str(uuid4()),
                    },
                }
            }
            response = await client.post("/api/v2/simulations", json=request_body)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_simulation_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v2/simulations/{uuid4()}")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_simulations_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/simulations")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_pause_simulation_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v2/simulations/{uuid4()}/pause")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_resume_simulation_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v2/simulations/{uuid4()}/resume")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_simulation_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v2/simulations/{uuid4()}/cancel")
            assert response.status_code == 401


class TestCreateSimulation:
    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_create_simulation_returns_201(
        self, mock_dispatch, admin_auth_client, playground_community, orchestrator
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

        response = await admin_auth_client.post("/api/v2/simulations", json=request_body)

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
        self, admin_auth_client, non_playground_community, orchestrator
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

        response = await admin_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 422
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_create_simulation_validates_orchestrator_exists(
        self, admin_auth_client, playground_community
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

        response = await admin_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_create_simulation_dispatches_workflow(
        self, mock_dispatch, admin_auth_client, playground_community, orchestrator
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

        response = await admin_auth_client.post("/api/v2/simulations", json=request_body)
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
        self, mock_dispatch, admin_auth_client, playground_community, orchestrator
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

        response = await admin_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 500
        data = response.json()
        assert data["data"]["attributes"]["status"] == "failed"
        assert data["data"]["attributes"]["error_message"] is not None


class TestGetSimulation:
    @pytest.mark.asyncio
    async def test_get_simulation_returns_status_and_metrics(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("pending")

        response = await admin_auth_client.get(f"/api/v2/simulations/{run['id']}")

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
    async def test_get_simulation_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        response = await admin_auth_client.get(f"/api/v2/simulations/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_get_soft_deleted_simulation_returns_404(
        self, admin_auth_client, simulation_run_factory
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

        response = await admin_auth_client.get(f"/api/v2/simulations/{run['id']}")
        assert response.status_code == 404


class TestListSimulations:
    @pytest.mark.asyncio
    async def test_list_simulations_with_pagination(
        self, admin_auth_client, simulation_run_factory
    ):
        await simulation_run_factory("pending")
        await simulation_run_factory("running")

        response = await admin_auth_client.get("/api/v2/simulations?page[number]=1&page[size]=5")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 2
        assert "links" in data
        assert "meta" in data
        assert "count" in data["meta"]

    @pytest.mark.asyncio
    async def test_list_simulations_response_structure(self, admin_auth_client):
        response = await admin_auth_client.get("/api/v2/simulations")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "jsonapi" in data
        assert data["jsonapi"].get("version") == "1.1"

    @pytest.mark.asyncio
    async def test_list_simulations_excludes_soft_deleted(
        self, admin_auth_client, simulation_run_factory
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

        response = await admin_auth_client.get("/api/v2/simulations")
        assert response.status_code == 200
        data = response.json()
        returned_ids = {item["id"] for item in data["data"]}
        assert str(run_visible["id"]) in returned_ids
        assert str(run_deleted["id"]) not in returned_ids


class TestPauseSimulation:
    @pytest.mark.asyncio
    async def test_pause_running_simulation(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("running")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/pause")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["attributes"]["status"] == "paused"
        assert data["data"]["attributes"]["paused_at"] is not None

    @pytest.mark.asyncio
    async def test_pause_non_running_returns_409(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("pending")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/pause")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_pause_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        response = await admin_auth_client.post(f"/api/v2/simulations/{fake_id}/pause")

        assert response.status_code == 404


class TestResumeSimulation:
    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_paused_simulation(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-resume"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_from_failed_status(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-resume-failed"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("failed")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        assert data["data"]["attributes"]["error_message"] is None
        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_skips_dispatch_when_workflow_active(
        self, admin_auth_client, simulation_run_factory
    ):
        mock_client = MagicMock()
        mock_active_wf = MagicMock()
        mock_client.list_workflows.return_value = [mock_active_wf]

        run = await simulation_run_factory("paused")

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.get_dbos_client",
                return_value=mock_client,
            ),
            patch(
                "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
                new_callable=AsyncMock,
            ) as mock_dispatch,
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_from_pending_status(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-resume-pending"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("pending")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_cancelled_without_reset_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("cancelled")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_resume_from_completed_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("completed")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_resume_non_paused_returns_409(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("running")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_resume_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        response = await admin_auth_client.post(f"/api/v2/simulations/{fake_id}/resume")

        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_increments_generation(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-gen2"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        call_kwargs = mock_dispatch.call_args
        assert call_kwargs.kwargs.get("generation") == 2

    @pytest.mark.asyncio
    async def test_resume_returns_503_when_dbos_client_fails(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            side_effect=RuntimeError("DBOS unavailable"),
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 503
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
        side_effect=RuntimeError("dispatch exploded"),
    )
    async def test_resume_returns_502_when_dispatch_fails(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 502
        data = response.json()
        assert "errors" in data


class TestRestartSimulation:
    @staticmethod
    def _restart_body(reset_turns: bool = True) -> dict:
        return {
            "data": {
                "type": "simulations",
                "attributes": {"reset_turns": reset_turns},
            }
        }

    @staticmethod
    async def _create_agents(simulation_run_id: UUID, count: int = 2) -> list[dict]:
        from src.database import get_session_maker
        from src.simulation.models import SimAgent, SimAgentInstance
        from src.users.profile_models import UserProfile

        agents = []
        async with get_session_maker()() as session:
            for i in range(count):
                unique = uuid4().hex[:8]
                profile = UserProfile(
                    display_name=f"Agent Profile {unique}",
                    is_human=False,
                    is_active=True,
                )
                session.add(profile)
                await session.flush()

                sim_agent = SimAgent(
                    name=f"TestAgent_{unique}",
                    personality=f"Test personality {i}",
                    model_name="test-model",
                )
                session.add(sim_agent)
                await session.flush()

                instance = SimAgentInstance(
                    simulation_run_id=simulation_run_id,
                    agent_profile_id=sim_agent.id,
                    user_profile_id=profile.id,
                    state="active",
                    turn_count=5,
                    cumulative_turn_count=0,
                )
                session.add(instance)
                await session.flush()
                await session.refresh(instance)
                agents.append(
                    {
                        "id": instance.id,
                        "state": instance.state,
                        "turn_count": instance.turn_count,
                    }
                )

            await session.commit()
        return agents

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_completed_simulation(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        await self._create_agents(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_resets_turn_counts(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart-turns"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        agents = await self._create_agents(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 200

        from src.database import get_session_maker
        from src.simulation.models import SimAgentInstance

        async with get_session_maker()() as session:
            for agent_data in agents:
                result = await session.execute(
                    select(SimAgentInstance).where(SimAgentInstance.id == agent_data["id"])
                )
                inst = result.scalar_one()
                assert inst.turn_count == 0
                assert inst.cumulative_turn_count == 5

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_reactivates_completed_agents(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart-reactivate"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        agents = await self._create_agents(run["id"])

        from src.database import get_session_maker
        from src.simulation.models import SimAgentInstance

        async with get_session_maker()() as session:
            await session.execute(
                update(SimAgentInstance)
                .where(SimAgentInstance.id == agents[0]["id"])
                .values(state="completed")
            )
            await session.commit()

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 200

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agents[0]["id"])
            )
            inst = result.scalar_one()
            assert inst.state == "active"

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_keeps_removed_agents_removed(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart-removed"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        agents = await self._create_agents(run["id"])

        from src.database import get_session_maker
        from src.simulation.models import SimAgentInstance

        async with get_session_maker()() as session:
            await session.execute(
                update(SimAgentInstance)
                .where(SimAgentInstance.id == agents[0]["id"])
                .values(state="removed", removal_reason="test removal")
            )
            await session.commit()

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 200

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agents[0]["id"])
            )
            inst = result.scalar_one()
            assert inst.state == "removed"
            assert inst.removal_reason == "test removal"

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_creates_audit_records(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart-audit"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        agents = await self._create_agents(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 200

        from src.database import get_session_maker
        from src.simulation.models import SimAgentRunLog, SimulationRunConfig

        async with get_session_maker()() as session:
            config_result = await session.execute(
                select(SimulationRunConfig).where(
                    SimulationRunConfig.simulation_run_id == run["id"]
                )
            )
            configs = config_result.scalars().all()
            assert len(configs) == 1
            assert configs[0].restart_number == 0

            logs_result = await session.execute(
                select(SimAgentRunLog).where(SimAgentRunLog.simulation_run_id == run["id"])
            )
            logs = logs_result.scalars().all()
            assert len(logs) == len(agents)

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_increments_restart_count(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart-count"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        await self._create_agents(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 200

        from src.database import get_session_maker
        from src.simulation.models import SimulationRun

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run["id"])
            )
            sim_run = result.scalar_one()
            assert sim_run.restart_count == 1
            assert sim_run.cumulative_turns == 10

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_without_body_still_works(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-no-body"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_restart_from_running_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("running")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_resume_from_completed_without_reset_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("completed")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_from_cancelled_with_reset_turns(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart-cancelled"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("cancelled")
        agents = await self._create_agents(run["id"])

        from src.database import get_session_maker
        from src.simulation.models import SimAgentInstance

        async with get_session_maker()() as session:
            for agent_data in agents:
                await session.execute(
                    update(SimAgentInstance)
                    .where(SimAgentInstance.id == agent_data["id"])
                    .values(state="removed", removal_reason="simulation_cancelled")
                )
            await session.commit()

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        assert data["data"]["attributes"]["completed_at"] is None
        mock_dispatch.assert_called_once()

        async with get_session_maker()() as session:
            for agent_data in agents:
                result = await session.execute(
                    select(SimAgentInstance).where(SimAgentInstance.id == agent_data["id"])
                )
                inst = result.scalar_one()
                assert inst.state == "active"
                assert inst.removal_reason is None
                assert inst.turn_count == 0


class TestCancelSimulation:
    @pytest.mark.asyncio
    async def test_cancel_running_simulation(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("running")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["attributes"]["status"] == "cancelled"
        assert data["data"]["attributes"]["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_cancel_pending_simulation(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("pending")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_paused_simulation(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("paused")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_already_completed_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("completed")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("cancelled")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_cancel_failed_returns_409(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("failed")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 409
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        response = await admin_auth_client.post(f"/api/v2/simulations/{fake_id}/cancel")

        assert response.status_code == 404
