from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.unit
class TestDispatchAgentTurnGenerationWorkflowId:
    @pytest.mark.asyncio
    async def test_dispatch_includes_generation_in_workflow_id(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import dispatch_agent_turn

        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = "test-wf"

        agent_id = uuid4()
        captured_wf_ids: list[str] = []
        captured_dedup_ids: list[str] = []

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.simulation_turn_queue"
            ) as mock_queue,
            patch(
                "dbos.SetWorkflowID",
                side_effect=lambda wf_id: captured_wf_ids.append(wf_id) or MagicMock(),
            ),
            patch(
                "dbos.SetEnqueueOptions",
                side_effect=lambda deduplication_id: captured_dedup_ids.append(deduplication_id)
                or MagicMock(),
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            mock_queue.enqueue.return_value = mock_handle
            await dispatch_agent_turn(agent_id, 5, generation=3)

        expected_id = f"turn-{agent_id}-gen3-5-retry0"
        assert captured_wf_ids[0] == expected_id
        assert captured_dedup_ids[0] == expected_id

    @pytest.mark.asyncio
    async def test_dispatch_default_generation_is_1(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import dispatch_agent_turn

        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = "test-wf"

        agent_id = uuid4()
        captured_wf_ids: list[str] = []

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.simulation_turn_queue"
            ) as mock_queue,
            patch(
                "dbos.SetWorkflowID",
                side_effect=lambda wf_id: captured_wf_ids.append(wf_id) or MagicMock(),
            ),
            patch(
                "dbos.SetEnqueueOptions",
                side_effect=lambda **kw: MagicMock(),
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            mock_queue.enqueue.return_value = mock_handle
            await dispatch_agent_turn(agent_id, 2)

        expected_id = f"turn-{agent_id}-gen1-2-retry0"
        assert captured_wf_ids[0] == expected_id

    @pytest.mark.asyncio
    async def test_dispatch_different_generations_produce_different_ids(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import dispatch_agent_turn

        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = "test-wf"

        agent_id = uuid4()
        captured_wf_ids: list[str] = []

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.simulation_turn_queue"
            ) as mock_queue,
            patch(
                "dbos.SetWorkflowID",
                side_effect=lambda wf_id: captured_wf_ids.append(wf_id) or MagicMock(),
            ),
            patch(
                "dbos.SetEnqueueOptions",
                side_effect=lambda **kw: MagicMock(),
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            mock_queue.enqueue.return_value = mock_handle
            await dispatch_agent_turn(agent_id, 1, generation=1)
            await dispatch_agent_turn(agent_id, 1, generation=2)

        assert captured_wf_ids[0] != captured_wf_ids[1]
        assert "gen1" in captured_wf_ids[0]
        assert "gen2" in captured_wf_ids[1]


@pytest.mark.unit
class TestDetectStuckAgentsGenerationWorkflowId:
    def _run_detect_stuck(self, agent_id, turn_count, retry_count, generation):
        import asyncio

        from src.simulation.workflows.orchestrator_workflow import detect_stuck_agents_step

        def _run_coro(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        run_id = str(uuid4())

        mock_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.all.return_value = [(agent_id, turn_count, retry_count)]
        mock_session.execute = AsyncMock(return_value=agents_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.run_sync",
                side_effect=_run_coro,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=lambda: mock_session_ctx,
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.get_workflow_status.return_value = None
            detect_stuck_agents_step.__wrapped__(run_id, generation=generation)

        return mock_dbos

    def test_detect_stuck_uses_generation_in_workflow_id(self) -> None:
        agent_id = uuid4()
        mock_dbos = self._run_detect_stuck(agent_id, 3, 1, generation=2)
        mock_dbos.get_workflow_status.assert_called_once_with(f"turn-{agent_id}-gen2-4-retry1")

    def test_detect_stuck_default_generation_is_1(self) -> None:
        agent_id = uuid4()
        mock_dbos = self._run_detect_stuck(agent_id, 0, 0, generation=1)
        mock_dbos.get_workflow_status.assert_called_once_with(f"turn-{agent_id}-gen1-1-retry0")


@pytest.mark.unit
class TestInitializeRunStepIncludesGeneration:
    def test_initialize_run_returns_generation_in_config(self) -> None:
        import asyncio

        from src.simulation.workflows.orchestrator_workflow import initialize_run_step

        def _run_coro(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        run_id = uuid4()
        cs_id = uuid4()

        mock_orchestrator = MagicMock()
        mock_orchestrator.turn_cadence_seconds = 30
        mock_orchestrator.max_active_agents = 10
        mock_orchestrator.removal_rate = 0.1
        mock_orchestrator.max_turns_per_agent = 50
        mock_orchestrator.agent_profile_ids = [str(uuid4())]

        mock_run = MagicMock()
        mock_run.community_server_id = cs_id
        mock_run.orchestrator = mock_orchestrator
        mock_run.generation = 5

        update_result = MagicMock()
        update_result.scalar_one_or_none.return_value = run_id

        run_result = MagicMock()
        run_result.scalar_one.return_value = mock_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[update_result, run_result])
        mock_session.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.run_sync",
                side_effect=_run_coro,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=lambda: mock_session_ctx,
            ),
        ):
            config = initialize_run_step.__wrapped__(str(run_id))

        assert config["generation"] == 5


@pytest.mark.unit
class TestRefreshConfigStepIncludesGeneration:
    def test_refresh_config_returns_generation_in_config(self) -> None:
        import asyncio

        from src.simulation.workflows.orchestrator_workflow import refresh_config_step

        def _run_coro(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        run_id = uuid4()
        cs_id = uuid4()

        mock_orchestrator = MagicMock()
        mock_orchestrator.turn_cadence_seconds = 15
        mock_orchestrator.max_active_agents = 8
        mock_orchestrator.removal_rate = 0.2
        mock_orchestrator.max_turns_per_agent = 25
        mock_orchestrator.agent_profile_ids = [str(uuid4())]

        mock_run = MagicMock()
        mock_run.community_server_id = cs_id
        mock_run.orchestrator = mock_orchestrator
        mock_run.generation = 3

        run_result = MagicMock()
        run_result.scalar_one.return_value = mock_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=run_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.run_sync",
                side_effect=_run_coro,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=lambda: mock_session_ctx,
            ),
        ):
            config = refresh_config_step.__wrapped__(str(run_id))

        assert config["generation"] == 3


@pytest.mark.unit
class TestScheduleTurnsPassesGeneration:
    def test_schedule_turns_passes_generation_to_dispatch(self) -> None:
        import asyncio

        from src.simulation.workflows.orchestrator_workflow import schedule_turns_step

        def _run_coro(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        config = {
            "turn_cadence_seconds": 10,
            "max_active_agents": 5,
            "removal_rate": 0.0,
            "max_turns_per_agent": 100,
            "agent_profile_ids": [str(uuid4())],
            "community_server_id": str(uuid4()),
            "generation": 4,
        }

        instance_id = uuid4()

        mock_session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [(instance_id, 2, 0)]
        mock_session.execute = AsyncMock(return_value=query_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_dispatch = AsyncMock(return_value="wf-id")

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.run_sync",
                side_effect=_run_coro,
            ),
            patch(
                "src.database.get_session_maker",
                return_value=lambda: mock_session_ctx,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.dispatch_agent_turn",
                mock_dispatch,
            ),
        ):
            schedule_turns_step(str(uuid4()), config)

        mock_dispatch.assert_awaited_once_with(instance_id, 3, 0, generation=4)
