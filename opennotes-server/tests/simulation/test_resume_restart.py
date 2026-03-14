from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pendulum
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

        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(run["id"], state="completed", turn_count=15)

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(
            run["id"],
            state="completed",
            turn_count=15,
            cumulative_turn_count=30,
        )

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(run["id"], state="completed", turn_count=10)

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed")
        removed_agent = await agent_instance_factory(
            run["id"], state="removed", turn_count=5, removal_reason="max_retries_exceeded"
        )
        active_agent = await agent_instance_factory(run["id"], state="completed", turn_count=10)

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed", restart_count=2)

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
                "src.simulation.simulations_jsonapi_router.DBOS",
            ) as mock_dbos,
            patch(
                "src.simulation.simulations_jsonapi_router.snapshot_restart_state",
                new_callable=AsyncMock,
            ) as mock_snapshot,
        ):
            mock_dbos.list_workflows.return_value = []
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

        run = await simulation_run_factory("completed", cumulative_turns=50)
        await agent_instance_factory(run["id"], state="completed", turn_count=10)
        await agent_instance_factory(run["id"], state="completed", turn_count=5)

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_increments_generation(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("completed", generation=3)

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
            assert sim_run.generation == 4

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_sets_current_config_id(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("completed")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
            assert sim_run.current_config_id is not None

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_clears_completed_at(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("completed")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
            assert sim_run.completed_at is None

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_from_paused_succeeds(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("paused")
        agent = await agent_instance_factory(run["id"], state="paused", turn_count=8)

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run["id"])
            )
            sim_run = result.scalar_one()
            assert sim_run.restart_count == 1
            assert sim_run.generation == 2
            assert sim_run.current_config_id is not None

            agent_result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agent["id"])
            )
            inst = agent_result.scalar_one()
            assert inst.turn_count == 0
            assert inst.state == "active"
            assert inst.cumulative_turn_count == 8

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_from_failed_succeeds(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("failed")
        agent = await agent_instance_factory(run["id"], state="active", turn_count=12)

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
        data = response.json()
        assert data["data"]["attributes"]["status"] == "running"

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run["id"])
            )
            sim_run = result.scalar_one()
            assert sim_run.restart_count == 1
            assert sim_run.generation == 2
            assert sim_run.current_config_id is not None
            assert sim_run.completed_at is None
            assert sim_run.error_message is None

            agent_result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agent["id"])
            )
            inst = agent_result.scalar_one()
            assert inst.turn_count == 0
            assert inst.state == "active"

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_double_restart_accumulates_across_segments(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(
            run["id"], state="completed", turn_count=10, cumulative_turn_count=0
        )

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
            response1 = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response1.status_code == 200

        from src.database import get_session_maker

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run["id"])
            )
            sim_run = result.scalar_one()
            assert sim_run.restart_count == 1
            assert sim_run.cumulative_turns == 10
            assert sim_run.generation == 2

            agent_result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agent["id"])
            )
            inst = agent_result.scalar_one()
            assert inst.turn_count == 0
            assert inst.cumulative_turn_count == 10

        async with get_session_maker()() as session:
            from sqlalchemy import update as sa_update

            await session.execute(
                sa_update(SimAgentInstance)
                .where(SimAgentInstance.id == agent["id"])
                .values(turn_count=20, state="completed")
            )
            await session.execute(
                sa_update(SimulationRun)
                .where(SimulationRun.id == run["id"])
                .values(
                    status="completed",
                    completed_at=pendulum.now("UTC"),
                )
            )
            await session.commit()

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
            response2 = await admin_auth_client.post(
                f"/api/v2/simulations/{run['id']}/resume",
                json={
                    "data": {
                        "type": "simulations",
                        "attributes": {"reset_turns": True},
                    }
                },
            )

        assert response2.status_code == 200

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == run["id"])
            )
            sim_run = result.scalar_one()
            assert sim_run.restart_count == 2
            assert sim_run.cumulative_turns == 30
            assert sim_run.generation == 3
            assert sim_run.completed_at is None

            agent_result = await session.execute(
                select(SimAgentInstance).where(SimAgentInstance.id == agent["id"])
            )
            inst = agent_result.scalar_one()
            assert inst.turn_count == 0
            assert inst.cumulative_turn_count == 30
            assert inst.state == "active"

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_restart_reactivates_removal_rate_agents(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(
            run["id"], state="removed", turn_count=5, removal_reason="removal_rate"
        )

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
    async def test_restart_reactivates_simulation_completed_agents(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(
            run["id"], state="removed", turn_count=5, removal_reason="simulation_completed"
        )

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
    async def test_restart_keeps_max_retries_exceeded_removed(
        self,
        mock_dispatch,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
    ):
        mock_dispatch.return_value = "wf-restart"

        run = await simulation_run_factory("completed")
        agent = await agent_instance_factory(
            run["id"], state="removed", turn_count=5, removal_reason="max_retries_exceeded"
        )

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.return_value = []
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
            assert inst.state == "removed"


class TestResumeTimeout:
    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_resume_dbos_timeout_returns_503(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("paused")

        with patch(
            "src.simulation.simulations_jsonapi_router.DBOS",
        ) as mock_dbos:
            mock_dbos.list_workflows.side_effect = TimeoutError("simulated DBOS timeout")
            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 503
        data = response.json()
        assert "errors" in data


class TestResumeAppVersionMismatch:
    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_orphaned_workflows_trigger_redispatch(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-resume"
        run = await simulation_run_factory("paused")

        orphaned_wf = SimpleNamespace(
            workflow_id="orchestrator-old-123",
            app_version="old-deploy-abc",
        )

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.DBOS",
            ) as mock_dbos,
            patch(
                "src.simulation.simulations_jsonapi_router.GlobalParams",
            ) as mock_gp,
        ):
            mock_dbos.list_workflows.return_value = [orphaned_wf]
            mock_dbos.cancel_workflow = MagicMock()
            mock_gp.app_version = "new-deploy-xyz"

            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        mock_dispatch.assert_called_once()
        mock_dbos.cancel_workflow.assert_called_once_with("orchestrator-old-123")

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_matching_app_version_skips_redispatch(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        run = await simulation_run_factory("paused")

        current_wf = SimpleNamespace(
            workflow_id="orchestrator-current-456",
            app_version="current-deploy",
        )

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.DBOS",
            ) as mock_dbos,
            patch(
                "src.simulation.simulations_jsonapi_router.GlobalParams",
            ) as mock_gp,
        ):
            mock_dbos.list_workflows.return_value = [current_wf]
            mock_gp.app_version = "current-deploy"

            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "src.simulation.simulations_jsonapi_router.dispatch_orchestrator",
        new_callable=AsyncMock,
    )
    async def test_mixed_versions_cancels_only_orphaned(
        self, mock_dispatch, admin_auth_client, simulation_run_factory
    ):
        mock_dispatch.return_value = "wf-resume"
        run = await simulation_run_factory("paused")

        orphaned_wf = SimpleNamespace(
            workflow_id="orchestrator-old",
            app_version="old-version",
        )
        current_wf = SimpleNamespace(
            workflow_id="orchestrator-current",
            app_version="current-version",
        )

        with (
            patch(
                "src.simulation.simulations_jsonapi_router.DBOS",
            ) as mock_dbos,
            patch(
                "src.simulation.simulations_jsonapi_router.GlobalParams",
            ) as mock_gp,
        ):
            mock_dbos.list_workflows.return_value = [orphaned_wf, current_wf]
            mock_dbos.cancel_workflow = MagicMock()
            mock_gp.app_version = "current-version"

            response = await admin_auth_client.post(f"/api/v2/simulations/{run['id']}/resume")

        assert response.status_code == 200
        mock_dispatch.assert_not_called()
        mock_dbos.cancel_workflow.assert_called_once_with("orchestrator-old")
