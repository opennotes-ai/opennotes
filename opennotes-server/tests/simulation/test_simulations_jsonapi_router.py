from __future__ import annotations

import json
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
            max_active_agents=10,
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

    @pytest.mark.asyncio
    async def test_cancel_workflows_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v2/simulations/{uuid4()}/cancel-workflows")
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

    @pytest.mark.asyncio
    async def test_get_simulation_returns_raw_non_sensitive_error_for_admin(
        self,
        admin_auth_client,
        simulation_run_factory,
    ):
        from src.database import get_session_maker
        from src.simulation.models import SimulationRun

        run = await simulation_run_factory("failed")
        raw_error = "different failure"

        async with get_session_maker()() as session:
            await session.execute(
                update(SimulationRun)
                .where(SimulationRun.id == run["id"])
                .values(error_message=raw_error)
            )
            await session.commit()

        response = await admin_auth_client.get(f"/api/v2/simulations/{run['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["error_message"] == raw_error

    @pytest.mark.asyncio
    async def test_get_simulation_direct_call_uses_unsanitized_resource_for_admin(self):
        from starlette.requests import Request

        from src.simulation.simulations_jsonapi_router import get_simulation

        run = MagicMock()
        run.id = uuid4()
        run.status = "failed"
        run.error_message = "different failure"
        run.metrics = {}
        run.cumulative_turns = 0
        run.restart_count = 0
        run.is_public = False
        run.orchestrator_id = uuid4()
        run.community_server_id = uuid4()
        run.started_at = None
        run.completed_at = None
        run.paused_at = None
        run.created_at = None
        run.updated_at = None
        run.generation = 1
        run.current_config_id = None
        run.config_snapshot = None

        result = MagicMock()
        result.scalar_one_or_none.return_value = run
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": f"/api/v2/simulations/{run.id}",
                "headers": [],
                "query_string": b"",
                "scheme": "http",
                "server": ("test", 80),
                "client": ("testclient", 1234),
            }
        )

        with patch(
            "src.simulation.simulations_jsonapi_router.require_scope_or_admin",
            return_value=False,
        ):
            response = await get_simulation(run.id, request, db, MagicMock())

        payload = json.loads(response.body)
        assert payload["data"]["attributes"]["error_message"] == "different failure"


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

    @pytest.mark.asyncio
    async def test_pause_cancels_turn_workflows(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        inst1 = await agent_instance_factory(run["id"])
        inst2 = await agent_instance_factory(run["id"])

        mock_wf1 = MagicMock()
        mock_wf1.workflow_id = f"turn-{inst1['id']}-1"
        mock_wf2 = MagicMock()
        mock_wf2.workflow_id = f"turn-{inst2['id']}-1"

        def _list_workflows(**kwargs):
            prefix = kwargs.get("workflow_id_prefix", "")
            if str(inst1["id"]) in prefix:
                return [mock_wf1]
            if str(inst2["id"]) in prefix:
                return [mock_wf2]
            return []

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = _list_workflows
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "paused"

        cancelled_ids = [call.args[0] for call in mock_dbos.cancel_workflow.call_args_list]
        assert mock_wf1.workflow_id in cancelled_ids
        assert mock_wf2.workflow_id in cancelled_ids

    @pytest.mark.asyncio
    async def test_pause_succeeds_when_dbos_cascade_fails(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        await agent_instance_factory(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = RuntimeError("DBOS unavailable")
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "paused"


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

        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("failed")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
        mock_active_wf = MagicMock()

        run = await simulation_run_factory("paused")

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.DBOS",
            ) as mock_dbos,
            patch(
                "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
                new_callable=AsyncMock,
            ) as mock_dispatch,
        ):
            mock_dbos.list_workflows.return_value = [mock_active_wf]
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

        run = await simulation_run_factory("pending")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_pending_skips_dispatch_when_workflow_active(
        self, admin_auth_client, simulation_run_factory
    ):
        mock_active_wf = MagicMock()

        run = await simulation_run_factory("pending")

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.DBOS",
            ) as mock_dbos,
            patch(
                "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
                new_callable=AsyncMock,
            ) as mock_dispatch,
        ):
            mock_dbos.list_workflows.return_value = [mock_active_wf]
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_from_cancelled_without_reset_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("cancelled")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = RuntimeError("DBOS unavailable")
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
        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")
        await self._create_agents(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")
        agents = await self._create_agents(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")
        agents = await self._create_agents(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")
        await self._create_agents(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_restart_from_running_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("running")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
                assert inst.cumulative_turn_count == 5

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_from_cancelled_with_mixed_removal_reasons(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart-mixed"

        run = await simulation_run_factory("cancelled")
        agents = await self._create_agents(run["id"])

        from src.database import get_session_maker
        from src.simulation.models import SimAgentInstance

        async with get_session_maker()() as session:
            await session.execute(
                update(SimAgentInstance)
                .where(SimAgentInstance.id == agents[0]["id"])
                .values(state="removed", removal_reason="simulation_cancelled")
            )
            await session.execute(
                update(SimAgentInstance)
                .where(SimAgentInstance.id == agents[1]["id"])
                .values(state="removed", removal_reason="max_retries_exceeded")
            )
            await session.commit()

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json=self._restart_body(),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        mock_dispatch.assert_called_once()

        async with get_session_maker()() as session:
            result_cancelled = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agents[0]["id"])
            )
            inst_cancelled = result_cancelled.scalar_one()
            assert inst_cancelled.state == "active"
            assert inst_cancelled.removal_reason is None
            assert inst_cancelled.turn_count == 0
            assert inst_cancelled.cumulative_turn_count == 5

            result_retries = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agents[1]["id"])
            )
            inst_retries = result_retries.scalar_one()
            assert inst_retries.state == "removed"
            assert inst_retries.removal_reason == "max_retries_exceeded"
            assert inst_retries.turn_count == 5


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

    @pytest.mark.asyncio
    async def test_cancel_cancels_turn_workflows(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        inst1 = await agent_instance_factory(run["id"])
        inst2 = await agent_instance_factory(run["id"])

        mock_wf1 = MagicMock()
        mock_wf1.workflow_id = f"turn-{inst1['id']}-1"
        mock_wf2 = MagicMock()
        mock_wf2.workflow_id = f"turn-{inst2['id']}-1"

        def _list_workflows(**kwargs):
            prefix = kwargs.get("workflow_id_prefix", "")
            if str(inst1["id"]) in prefix:
                return [mock_wf1]
            if str(inst2["id"]) in prefix:
                return [mock_wf2]
            return []

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = _list_workflows
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "cancelled"

        cancelled_ids = [call.args[0] for call in mock_dbos.cancel_workflow.call_args_list]
        assert mock_wf1.workflow_id in cancelled_ids
        assert mock_wf2.workflow_id in cancelled_ids

    @pytest.mark.asyncio
    async def test_cancel_succeeds_when_dbos_cascade_fails(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        await agent_instance_factory(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = RuntimeError("DBOS unavailable")
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "cancelled"


class TestCancelWorkflows:
    @pytest.mark.asyncio
    async def test_cancel_workflows_dry_run(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        inst1 = await agent_instance_factory(run["id"])
        inst2 = await agent_instance_factory(run["id"])

        mock_wf1 = MagicMock()
        mock_wf1.workflow_id = f"turn-{inst1['id']}-gen1-1-retry0"
        mock_wf2 = MagicMock()
        mock_wf2.workflow_id = f"turn-{inst2['id']}-gen1-2-retry0"

        def _list_workflows(**kwargs):
            prefix = kwargs.get("workflow_id_prefix", "")
            if str(inst1["id"]) in prefix:
                return [mock_wf1]
            if str(inst2["id"]) in prefix:
                return [mock_wf2]
            return []

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = _list_workflows
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/cancel-workflows?dry_run=true"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert data["total"] == 2
        assert mock_wf1.workflow_id in data["workflow_ids"]
        assert mock_wf2.workflow_id in data["workflow_ids"]
        mock_dbos.cancel_workflow.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_workflows_execute(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        inst1 = await agent_instance_factory(run["id"])

        mock_wf1 = MagicMock()
        mock_wf1.workflow_id = f"turn-{inst1['id']}-gen1-1-retry0"

        def _list_workflows(**kwargs):
            prefix = kwargs.get("workflow_id_prefix", "")
            if str(inst1["id"]) in prefix:
                return [mock_wf1]
            return []

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = _list_workflows
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/cancel-workflows"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is False
        assert data["total"] == 1
        assert data["cancelled"] == 1
        assert mock_wf1.workflow_id in data["workflow_ids"]
        mock_dbos.cancel_workflow.assert_called_once_with(mock_wf1.workflow_id)

    @pytest.mark.asyncio
    async def test_cancel_workflows_with_generation_filter(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        inst1 = await agent_instance_factory(run["id"])

        mock_wf_gen2 = MagicMock()
        mock_wf_gen2.workflow_id = f"turn-{inst1['id']}-gen2-5-retry0"

        def _list_workflows(**kwargs):
            prefix = kwargs.get("workflow_id_prefix", "")
            if "gen2" in prefix:
                return [mock_wf_gen2]
            return []

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = _list_workflows
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/cancel-workflows?generation=2"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["cancelled"] == 1
        assert data["generation"] == 2

        call_args = mock_dbos.list_workflows.call_args_list
        for call in call_args:
            prefix = call.kwargs.get("workflow_id_prefix", "")
            assert "gen2" in prefix

    @pytest.mark.asyncio
    async def test_cancel_workflows_not_found(self, admin_auth_client):
        from uuid import uuid4

        fake_id = str(uuid4())

        response = await admin_auth_client.post(f"/api/v2/simulations/{fake_id}/cancel-workflows")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_workflows_dbos_unavailable(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        await agent_instance_factory(run["id"])

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = RuntimeError("DBOS unavailable")
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/cancel-workflows"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_cancel_workflows_partial_failure(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        inst1 = await agent_instance_factory(run["id"])
        inst2 = await agent_instance_factory(run["id"])

        mock_wf1 = MagicMock()
        mock_wf1.workflow_id = f"turn-{inst1['id']}-gen1-1-retry0"
        mock_wf2 = MagicMock()
        mock_wf2.workflow_id = f"turn-{inst2['id']}-gen1-2-retry0"

        def _list_workflows(**kwargs):
            prefix = kwargs.get("workflow_id_prefix", "")
            if str(inst1["id"]) in prefix:
                return [mock_wf1]
            if str(inst2["id"]) in prefix:
                return [mock_wf2]
            return []

        call_count = 0

        def _cancel_workflow(wf_id):
            nonlocal call_count
            call_count += 1
            if wf_id == mock_wf2.workflow_id:
                raise RuntimeError("DBOS cancel failed")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = _list_workflows
            mock_dbos.cancel_workflow.side_effect = _cancel_workflow
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/cancel-workflows"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["cancelled"] == 1
        assert len(data["errors"]) == 1
        assert mock_wf2.workflow_id in data["errors"][0]

    @pytest.mark.asyncio
    async def test_cancel_workflows_response_has_errors_field(
        self, admin_auth_client, simulation_run_factory, agent_instance_factory
    ):
        run = await simulation_run_factory("running")
        inst1 = await agent_instance_factory(run["id"])

        mock_wf1 = MagicMock()
        mock_wf1.workflow_id = f"turn-{inst1['id']}-gen1-1-retry0"

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = [mock_wf1]
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/cancel-workflows?dry_run=true"
            )

        assert response.status_code == 200
        data = response.json()
        assert "errors" in data
        assert data["errors"] == []

    @pytest.mark.asyncio
    async def test_cancel_workflows_no_agents_has_errors_field(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("running")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/cancel-workflows")

        assert response.status_code == 200
        data = response.json()
        assert "errors" in data
        assert data["errors"] == []


class TestPublishSimulation:
    @pytest.mark.asyncio
    async def test_publish_sets_is_public_true(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("completed")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/publish")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["data"]["attributes"]["is_public"] is True

    @pytest.mark.asyncio
    async def test_publish_already_public_is_idempotent(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("completed")

        first = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/publish")
        assert first.status_code == 200

        second = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/publish")
        assert second.status_code == 200
        assert second.json()["data"]["attributes"]["is_public"] is True

    @pytest.mark.asyncio
    async def test_publish_nonexistent_returns_404(self, admin_auth_client):
        fake_id = str(uuid4())
        response = await admin_auth_client.post(f"/api/v2/simulations/{fake_id}/publish")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_publish_deleted_sim_returns_404(self, admin_auth_client, simulation_run_factory):
        import pendulum

        from src.database import get_session_maker
        from src.simulation.models import SimulationRun

        run = await simulation_run_factory("completed")

        async with get_session_maker()() as session:
            await session.execute(
                update(SimulationRun)
                .where(SimulationRun.id == run["id"])
                .values(deleted_at=pendulum.now("UTC"))
            )
            await session.commit()

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/publish")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unpublish_sets_is_public_false(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("completed")

        await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/publish")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/unpublish")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["is_public"] is False

    @pytest.mark.asyncio
    async def test_unpublish_already_private_is_idempotent(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("completed")

        response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/unpublish")
        assert response.status_code == 200
        assert response.json()["data"]["attributes"]["is_public"] is False

    @pytest.mark.asyncio
    async def test_unpublish_nonexistent_returns_404(self, admin_auth_client):
        fake_id = str(uuid4())
        response = await admin_auth_client.post(f"/api/v2/simulations/{fake_id}/unpublish")
        assert response.status_code == 404


class TestPublishUnpublishAuth:
    @pytest.mark.asyncio
    async def test_publish_unauthenticated_returns_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v2/simulations/{uuid4()}/publish")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unpublish_unauthenticated_returns_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/v2/simulations/{uuid4()}/unpublish")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_publish_non_admin_returns_403(self):
        from src.auth.auth import create_access_token
        from src.database import get_session_maker
        from src.users.models import User

        unique = uuid4().hex[:8]
        user_data = {
            "username": f"regular_{unique}",
            "email": f"regular_{unique}@example.com",
            "password": "TestPassword123!",
            "full_name": "Regular User",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v1/auth/register", json=user_data)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == user_data["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

        token = create_access_token(
            {"sub": str(user.id), "username": user.username, "role": user.role}
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update({"Authorization": f"Bearer {token}"})
            response = await client.post(f"/api/v2/simulations/{uuid4()}/publish")
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unpublish_non_admin_returns_403(self):
        from src.auth.auth import create_access_token
        from src.database import get_session_maker
        from src.users.models import User

        unique = uuid4().hex[:8]
        user_data = {
            "username": f"regular_{unique}",
            "email": f"regular_{unique}@example.com",
            "password": "TestPassword123!",
            "full_name": "Regular User",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v1/auth/register", json=user_data)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == user_data["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

        token = create_access_token(
            {"sub": str(user.id), "username": user.username, "role": user.role}
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update({"Authorization": f"Bearer {token}"})
            response = await client.post(f"/api/v2/simulations/{uuid4()}/unpublish")
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_publish_scoped_key_without_admin_returns_403(self):
        from src.auth.models import APIKeyCreate
        from src.database import get_session_maker
        from src.users.crud import create_api_key
        from src.users.models import User

        unique = uuid4().hex[:8]
        user_data = {
            "username": f"scoped_{unique}",
            "email": f"scoped_{unique}@example.com",
            "password": "TestPassword123!",
            "full_name": "Scoped User",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v1/auth/register", json=user_data)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == user_data["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            _, raw_key = await create_api_key(
                db=session,
                user_id=user.id,
                api_key_create=APIKeyCreate(
                    name="scoped-key",
                    expires_in_days=30,
                    scopes=["simulations:read"],
                ),
            )
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update({"X-API-Key": raw_key})
            response = await client.post(f"/api/v2/simulations/{uuid4()}/publish")
            assert response.status_code == 403


class TestScopedKeyFiltering:
    def test_sanitize_public_simulation_error_message_preserves_non_sensitive_errors(self):
        from src.simulation.simulations_jsonapi_router import (
            _sanitize_public_simulation_error_message,
        )

        assert _sanitize_public_simulation_error_message("different failure") == "different failure"

    @pytest.fixture
    async def service_account_scoped_client(self):
        from src.auth.models import APIKeyCreate
        from src.database import get_session_maker
        from src.users.crud import create_api_key
        from src.users.models import User

        unique = uuid4().hex[:8]
        async with get_session_maker()() as session:
            user = User(
                username=f"svc_{unique}",
                email=f"svc_{unique}@example.com",
                hashed_password="unused-placeholder",
                is_active=True,
                is_service_account=True,
            )
            session.add(user)
            await session.flush()

            _, raw_key = await create_api_key(
                db=session,
                user_id=user.id,
                api_key_create=APIKeyCreate(
                    name="scoped-sim-key",
                    expires_in_days=30,
                    scopes=["simulations:read"],
                ),
            )
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update({"X-API-Key": raw_key})
            yield client

    @pytest.fixture
    async def wrong_scope_client(self):
        from src.auth.password import get_password_hash
        from src.database import get_session_maker
        from src.users.models import APIKey, User

        unique = uuid4().hex[:8]
        async with get_session_maker()() as session:
            user = User(
                username=f"wrong_{unique}",
                email=f"wrong_{unique}@example.com",
                hashed_password="unused-placeholder",
                is_active=True,
                is_service_account=True,
            )
            session.add(user)
            await session.flush()

            raw_key, key_prefix = APIKey.generate_key()
            api_key = APIKey(
                user_id=user.id,
                name="wrong-scope-key",
                key_prefix=key_prefix,
                key_hash=get_password_hash(raw_key),
                is_active=True,
                scopes=["notes:read"],
            )
            session.add(api_key)
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update({"X-API-Key": raw_key})
            yield client

    @pytest.mark.asyncio
    async def test_scoped_key_list_only_sees_public_sims(
        self,
        admin_auth_client,
        service_account_scoped_client,
        simulation_run_factory,
    ):
        run_public = await simulation_run_factory("completed")
        await simulation_run_factory("completed")

        await admin_auth_client.post(f"/api/v2/simulations/{run_public['id']}/publish")

        response = await service_account_scoped_client.get("/api/v2/simulations")

        assert response.status_code == 200
        data = response.json()
        returned_ids = [item["id"] for item in data["data"]]
        assert str(run_public["id"]) in returned_ids

        for item in data["data"]:
            assert item["attributes"]["is_public"] is True

    @pytest.mark.asyncio
    async def test_scoped_key_get_public_sim_succeeds(
        self,
        admin_auth_client,
        service_account_scoped_client,
        simulation_run_factory,
    ):
        run = await simulation_run_factory("completed")
        await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/publish")

        response = await service_account_scoped_client.get(f"/api/v2/simulations/{run['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["is_public"] is True

    @pytest.mark.asyncio
    async def test_scoped_key_get_public_sim_sanitizes_scoring_persistence_error(
        self,
        admin_auth_client,
        service_account_scoped_client,
        simulation_run_factory,
    ):
        from src.database import get_session_maker
        from src.simulation.models import SimulationRun

        run = await simulation_run_factory("failed")
        raw_error = "Required scoring snapshot persistence failed: bucket credentials leaked"

        async with get_session_maker()() as session:
            await session.execute(
                update(SimulationRun)
                .where(SimulationRun.id == run["id"])
                .values(error_message=raw_error)
            )
            await session.commit()

        await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/publish")

        response = await service_account_scoped_client.get(f"/api/v2/simulations/{run['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["error_message"] == (
            "Required scoring snapshot persistence failed"
        )

    @pytest.mark.asyncio
    async def test_scoped_key_list_sanitizes_scoring_persistence_error(
        self,
        admin_auth_client,
        service_account_scoped_client,
        simulation_run_factory,
    ):
        from src.database import get_session_maker
        from src.simulation.models import SimulationRun

        run = await simulation_run_factory("failed")
        raw_error = "Required scoring snapshot persistence failed: bucket credentials leaked"

        async with get_session_maker()() as session:
            await session.execute(
                update(SimulationRun)
                .where(SimulationRun.id == run["id"])
                .values(error_message=raw_error)
            )
            await session.commit()

        await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/publish")

        response = await service_account_scoped_client.get("/api/v2/simulations")

        assert response.status_code == 200
        data = response.json()
        matching = [item for item in data["data"] if item["id"] == str(run["id"])]
        assert len(matching) == 1
        assert matching[0]["attributes"]["error_message"] == (
            "Required scoring snapshot persistence failed"
        )

    @pytest.mark.asyncio
    async def test_scoped_key_get_private_sim_returns_404(
        self,
        service_account_scoped_client,
        simulation_run_factory,
    ):
        run = await simulation_run_factory("completed")

        response = await service_account_scoped_client.get(f"/api/v2/simulations/{run['id']}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_scope_key_gets_403(
        self,
        wrong_scope_client,
    ):
        response = await wrong_scope_client.get("/api/v2/simulations")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_sees_all_sims_including_private(
        self,
        admin_auth_client,
        simulation_run_factory,
    ):
        run_a = await simulation_run_factory("completed")
        run_b = await simulation_run_factory("completed")

        await admin_auth_client.post(f"/api/v2/simulations/{run_a['id']}/publish")

        response = await admin_auth_client.get("/api/v2/simulations")

        assert response.status_code == 200
        data = response.json()
        returned_ids = [item["id"] for item in data["data"]]
        assert str(run_a["id"]) in returned_ids
        assert str(run_b["id"]) in returned_ids


class TestCreateSimulationName:
    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_create_simulation_with_name(
        self, mock_dispatch, admin_auth_client, playground_community, orchestrator
    ):
        mock_dispatch.return_value = "wf-name"

        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {
                    "orchestrator_id": str(orchestrator["id"]),
                    "community_server_id": str(playground_community["id"]),
                    "name": "My Test Run",
                },
            }
        }

        response = await admin_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["attributes"]["name"] == "My Test Run"

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_create_simulation_without_name(
        self, mock_dispatch, admin_auth_client, playground_community, orchestrator
    ):
        mock_dispatch.return_value = "wf-noname"

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
        data = response.json()
        assert data["data"]["attributes"]["name"] is None

    @pytest.mark.asyncio
    async def test_create_simulation_name_too_long(
        self, admin_auth_client, playground_community, orchestrator
    ):
        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {
                    "orchestrator_id": str(orchestrator["id"]),
                    "community_server_id": str(playground_community["id"]),
                    "name": "x" * 256,
                },
            }
        }

        response = await admin_auth_client.post("/api/v2/simulations", json=request_body)

        assert response.status_code == 422


class TestUpdateSimulation:
    @pytest.mark.asyncio
    async def test_patch_simulation_name(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("pending")

        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {"name": "Updated Name"},
            }
        }

        response = await admin_auth_client.patch(
            f"/api/v2/simulations/{run['id']}", json=request_body
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_patch_simulation_clear_name(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("pending")

        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {"name": "Temp Name"},
            }
        }
        await admin_auth_client.patch(f"/api/v2/simulations/{run['id']}", json=request_body)

        request_body["data"]["attributes"]["name"] = None
        response = await admin_auth_client.patch(
            f"/api/v2/simulations/{run['id']}", json=request_body
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["name"] is None

    @pytest.mark.asyncio
    async def test_patch_simulation_empty_attributes_preserves_name(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("pending")

        set_body = {
            "data": {
                "type": "simulations",
                "attributes": {"name": "Keep Me"},
            }
        }
        await admin_auth_client.patch(f"/api/v2/simulations/{run['id']}", json=set_body)

        empty_body = {
            "data": {
                "type": "simulations",
                "attributes": {},
            }
        }
        response = await admin_auth_client.patch(
            f"/api/v2/simulations/{run['id']}", json=empty_body
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["name"] == "Keep Me"

    @pytest.mark.asyncio
    async def test_patch_simulation_not_found(self, admin_auth_client):
        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {"name": "Ghost"},
            }
        }

        response = await admin_auth_client.patch(
            f"/api/v2/simulations/{uuid4()}", json=request_body
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_simulation_name_too_long(self, admin_auth_client, simulation_run_factory):
        run = await simulation_run_factory("pending")

        request_body = {
            "data": {
                "type": "simulations",
                "attributes": {"name": "x" * 256},
            }
        }

        response = await admin_auth_client.patch(
            f"/api/v2/simulations/{run['id']}", json=request_body
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_simulation_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/simulations/{uuid4()}",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"name": "nope"},
                    }
                },
            )
            assert response.status_code == 401
