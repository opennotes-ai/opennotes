from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from src.simulation.models import SimAgentInstance, SimulationRun


class TestResumeWithoutBody:
    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_no_body_works_as_before(
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

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"
        mock_dispatch.assert_called_once()


class TestResumeWithResetTurns:
    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_from_completed_succeeds(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_resets_agent_turn_count(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(run["id"], state="completed", turn_count=15)

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response.status_code == 200

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agent["id"])
            )
            inst = result.scalar_one()
            assert inst.turn_count == 0

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_accumulates_cumulative_turn_count(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(
            run["id"],
            state="completed",
            turn_count=15,
            cumulative_turn_count=30,
        )

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response.status_code == 200

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agent["id"])
            )
            inst = result.scalar_one()
            assert inst.cumulative_turn_count == 45
            assert inst.turn_count == 0

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_reactivates_completed_agents(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(run["id"], state="completed", turn_count=10)

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response.status_code == 200

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agent["id"])
            )
            inst = result.scalar_one()
            assert inst.state == "active"

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_does_not_reactivate_removed_agents(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")
        removed_agent = await agent_instance_factory(run["id"], state="removed", turn_count=5)
        active_agent = await agent_instance_factory(run["id"], state="completed", turn_count=10)

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response.status_code == 200

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            removed_result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == removed_agent["id"])
            )
            removed_inst = removed_result.scalar_one()
            assert removed_inst.state == "removed"

            active_result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == active_agent["id"])
            )
            active_inst = active_result.scalar_one()
            assert active_inst.state == "active"

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_increments_restart_count(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed", restart_count=2)

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response.status_code == 200

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run["id"])
            )
            sim_run = result.scalar_one()
            assert sim_run.restart_count == 3

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_calls_snapshot_restart_state(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed")

        from src.database import get_session_maker
        from src.simulation.models import SimulationRunConfig
        from src.simulation.restart import RestartSnapshot

        async with get_session_maker()() as session:
            config = SimulationRunConfig(
                simulation_run_id=run["id"],
                restart_number=0,
                max_turns_per_agent=100,
                turn_cadence_seconds=60,
                max_agents=10,
                removal_rate=0.1,
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            config_id = config.id

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.get_dbos_client",
                return_value=mock_client,
            ),
            patch(
                "src.simulation.simulations_jsonapi_router.snapshot_restart_state",
                new_callable=AsyncMock,
            ) as mock_snapshot,
        ):
            mock_snapshot.return_value = RestartSnapshot(config_id=config_id, log_ids=[])
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response.status_code == 200
        mock_snapshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_restart_from_running_returns_409(
        self, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("running")

        response = await admin_auth_client.post(
            f"/api/v2/simulations/{run['id']}/resume",
            json={
                "data": {
                    "type": "simulations",
                    "attributes": {"reset_turns": True},
                }
            },
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_accumulates_cumulative_turns_on_run(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"
        mock_client = MagicMock()
        mock_client.list_workflows.return_value = []

        run = await simulation_run_factory("completed", cumulative_turns=50)
        await agent_instance_factory(run["id"], state="completed", turn_count=10)
        await agent_instance_factory(run["id"], state="completed", turn_count=5)

        with patch(
            "src.simulation.simulations_jsonapi_router.get_dbos_client",
            return_value=mock_client,
        ):
            response = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response.status_code == 200

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run["id"])
            )
            sim_run = result.scalar_one()
            assert sim_run.cumulative_turns == 65
