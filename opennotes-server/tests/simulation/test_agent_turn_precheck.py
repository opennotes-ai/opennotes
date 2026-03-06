from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestCheckSimulationActiveStep:
    def test_returns_true_when_running(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import check_simulation_active_step

        mock_session = AsyncMock()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = "running"
        mock_session.execute = AsyncMock(return_value=status_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
        ):
            assert check_simulation_active_step.__wrapped__(str(uuid4())) is True

    def test_returns_true_when_pending(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import check_simulation_active_step

        mock_session = AsyncMock()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = "pending"
        mock_session.execute = AsyncMock(return_value=status_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
        ):
            assert check_simulation_active_step.__wrapped__(str(uuid4())) is True

    @pytest.mark.parametrize("status", ["paused", "cancelled", "completed", "failed"])
    def test_returns_false_when_inactive(self, status: str) -> None:
        from src.simulation.workflows.agent_turn_workflow import check_simulation_active_step

        mock_session = AsyncMock()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = status
        mock_session.execute = AsyncMock(return_value=status_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
        ):
            assert check_simulation_active_step.__wrapped__(str(uuid4())) is False

    def test_returns_false_when_instance_not_found(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import check_simulation_active_step

        mock_session = AsyncMock()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=status_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
        ):
            assert check_simulation_active_step.__wrapped__(str(uuid4())) is False


class TestRunAgentTurnEarlyExit:
    def test_skips_when_simulation_inactive(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_id = str(uuid4())

        mock_gate = MagicMock()
        mock_dbos = MagicMock()
        mock_dbos.workflow_id = "wf-test-123"

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.TokenGate",
                return_value=mock_gate,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.DBOS",
                mock_dbos,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.check_simulation_active_step",
                return_value=False,
            ) as mock_check,
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
            ) as mock_load,
        ):
            result = run_agent_turn.__wrapped__(agent_id)

        mock_gate.acquire.assert_not_called()
        mock_gate.release.assert_not_called()
        mock_check.assert_called_once_with(agent_id)
        mock_load.assert_not_called()
        assert result["status"] == "skipped_inactive"
        assert result["agent_instance_id"] == agent_id

    def test_skips_when_simulation_becomes_inactive_after_acquire(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_id = str(uuid4())

        mock_gate = MagicMock()
        mock_dbos = MagicMock()
        mock_dbos.workflow_id = "wf-test-789"

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.TokenGate",
                return_value=mock_gate,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.DBOS",
                mock_dbos,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.check_simulation_active_step",
                side_effect=[True, False],
            ) as mock_check,
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
            ) as mock_load,
        ):
            result = run_agent_turn.__wrapped__(agent_id)

        assert mock_check.call_count == 2
        mock_gate.acquire.assert_called_once()
        mock_gate.release.assert_called_once()
        mock_load.assert_not_called()
        assert result["status"] == "skipped_inactive"
        assert result["agent_instance_id"] == agent_id

    def test_continues_when_simulation_active(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_id = str(uuid4())
        context = {
            "agent_instance_id": agent_id,
            "community_server_id": str(uuid4()),
            "message_history": [],
            "instance_turn_count": 0,
            "memory_compaction_strategy": "sliding_window",
            "memory_compaction_config": None,
            "memory_id": str(uuid4()),
            "simulation_run_id": str(uuid4()),
            "recent_actions": [],
        }

        mock_gate = MagicMock()
        mock_dbos = MagicMock()
        mock_dbos.workflow_id = "wf-test-456"

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.TokenGate",
                return_value=mock_gate,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.DBOS",
                mock_dbos,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.check_simulation_active_step",
                return_value=True,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.get_settings",
            ) as mock_settings,
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
                return_value=context,
            ) as mock_load,
            patch(
                "src.simulation.workflows.agent_turn_workflow.compact_memory_step",
                return_value={"messages": [], "was_compacted": False},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.build_deps_step",
                return_value={"available_requests": [], "available_notes": []},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                return_value={
                    "action_type": "pass_turn",
                    "reasoning": "nothing to do",
                    "phase1_messages": [],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={
                    "agent_instance_id": agent_id,
                    "action_type": "pass_turn",
                    "persisted": True,
                },
            ),
        ):
            mock_settings.return_value.SIMULATION_COMPACTION_INTERVAL = 5
            result = run_agent_turn.__wrapped__(agent_id)

        mock_load.assert_called_once()
        assert result["agent_instance_id"] == agent_id
        assert "status" not in result or result.get("status") != "skipped_inactive"
