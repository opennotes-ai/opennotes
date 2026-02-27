from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _run_coro(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_mock_session_ctx(session):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _patch_run_sync():
    return patch(
        "src.simulation.workflows.orchestrator_workflow.run_sync",
        side_effect=_run_coro,
    )


def _patch_session(mock_session_ctx):
    return patch(
        "src.database.get_session_maker",
        return_value=lambda: mock_session_ctx,
    )


def _make_config(
    *,
    turn_cadence_seconds: int = 10,
    max_agents: int = 5,
    removal_rate: float = 0.0,
    max_turns_per_agent: int = 100,
    agent_profile_ids: list[str] | None = None,
    community_server_id: str | None = None,
) -> dict:
    return {
        "turn_cadence_seconds": turn_cadence_seconds,
        "max_agents": max_agents,
        "removal_rate": removal_rate,
        "max_turns_per_agent": max_turns_per_agent,
        "agent_profile_ids": agent_profile_ids or [str(uuid4())],
        "community_server_id": community_server_id or str(uuid4()),
    }


class TestWorkflowNameConstants:
    def test_workflow_name_matches_qualname(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import (
            RUN_ORCHESTRATOR_WORKFLOW_NAME,
            run_orchestrator,
        )

        assert run_orchestrator.__qualname__ == RUN_ORCHESTRATOR_WORKFLOW_NAME

    def test_workflow_name_is_nonempty_string(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import RUN_ORCHESTRATOR_WORKFLOW_NAME

        assert isinstance(RUN_ORCHESTRATOR_WORKFLOW_NAME, str)
        assert len(RUN_ORCHESTRATOR_WORKFLOW_NAME) > 0


class TestInitializeRunStep:
    def test_initialize_run_atomic_update_and_loads_config(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import initialize_run_step

        run_id = uuid4()
        cs_id = uuid4()

        mock_orchestrator = MagicMock()
        mock_orchestrator.turn_cadence_seconds = 30
        mock_orchestrator.max_agents = 10
        mock_orchestrator.removal_rate = 0.1
        mock_orchestrator.max_turns_per_agent = 50
        mock_orchestrator.agent_profile_ids = [str(uuid4())]

        mock_run = MagicMock()
        mock_run.community_server_id = cs_id
        mock_run.orchestrator = mock_orchestrator

        update_result = MagicMock()
        update_result.scalar_one_or_none.return_value = run_id

        run_result = MagicMock()
        run_result.scalar_one.return_value = mock_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[update_result, run_result])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = initialize_run_step.__wrapped__(str(run_id))

        assert result["turn_cadence_seconds"] == 30
        assert result["max_agents"] == 10
        assert result["removal_rate"] == 0.1
        assert result["max_turns_per_agent"] == 50
        assert result["community_server_id"] == str(cs_id)
        assert mock_session.execute.await_count == 2
        mock_session.commit.assert_awaited_once()

    def test_initialize_run_fails_if_run_not_found(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import initialize_run_step

        update_result = MagicMock()
        update_result.scalar_one_or_none.return_value = None

        check_result = MagicMock()
        check_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[update_result, check_result])

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            pytest.raises(ValueError, match="SimulationRun not found"),
        ):
            initialize_run_step.__wrapped__(str(uuid4()))

    def test_initialize_run_fails_if_completed(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import initialize_run_step

        update_result = MagicMock()
        update_result.scalar_one_or_none.return_value = None

        check_result = MagicMock()
        check_result.scalar_one_or_none.return_value = "completed"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[update_result, check_result])

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            pytest.raises(ValueError, match="expected 'pending' or 'running'"),
        ):
            initialize_run_step.__wrapped__(str(uuid4()))

    def test_initialize_run_accepts_running_on_retry(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import initialize_run_step

        run_id = uuid4()
        cs_id = uuid4()

        mock_orchestrator = MagicMock()
        mock_orchestrator.turn_cadence_seconds = 10
        mock_orchestrator.max_agents = 5
        mock_orchestrator.removal_rate = 0.0
        mock_orchestrator.max_turns_per_agent = 100
        mock_orchestrator.agent_profile_ids = [str(uuid4())]

        mock_run = MagicMock()
        mock_run.community_server_id = cs_id
        mock_run.orchestrator = mock_orchestrator

        update_result = MagicMock()
        update_result.scalar_one_or_none.return_value = run_id

        run_result = MagicMock()
        run_result.scalar_one.return_value = mock_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[update_result, run_result])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = initialize_run_step.__wrapped__(str(run_id))

        assert result["turn_cadence_seconds"] == 10


class TestCheckRunStatusStep:
    def test_check_run_status_returns_running(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import check_run_status_step

        mock_session = AsyncMock()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = "running"
        mock_session.execute = AsyncMock(return_value=status_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = check_run_status_step.__wrapped__(str(uuid4()))

        assert result == "running"

    def test_check_run_status_returns_paused(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import check_run_status_step

        mock_session = AsyncMock()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = "paused"
        mock_session.execute = AsyncMock(return_value=status_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = check_run_status_step.__wrapped__(str(uuid4()))

        assert result == "paused"

    def test_check_run_status_returns_cancelled(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import check_run_status_step

        mock_session = AsyncMock()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = "cancelled"
        mock_session.execute = AsyncMock(return_value=status_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = check_run_status_step.__wrapped__(str(uuid4()))

        assert result == "cancelled"


class TestGetPopulationSnapshotStep:
    def test_population_snapshot_counts_active_instances(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import get_population_snapshot_step

        mock_session = AsyncMock()
        active_result = MagicMock()
        active_result.scalar.return_value = 3
        total_result = MagicMock()
        total_result.scalar.return_value = 7
        removed_result = MagicMock()
        removed_result.scalar.return_value = 4
        mock_session.execute = AsyncMock(side_effect=[active_result, total_result, removed_result])

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = get_population_snapshot_step.__wrapped__(str(uuid4()))

        assert result["active_count"] == 3
        assert result["total_spawned"] == 7
        assert result["total_removed"] == 4

    def test_population_snapshot_empty_run(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import get_population_snapshot_step

        mock_session = AsyncMock()
        zero_result = MagicMock()
        zero_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(side_effect=[zero_result, zero_result, zero_result])

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = get_population_snapshot_step.__wrapped__(str(uuid4()))

        assert result["active_count"] == 0
        assert result["total_spawned"] == 0
        assert result["total_removed"] == 0


class TestSpawnAgentsStep:
    def test_spawn_agents_creates_user_profiles_and_instances(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        config = _make_config(max_agents=1, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        mock_session.execute = AsyncMock(side_effect=[count_result, agent_name_result])

        added_objects: list = []

        def track_add(obj):
            added_objects.append(obj)
            if hasattr(obj, "id") and obj.id is None:
                obj.id = uuid4()

        mock_session.add = MagicMock(side_effect=track_add)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = spawn_agents_step.__wrapped__(
                str(uuid4()), config, active_count=0, total_spawned=0
            )

        assert len(result) == 1
        assert mock_session.add.call_count == 3

    def test_spawn_agents_respects_max_cap(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        config = _make_config(max_agents=5, agent_profile_ids=[str(uuid4())])

        result = spawn_agents_step.__wrapped__(
            str(uuid4()), config, active_count=5, total_spawned=5
        )

        assert result == []

    def test_spawn_agents_idempotent_check(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        config = _make_config(max_agents=5, agent_profile_ids=[str(uuid4())])

        mock_session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 5
        mock_session.execute = AsyncMock(return_value=count_result)
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = spawn_agents_step.__wrapped__(
                str(uuid4()), config, active_count=0, total_spawned=0
            )

        assert result == []

    def test_spawn_agents_round_robin_profile_selection(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_ids = [str(uuid4()) for _ in range(3)]
        config = _make_config(max_agents=10, agent_profile_ids=profile_ids)

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "Agent"

        mock_session.execute = AsyncMock(side_effect=[count_result] + [agent_name_result] * 5)
        mock_session.add = MagicMock(
            side_effect=lambda obj: setattr(obj, "id", uuid4())
            if hasattr(obj, "id") and obj.id is None
            else None
        )
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = spawn_agents_step.__wrapped__(
                str(uuid4()), config, active_count=0, total_spawned=0
            )

        assert len(result) == 5


class TestRemoveAgentsStep:
    def test_remove_agents_marks_instances_removed(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import remove_agents_step

        config = _make_config(removal_rate=1.0)
        oldest_id = uuid4()

        mock_session = AsyncMock()
        oldest_result = MagicMock()
        oldest_result.scalar_one_or_none.return_value = oldest_id

        remove_result = MagicMock()
        remove_result.scalar_one_or_none.return_value = oldest_id

        mock_session.execute = AsyncMock(side_effect=[oldest_result, remove_result])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch("src.simulation.workflows.orchestrator_workflow.random") as mock_random,
        ):
            mock_random.random.return_value = 0.0
            result = remove_agents_step.__wrapped__(str(uuid4()), config, active_count=3)

        assert len(result) == 1
        assert result[0] == str(oldest_id)

    def test_remove_agents_skips_when_rate_zero(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import remove_agents_step

        config = _make_config(removal_rate=0.0)

        result = remove_agents_step.__wrapped__(str(uuid4()), config, active_count=5)

        assert result == []

    def test_remove_agents_respects_minimum_population(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import remove_agents_step

        config = _make_config(removal_rate=1.0)

        result = remove_agents_step.__wrapped__(str(uuid4()), config, active_count=1)

        assert result == []

    def test_remove_agents_handles_concurrent_removal(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import remove_agents_step

        config = _make_config(removal_rate=1.0)
        oldest_id = uuid4()

        mock_session = AsyncMock()
        oldest_result = MagicMock()
        oldest_result.scalar_one_or_none.return_value = oldest_id

        remove_result = MagicMock()
        remove_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[oldest_result, remove_result])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch("src.simulation.workflows.orchestrator_workflow.random") as mock_random,
        ):
            mock_random.random.return_value = 0.0
            result = remove_agents_step.__wrapped__(str(uuid4()), config, active_count=3)

        assert result == []


class TestDetectStuckAgentsStep:
    def test_detect_stuck_agents_increments_retry_count_on_error(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import detect_stuck_agents_step

        run_id = str(uuid4())
        agent_id = uuid4()

        query_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.all.return_value = [(agent_id, 0, 0)]
        query_session.execute = AsyncMock(return_value=agents_result)

        update_session = AsyncMock()
        update_session.execute = AsyncMock()
        update_session.commit = AsyncMock()

        session_call_count = [0]

        def make_session():
            ctx = AsyncMock()
            if session_call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=query_session)
            else:
                ctx.__aenter__ = AsyncMock(return_value=update_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            session_call_count[0] += 1
            return ctx

        mock_wf_status = MagicMock()
        mock_wf_status.status = "ERROR"

        with (
            _patch_run_sync(),
            patch("src.database.get_session_maker", return_value=make_session),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.get_workflow_status.return_value = mock_wf_status
            result = detect_stuck_agents_step.__wrapped__(run_id)

        assert result["retried"] == 1
        mock_dbos.get_workflow_status.assert_called_once_with(f"turn-{agent_id}-1-retry0")
        update_session.execute.assert_awaited_once()
        update_session.commit.assert_awaited_once()

    def test_detect_stuck_agents_retries_on_max_recovery_exceeded(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import detect_stuck_agents_step

        run_id = str(uuid4())
        agent_id = uuid4()

        query_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.all.return_value = [(agent_id, 0, 0)]
        query_session.execute = AsyncMock(return_value=agents_result)

        update_session = AsyncMock()
        update_session.execute = AsyncMock()
        update_session.commit = AsyncMock()

        session_call_count = [0]

        def make_session():
            ctx = AsyncMock()
            if session_call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=query_session)
            else:
                ctx.__aenter__ = AsyncMock(return_value=update_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            session_call_count[0] += 1
            return ctx

        mock_wf_status = MagicMock()
        mock_wf_status.status = "MAX_RECOVERY_ATTEMPTS_EXCEEDED"

        with (
            _patch_run_sync(),
            patch("src.database.get_session_maker", return_value=make_session),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.get_workflow_status.return_value = mock_wf_status
            result = detect_stuck_agents_step.__wrapped__(run_id)

        assert result["retried"] == 1
        mock_dbos.get_workflow_status.assert_called_once_with(f"turn-{agent_id}-1-retry0")
        update_session.execute.assert_awaited_once()
        update_session.commit.assert_awaited_once()

    def test_detect_stuck_agents_retries_on_cancelled(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import detect_stuck_agents_step

        run_id = str(uuid4())
        agent_id = uuid4()

        query_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.all.return_value = [(agent_id, 0, 0)]
        query_session.execute = AsyncMock(return_value=agents_result)

        update_session = AsyncMock()
        update_session.execute = AsyncMock()
        update_session.commit = AsyncMock()

        session_call_count = [0]

        def make_session():
            ctx = AsyncMock()
            if session_call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=query_session)
            else:
                ctx.__aenter__ = AsyncMock(return_value=update_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            session_call_count[0] += 1
            return ctx

        mock_wf_status = MagicMock()
        mock_wf_status.status = "CANCELLED"

        with (
            _patch_run_sync(),
            patch("src.database.get_session_maker", return_value=make_session),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.get_workflow_status.return_value = mock_wf_status
            result = detect_stuck_agents_step.__wrapped__(run_id)

        assert result["retried"] == 1

    def test_detect_stuck_agents_skips_non_errored(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import detect_stuck_agents_step

        run_id = str(uuid4())
        agent_id = uuid4()

        mock_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.all.return_value = [(agent_id, 2, 0)]
        mock_session.execute = AsyncMock(return_value=agents_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        mock_wf_status = MagicMock()
        mock_wf_status.status = "SUCCESS"

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.get_workflow_status.return_value = mock_wf_status
            result = detect_stuck_agents_step.__wrapped__(run_id)

        assert result["retried"] == 0

    def test_detect_stuck_agents_skips_when_no_workflow_found(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import detect_stuck_agents_step

        run_id = str(uuid4())
        agent_id = uuid4()

        mock_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.all.return_value = [(agent_id, 0, 0)]
        mock_session.execute = AsyncMock(return_value=agents_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.get_workflow_status.return_value = None
            result = detect_stuck_agents_step.__wrapped__(run_id)

        assert result["retried"] == 0

    def test_detect_stuck_agents_uses_correct_workflow_id_format(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import detect_stuck_agents_step

        run_id = str(uuid4())
        agent_id = uuid4()

        mock_session = AsyncMock()
        agents_result = MagicMock()
        agents_result.all.return_value = [(agent_id, 3, 1)]
        mock_session.execute = AsyncMock(return_value=agents_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.get_workflow_status.return_value = None
            detect_stuck_agents_step.__wrapped__(run_id)

        mock_dbos.get_workflow_status.assert_called_once_with(f"turn-{agent_id}-4-retry1")


class TestScheduleTurnsStep:
    def test_schedule_turns_dispatches_for_active_agents(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import schedule_turns_step

        config = _make_config(max_turns_per_agent=100)
        instance1_id = uuid4()
        instance2_id = uuid4()

        mock_session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [
            (instance1_id, 0, 0),
            (instance2_id, 5, 0),
        ]
        mock_session.execute = AsyncMock(return_value=query_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        mock_dispatch = AsyncMock(return_value="wf-id")

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch(
                "src.simulation.workflows.agent_turn_workflow.dispatch_agent_turn",
                mock_dispatch,
            ),
        ):
            result = schedule_turns_step.__wrapped__(str(uuid4()), config)

        assert result["dispatched_count"] == 2
        assert result["skipped_count"] == 0
        assert mock_dispatch.await_count == 2

    def test_schedule_turns_skips_maxed_out_agents(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import schedule_turns_step

        config = _make_config(max_turns_per_agent=10)
        instance1_id = uuid4()
        instance2_id = uuid4()

        mock_session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [
            (instance1_id, 10, 0),
            (instance2_id, 5, 0),
        ]
        mock_session.execute = AsyncMock(return_value=query_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        mock_dispatch = AsyncMock(return_value="wf-id")

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch(
                "src.simulation.workflows.agent_turn_workflow.dispatch_agent_turn",
                mock_dispatch,
            ),
        ):
            result = schedule_turns_step.__wrapped__(str(uuid4()), config)

        assert result["dispatched_count"] == 1
        assert result["skipped_count"] == 1

    def test_schedule_turns_removes_agent_after_max_retries(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import schedule_turns_step

        config = _make_config(max_turns_per_agent=100)
        instance_id = uuid4()

        query_session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [
            (instance_id, 0, 3),
        ]
        query_session.execute = AsyncMock(return_value=query_result)

        removal_session = AsyncMock()
        removal_session.execute = AsyncMock()
        removal_session.commit = AsyncMock()

        session_call_count = [0]

        def make_session():
            ctx = AsyncMock()
            if session_call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=query_session)
            else:
                ctx.__aenter__ = AsyncMock(return_value=removal_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            session_call_count[0] += 1
            return ctx

        mock_dispatch = AsyncMock(return_value="wf-id")

        with (
            _patch_run_sync(),
            patch(
                "src.database.get_session_maker",
                return_value=make_session,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.dispatch_agent_turn",
                mock_dispatch,
            ),
        ):
            result = schedule_turns_step.__wrapped__(str(uuid4()), config)

        assert result["dispatched_count"] == 0
        assert result["removed_for_retries"] == 1
        mock_dispatch.assert_not_awaited()
        removal_session.execute.assert_awaited_once()
        removal_session.commit.assert_awaited_once()

    def test_schedule_turns_batches_multiple_retry_exhausted_removals(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import schedule_turns_step

        config = _make_config(max_turns_per_agent=100)
        id1 = uuid4()
        id2 = uuid4()
        id3 = uuid4()

        query_session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [
            (id1, 0, 3),
            (id2, 5, 4),
            (id3, 2, 0),
        ]
        query_session.execute = AsyncMock(return_value=query_result)

        removal_session = AsyncMock()
        removal_session.execute = AsyncMock()
        removal_session.commit = AsyncMock()

        session_call_count = [0]

        def make_session():
            ctx = AsyncMock()
            if session_call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=query_session)
            else:
                ctx.__aenter__ = AsyncMock(return_value=removal_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            session_call_count[0] += 1
            return ctx

        mock_dispatch = AsyncMock(return_value="wf-id")

        with (
            _patch_run_sync(),
            patch(
                "src.database.get_session_maker",
                return_value=make_session,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.dispatch_agent_turn",
                mock_dispatch,
            ),
        ):
            result = schedule_turns_step.__wrapped__(str(uuid4()), config)

        assert result["dispatched_count"] == 1
        assert result["removed_for_retries"] == 2
        removal_session.execute.assert_awaited_once()
        removal_session.commit.assert_awaited_once()

    def test_schedule_turns_passes_retry_count_to_dispatch(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import schedule_turns_step

        config = _make_config(max_turns_per_agent=100)
        instance_id = uuid4()

        mock_session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [
            (instance_id, 2, 1),
        ]
        mock_session.execute = AsyncMock(return_value=query_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        mock_dispatch = AsyncMock(return_value="wf-id")

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch(
                "src.simulation.workflows.agent_turn_workflow.dispatch_agent_turn",
                mock_dispatch,
            ),
        ):
            schedule_turns_step.__wrapped__(str(uuid4()), config)

        mock_dispatch.assert_awaited_once_with(instance_id, 3, 1)

    def test_schedule_turns_circuit_breaker_trips(self) -> None:
        from src.dbos_workflows.circuit_breaker import CircuitBreaker, CircuitOpenError

        breaker = CircuitBreaker(threshold=3, reset_timeout=300)

        for _ in range(3):
            breaker.record_failure()

        with pytest.raises(CircuitOpenError):
            breaker.check()


class TestCheckContentAvailabilityStep:
    def test_returns_has_content_true_when_pending_requests(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import (
            check_content_availability_step,
        )

        mock_session = AsyncMock()
        req_result = MagicMock()
        req_result.scalar.return_value = 3
        note_result = MagicMock()
        note_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(side_effect=[req_result, note_result])

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = check_content_availability_step.__wrapped__(str(uuid4()))

        assert result["has_content"] is True
        assert result["pending_requests"] == 3
        assert result["unrated_notes"] == 0

    def test_returns_has_content_true_when_unrated_notes(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import (
            check_content_availability_step,
        )

        mock_session = AsyncMock()
        req_result = MagicMock()
        req_result.scalar.return_value = 0
        note_result = MagicMock()
        note_result.scalar.return_value = 5
        mock_session.execute = AsyncMock(side_effect=[req_result, note_result])

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = check_content_availability_step.__wrapped__(str(uuid4()))

        assert result["has_content"] is True
        assert result["pending_requests"] == 0
        assert result["unrated_notes"] == 5

    def test_returns_has_content_false_when_empty(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import (
            check_content_availability_step,
        )

        mock_session = AsyncMock()
        req_result = MagicMock()
        req_result.scalar.return_value = 0
        note_result = MagicMock()
        note_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(side_effect=[req_result, note_result])

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = check_content_availability_step.__wrapped__(str(uuid4()))

        assert result["has_content"] is False
        assert result["pending_requests"] == 0
        assert result["unrated_notes"] == 0


class TestUpdateMetricsStep:
    def test_update_metrics_increments_counters(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import update_metrics_step

        mock_session = AsyncMock()
        metrics_result = MagicMock()
        metrics_result.scalar_one_or_none.return_value = {
            "turns_dispatched": 10,
            "agents_spawned": 5,
            "agents_removed": 2,
            "iterations": 3,
        }
        completed_result = MagicMock()
        completed_result.scalar.return_value = 13
        mock_session.execute = AsyncMock(side_effect=[metrics_result, completed_result, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = update_metrics_step.__wrapped__(
                str(uuid4()),
                dispatched_count=3,
                spawned_count=1,
                removed_count=0,
            )

        assert result["turns_dispatched"] == 13
        assert result["turns_completed"] == 13
        assert result["total_turns"] == 13
        assert result["agents_spawned"] == 6
        assert result["agents_removed"] == 2
        assert result["iterations"] == 4

    def test_update_metrics_handles_null_metrics(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import update_metrics_step

        mock_session = AsyncMock()
        metrics_result = MagicMock()
        metrics_result.scalar_one_or_none.return_value = None
        completed_result = MagicMock()
        completed_result.scalar.return_value = 2
        mock_session.execute = AsyncMock(side_effect=[metrics_result, completed_result, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = update_metrics_step.__wrapped__(
                str(uuid4()),
                dispatched_count=2,
                spawned_count=3,
                removed_count=0,
            )

        assert result["turns_dispatched"] == 2
        assert result["turns_completed"] == 2
        assert result["total_turns"] == 2
        assert result["agents_spawned"] == 3
        assert result["agents_removed"] == 0
        assert result["iterations"] == 1

    def test_update_metrics_turns_completed_from_agent_instances(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import update_metrics_step

        mock_session = AsyncMock()
        metrics_result = MagicMock()
        metrics_result.scalar_one_or_none.return_value = {
            "turns_dispatched": 50,
            "agents_spawned": 10,
            "agents_removed": 0,
            "iterations": 5,
        }
        completed_result = MagicMock()
        completed_result.scalar.return_value = 42
        mock_session.execute = AsyncMock(side_effect=[metrics_result, completed_result, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = update_metrics_step.__wrapped__(
                str(uuid4()),
                dispatched_count=5,
                spawned_count=0,
                removed_count=0,
            )

        assert result["turns_completed"] == 42
        assert result["total_turns"] == 42
        assert result["turns_dispatched"] == 55


class TestFinalizeRunStep:
    def test_finalize_run_sets_completed_status(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import finalize_run_step

        mock_session = AsyncMock()
        active_result = MagicMock()
        active_result.scalar.return_value = 2
        mock_session.execute = AsyncMock(side_effect=[active_result, None, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = finalize_run_step.__wrapped__(str(uuid4()), "completed")

        assert result["final_status"] == "completed"
        assert result["instances_finalized"] == 2

    def test_finalize_run_sets_cancelled_status(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import finalize_run_step

        mock_session = AsyncMock()
        active_result = MagicMock()
        active_result.scalar.return_value = 3
        mock_session.execute = AsyncMock(side_effect=[active_result, None, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = finalize_run_step.__wrapped__(str(uuid4()), "cancelled")

        assert result["final_status"] == "cancelled"
        assert result["instances_finalized"] == 3

    def test_finalize_run_marks_remaining_instances_completed(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import finalize_run_step

        mock_session = AsyncMock()
        active_result = MagicMock()
        active_result.scalar.return_value = 5
        mock_session.execute = AsyncMock(side_effect=[active_result, None, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = finalize_run_step.__wrapped__(str(uuid4()), "completed")

        assert result["instances_finalized"] == 5
        assert mock_session.execute.await_count == 3


class TestRunOrchestratorWorkflow:
    def test_run_orchestrator_happy_path_single_iteration(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()
        status_calls = iter(["running", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=["id-1"],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 1, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={
                    "total_turns": 1,
                    "agents_spawned": 1,
                    "agents_removed": 0,
                    "iterations": 1,
                },
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 1},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test-orch"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        assert result["simulation_run_id"] == run_id
        assert result["status"] == "cancelled"
        assert result["iterations"] == 2

    def test_run_orchestrator_paused_skips_turns(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()
        status_calls = iter(["paused", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
            ) as mock_snapshot,
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
            ) as mock_schedule,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_snapshot.assert_not_called()
        mock_schedule.assert_not_called()
        assert result["status"] == "cancelled"

    def test_run_orchestrator_cancelled_exits_immediately(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                return_value="cancelled",
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
            ) as mock_snapshot,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_snapshot.assert_not_called()
        assert result["status"] == "cancelled"
        assert result["iterations"] == 1

    def test_run_orchestrator_max_iterations_guard(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                return_value="running",
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 0, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "completed", "instances_finalized": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.MAX_ITERATIONS",
                3,
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        assert result["iterations"] == 3
        assert result["status"] == "completed"

    def test_run_orchestrator_finalize_failure_fallback(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()
        finalize_calls = [0]

        def mock_finalize(rid, status):
            finalize_calls[0] += 1
            if finalize_calls[0] == 1:
                raise RuntimeError("DB connection lost")
            return {"final_status": "failed", "instances_finalized": 0}

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                return_value="cancelled",
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                side_effect=mock_finalize,
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        assert result["status"] == "failed"
        assert finalize_calls[0] == 2


class TestSetRunStatusStep:
    def test_set_run_status_step_updates_status(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import set_run_status_step

        run_id = str(uuid4())
        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid4()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
        ):
            result = set_run_status_step.__wrapped__(run_id, "paused")

        assert result is True
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    def test_set_run_status_step_with_expected_status_match(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import set_run_status_step

        run_id = str(uuid4())
        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid4()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
        ):
            result = set_run_status_step.__wrapped__(run_id, "paused", expected_status="running")

        assert result is True
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    def test_set_run_status_step_with_expected_status_mismatch(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import set_run_status_step

        run_id = str(uuid4())
        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
        ):
            result = set_run_status_step.__wrapped__(run_id, "paused", expected_status="running")

        assert result is False
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    def test_set_run_status_step_sets_paused_at_for_paused(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import set_run_status_step

        run_id = str(uuid4())
        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid4()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch("src.simulation.workflows.orchestrator_workflow.pendulum") as mock_pendulum,
        ):
            mock_now = MagicMock()
            mock_pendulum.now.return_value = mock_now
            result = set_run_status_step.__wrapped__(run_id, "paused")

        assert result is True
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        compiled_str = str(compiled)
        assert "paused_at" in compiled_str


class TestDispatchOrchestrator:
    @pytest.mark.asyncio
    async def test_dispatch_orchestrator_enqueues_via_dbos_client(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import dispatch_orchestrator

        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "orchestrator-abc"
        mock_client.enqueue.return_value = mock_handle

        run_id = uuid4()

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            workflow_id = await dispatch_orchestrator(run_id)

        assert workflow_id == "orchestrator-abc"
        mock_client.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_orchestrator_uses_deduplication_id(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import dispatch_orchestrator

        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "test-wf"
        mock_client.enqueue.return_value = mock_handle

        run_id = uuid4()

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            await dispatch_orchestrator(run_id)
            await dispatch_orchestrator(run_id)

        call1_options = mock_client.enqueue.call_args_list[0].args[0]
        call2_options = mock_client.enqueue.call_args_list[1].args[0]
        assert call1_options["workflow_id"] == call2_options["workflow_id"]
        assert call1_options["deduplication_id"] == call2_options["deduplication_id"]
        assert call1_options["workflow_id"] == f"orchestrator-{run_id}-gen1"
        assert call1_options["queue_name"] == "simulation_orchestrator"

    @pytest.mark.asyncio
    async def test_dispatch_orchestrator_different_generation_different_workflow_id(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import dispatch_orchestrator

        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "test-wf"
        mock_client.enqueue.return_value = mock_handle

        run_id = uuid4()

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            await dispatch_orchestrator(run_id, generation=1)
            await dispatch_orchestrator(run_id, generation=2)

        call1_options = mock_client.enqueue.call_args_list[0].args[0]
        call2_options = mock_client.enqueue.call_args_list[1].args[0]
        assert call1_options["workflow_id"] == f"orchestrator-{run_id}-gen1"
        assert call2_options["workflow_id"] == f"orchestrator-{run_id}-gen2"
        assert call1_options["workflow_id"] != call2_options["workflow_id"]


class TestRunScoringStep:
    def test_run_scoring_step_calls_trigger_scoring(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_scoring_step

        mock_result = MagicMock()
        mock_result.scores_computed = 10
        mock_result.tier_name = "Minimal"
        mock_result.scorer_type = "BayesianAverageScorerAdapter"

        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch(
                "src.simulation.scoring_integration.trigger_scoring_for_simulation",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_trigger,
        ):
            result = run_scoring_step.__wrapped__(str(uuid4()))

        assert result["scores_computed"] == 10
        assert result["tier"] == "Minimal"
        assert result["scorer"] == "BayesianAverageScorerAdapter"
        mock_trigger.assert_awaited_once()


class TestOrchestratorEmptyContentPause:
    def test_orchestrator_auto_pauses_and_stays_alive(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        status_calls = iter(["running", "running", "running", "paused", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": False, "pending_requests": 0, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.set_run_status_step",
            ) as mock_set_status,
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
            ) as mock_snapshot,
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
            ) as mock_schedule,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.MAX_CONSECUTIVE_EMPTY",
                3,
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_set_status.assert_called_once_with(run_id, "paused", expected_status="running")
        mock_snapshot.assert_not_called()
        mock_schedule.assert_not_called()
        assert result["status"] == "cancelled"

    def test_orchestrator_resets_empty_counter_on_content(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        content_calls = iter(
            [
                {"has_content": False, "pending_requests": 0, "unrated_notes": 0},
                {"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ]
        )
        status_calls = iter(["running", "running", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                side_effect=lambda _: next(content_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 0, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        assert result["status"] == "cancelled"
        assert result["iterations"] == 3


class TestOrchestratorScoringIntegration:
    def test_orchestrator_calls_scoring_at_interval(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        iteration_count = [0]

        def mock_status(_):
            iteration_count[0] += 1
            if iteration_count[0] > 11:
                return "cancelled"
            return "running"

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=mock_status,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 0, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.run_scoring_step",
                return_value={"scores_computed": 5, "tier": "Minimal", "scorer": "Bayesian"},
            ) as mock_scoring,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        assert mock_scoring.call_count == 2
        assert result["status"] == "cancelled"

    def test_orchestrator_skips_scoring_on_non_interval(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()
        status_calls = iter(["running", "running", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 0, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.run_scoring_step",
            ) as mock_scoring,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"

            run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_scoring.assert_not_called()


class TestRetryExhaustedRemovalMetrics:
    def test_removed_for_retries_added_to_agents_removed_metric(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()
        status_calls = iter(["running", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 3, "total_spawned": 5, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=["removed-1"],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={
                    "dispatched_count": 1,
                    "skipped_count": 0,
                    "removed_for_retries": 2,
                },
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ) as mock_update_metrics,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"
            run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_update_metrics.assert_called_once_with(
            run_id,
            dispatched_count=1,
            spawned_count=0,
            removed_count=3,
        )


class TestConsecutiveEmptyResetOnException:
    def test_consecutive_empty_resets_on_content_check_exception(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        content_call_count = [0]

        def mock_content_check(_):
            content_call_count[0] += 1
            if content_call_count[0] <= 2:
                return {"has_content": False, "pending_requests": 0, "unrated_notes": 0}
            if content_call_count[0] == 3:
                raise RuntimeError("DB connection lost")
            if content_call_count[0] <= 12:
                return {"has_content": False, "pending_requests": 0, "unrated_notes": 0}
            return {"has_content": True, "pending_requests": 1, "unrated_notes": 0}

        status_call_count = [0]

        def mock_status(_):
            status_call_count[0] += 1
            if status_call_count[0] > 14:
                return "cancelled"
            return "running"

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=mock_status,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                side_effect=mock_content_check,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.set_run_status_step",
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 0, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.MAX_CONSECUTIVE_EMPTY",
                10,
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        assert result["status"] == "cancelled"
        assert content_call_count[0] > 10


class TestRefreshConfigStep:
    def test_refresh_config_reads_orchestrator_from_db(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import refresh_config_step

        run_id = uuid4()
        cs_id = uuid4()

        mock_orchestrator = MagicMock()
        mock_orchestrator.turn_cadence_seconds = 15
        mock_orchestrator.max_agents = 20
        mock_orchestrator.removal_rate = 0.05
        mock_orchestrator.max_turns_per_agent = 200
        mock_orchestrator.agent_profile_ids = [str(uuid4())]

        mock_run = MagicMock()
        mock_run.community_server_id = cs_id
        mock_run.orchestrator = mock_orchestrator

        run_result = MagicMock()
        run_result.scalar_one.return_value = mock_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=run_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = refresh_config_step.__wrapped__(str(run_id))

        assert result["max_agents"] == 20
        assert result["turn_cadence_seconds"] == 15
        assert result["removal_rate"] == 0.05
        assert result["max_turns_per_agent"] == 200
        assert result["community_server_id"] == str(cs_id)

    def test_refresh_config_returns_empty_list_when_no_profile_ids(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import refresh_config_step

        run_id = uuid4()
        cs_id = uuid4()

        mock_orchestrator = MagicMock()
        mock_orchestrator.turn_cadence_seconds = 10
        mock_orchestrator.max_agents = 5
        mock_orchestrator.removal_rate = 0.0
        mock_orchestrator.max_turns_per_agent = 100
        mock_orchestrator.agent_profile_ids = None

        mock_run = MagicMock()
        mock_run.community_server_id = cs_id
        mock_run.orchestrator = mock_orchestrator

        run_result = MagicMock()
        run_result.scalar_one.return_value = mock_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=run_result)

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = refresh_config_step.__wrapped__(str(run_id))

        assert result["agent_profile_ids"] == []


class TestPauseToRunningConfigRefresh:
    def test_config_refreshed_on_pause_to_running_transition(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        initial_config = _make_config(max_agents=5)
        refreshed_config = _make_config(max_agents=20, turn_cadence_seconds=5)

        status_calls = iter(["paused", "running", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=initial_config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.refresh_config_step",
                return_value=refreshed_config,
            ) as mock_refresh,
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 0, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_refresh.assert_called_once_with(run_id)
        assert result["status"] == "cancelled"

    def test_no_refresh_when_running_stays_running(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        status_calls = iter(["running", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.refresh_config_step",
            ) as mock_refresh,
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 0, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"
            run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_refresh.assert_not_called()

    def test_refresh_failure_does_not_crash_orchestrator(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        status_calls = iter(["paused", "running", "cancelled"])

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.initialize_run_step",
                return_value=config,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_run_status_step",
                side_effect=lambda _: next(status_calls),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.refresh_config_step",
                side_effect=Exception("DB connection lost"),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
                return_value={"has_content": True, "pending_requests": 1, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={"active_count": 0, "total_spawned": 0, "total_removed": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.remove_agents_step",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.detect_stuck_agents_step",
                return_value={"retried": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 0, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        assert result["status"] == "cancelled"
