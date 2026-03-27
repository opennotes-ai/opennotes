from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _run_coro(coro, **_kwargs):
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
    max_active_agents: int = 5,
    max_total_spawns: int = 2000,
    removal_rate: float = 0.0,
    max_turns_per_agent: int = 100,
    agent_profile_ids: list[str] | None = None,
    community_server_id: str | None = None,
) -> dict:
    return {
        "turn_cadence_seconds": turn_cadence_seconds,
        "max_active_agents": max_active_agents,
        "max_total_spawns": max_total_spawns,
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
        mock_orchestrator.max_active_agents = 10
        mock_orchestrator.max_total_spawns = 2000
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
        assert result["max_active_agents"] == 10
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
        mock_orchestrator.max_active_agents = 5
        mock_orchestrator.max_total_spawns = 2000
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
        removed_for_cause_result = MagicMock()
        removed_for_cause_result.scalar.return_value = 2
        removed_by_rate_result = MagicMock()
        removed_by_rate_result.scalar.return_value = 2
        mock_session.execute = AsyncMock(
            side_effect=[
                active_result,
                total_result,
                removed_for_cause_result,
                removed_by_rate_result,
            ]
        )

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = get_population_snapshot_step.__wrapped__(str(uuid4()))

        assert result["active_count"] == 3
        assert result["total_spawned"] == 7
        assert result["total_removed_for_cause"] == 2
        assert result["total_removed_by_rate"] == 2

    def test_population_snapshot_empty_run(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import get_population_snapshot_step

        mock_session = AsyncMock()
        zero_result = MagicMock()
        zero_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(
            side_effect=[zero_result, zero_result, zero_result, zero_result]
        )

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = get_population_snapshot_step.__wrapped__(str(uuid4()))

        assert result["active_count"] == 0
        assert result["total_spawned"] == 0
        assert result["total_removed_for_cause"] == 0
        assert result["total_removed_by_rate"] == 0


class TestSpawnAgentsStep:
    def test_spawn_agents_creates_user_profiles_and_instances(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        config = _make_config(max_active_agents=1, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        no_prior_instance_result = MagicMock()
        no_prior_instance_result.scalar_one_or_none.return_value = None

        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[
                count_result,
                agent_name_result,
                no_prior_instance_result,
                prior_memory_result,
            ]
        )

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
        assert mock_session.add.call_count == 4

    def test_spawn_agents_respects_max_cap(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        config = _make_config(max_active_agents=5, agent_profile_ids=[str(uuid4())])

        result = spawn_agents_step.__wrapped__(
            str(uuid4()), config, active_count=5, total_spawned=5
        )

        assert result == []

    def test_spawn_agents_idempotent_check(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        config = _make_config(
            max_active_agents=5, max_total_spawns=5, agent_profile_ids=[str(uuid4())]
        )

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
        config = _make_config(max_active_agents=10, agent_profile_ids=profile_ids)

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "Agent"

        no_prior_instance_result = MagicMock()
        no_prior_instance_result.scalar_one_or_none.return_value = None

        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[count_result]
            + [agent_name_result, no_prior_instance_result, prior_memory_result] * 5
        )
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

    def test_spawn_seeds_acted_on_from_prior_instance(self) -> None:
        from src.simulation.models import SimAgentMemory
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        prior_user_profile_id = uuid4()
        prior_instance_id = uuid4()
        config = _make_config(max_active_agents=1, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        mock_prior_instance = MagicMock()
        mock_prior_instance.id = prior_instance_id
        mock_prior_instance.user_profile_id = prior_user_profile_id
        prior_instance_result = MagicMock()
        prior_instance_result.scalar_one_or_none.return_value = mock_prior_instance

        active_conflict_result = MagicMock()
        active_conflict_result.scalar.return_value = 0

        mock_prior_memory = MagicMock()
        mock_prior_memory.message_history = [{"role": "user", "content": "hi"}]
        mock_prior_memory.token_count = 42
        mock_prior_memory.recent_actions = ["write_note"]
        mock_prior_memory.seen_request_ids = ["req-0"]
        mock_prior_memory.acted_on_request_ids = ["req-1", "req-2"]
        mock_prior_memory.compaction_strategy = "sliding_window"
        mock_prior_memory.last_compacted_at = None
        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = mock_prior_memory

        mock_session.execute = AsyncMock(
            side_effect=[
                count_result,
                agent_name_result,
                prior_instance_result,
                active_conflict_result,
                prior_memory_result,
            ]
        )

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

        memory_objects = [o for o in added_objects if isinstance(o, SimAgentMemory)]
        assert len(memory_objects) == 1
        assert memory_objects[0].acted_on_request_ids == ["req-1", "req-2"]

    def test_spawn_creates_empty_memory_for_first_instance(self) -> None:
        from src.simulation.models import SimAgentMemory
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        config = _make_config(max_active_agents=1, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        no_prior_instance_result = MagicMock()
        no_prior_instance_result.scalar_one_or_none.return_value = None

        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[
                count_result,
                agent_name_result,
                no_prior_instance_result,
                prior_memory_result,
            ]
        )

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

        memory_objects = [o for o in added_objects if isinstance(o, SimAgentMemory)]
        assert len(memory_objects) == 1
        assert memory_objects[0].acted_on_request_ids == []

    def test_spawn_continues_after_removals_when_under_active_cap(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        config = _make_config(
            max_active_agents=5,
            max_total_spawns=100,
            agent_profile_ids=[profile_id],
        )

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 8

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "Agent"

        no_prior_instance_result = MagicMock()
        no_prior_instance_result.scalar_one_or_none.return_value = None

        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[count_result]
            + [agent_name_result, no_prior_instance_result, prior_memory_result] * 3
        )
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
                str(uuid4()), config, active_count=2, total_spawned=8
            )

        assert len(result) == 3

    def test_spawn_blocked_by_total_cap_not_active_cap(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        config = _make_config(
            max_active_agents=10,
            max_total_spawns=6,
            agent_profile_ids=[profile_id],
        )

        mock_session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 6
        mock_session.execute = AsyncMock(return_value=count_result)
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = spawn_agents_step.__wrapped__(
                str(uuid4()), config, active_count=2, total_spawned=6
            )

        assert result == []

    def test_spawn_clamped_to_remaining_total_budget(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        config = _make_config(
            max_active_agents=10,
            max_total_spawns=8,
            agent_profile_ids=[profile_id],
        )

        mock_session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 6

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "Agent"

        no_prior_instance_result = MagicMock()
        no_prior_instance_result.scalar_one_or_none.return_value = None

        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[count_result]
            + [agent_name_result, no_prior_instance_result, prior_memory_result] * 2
        )
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
                str(uuid4()), config, active_count=0, total_spawned=6
            )

        assert len(result) == 2

    def test_spawn_blocked_by_active_cap(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        config = _make_config(
            max_active_agents=5,
            max_total_spawns=100,
            agent_profile_ids=[str(uuid4())],
        )

        result = spawn_agents_step.__wrapped__(
            str(uuid4()), config, active_count=5, total_spawned=3
        )

        assert result == []


class TestRespawnAgentMemory:
    def test_respawn_reuses_user_profile_id(self) -> None:
        from src.simulation.models import SimAgentInstance
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        prior_user_profile_id = uuid4()
        prior_instance_id = uuid4()
        config = _make_config(max_active_agents=1, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        mock_prior_instance = MagicMock()
        mock_prior_instance.id = prior_instance_id
        mock_prior_instance.user_profile_id = prior_user_profile_id
        prior_instance_result = MagicMock()
        prior_instance_result.scalar_one_or_none.return_value = mock_prior_instance

        active_conflict_result = MagicMock()
        active_conflict_result.scalar.return_value = 0

        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[
                count_result,
                agent_name_result,
                prior_instance_result,
                active_conflict_result,
                prior_memory_result,
            ]
        )

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
                str(uuid4()), config, active_count=0, total_spawned=1
            )

        assert len(result) == 1

        instance_objects = [o for o in added_objects if isinstance(o, SimAgentInstance)]
        assert len(instance_objects) == 1
        assert instance_objects[0].user_profile_id == prior_user_profile_id

    def test_respawn_copies_full_memory(self) -> None:
        from src.simulation.models import SimAgentMemory
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step

        profile_id = str(uuid4())
        prior_instance_id = uuid4()
        config = _make_config(max_active_agents=1, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        mock_prior_instance = MagicMock()
        mock_prior_instance.id = prior_instance_id
        mock_prior_instance.user_profile_id = uuid4()
        prior_instance_result = MagicMock()
        prior_instance_result.scalar_one_or_none.return_value = mock_prior_instance

        active_conflict_result = MagicMock()
        active_conflict_result.scalar.return_value = 0

        mock_prior_memory = MagicMock()
        mock_prior_memory.message_history = [{"role": "user", "content": "hello"}]
        mock_prior_memory.token_count = 150
        mock_prior_memory.recent_actions = ["rate_note", "write_note"]
        mock_prior_memory.seen_request_ids = ["req-A", "req-B"]
        mock_prior_memory.acted_on_request_ids = ["req-A"]
        mock_prior_memory.compaction_strategy = "sliding_window"
        mock_prior_memory.last_compacted_at = None
        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = mock_prior_memory

        mock_session.execute = AsyncMock(
            side_effect=[
                count_result,
                agent_name_result,
                prior_instance_result,
                active_conflict_result,
                prior_memory_result,
            ]
        )

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
                str(uuid4()), config, active_count=0, total_spawned=1
            )

        assert len(result) == 1

        memory_objects = [o for o in added_objects if isinstance(o, SimAgentMemory)]
        assert len(memory_objects) == 1
        mem = memory_objects[0]
        assert mem.message_history == [{"role": "user", "content": "hello"}]
        assert mem.token_count == 150
        assert mem.recent_actions == ["rate_note", "write_note"]
        assert mem.seen_request_ids == ["req-A", "req-B"]
        assert mem.acted_on_request_ids == ["req-A"]
        assert mem.compaction_strategy == "sliding_window"
        assert mem.turn_count == 0

    def test_respawn_no_new_user_profile_or_community_member(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step
        from src.users.profile_models import CommunityMember, UserProfile

        profile_id = str(uuid4())
        prior_instance_id = uuid4()
        config = _make_config(max_active_agents=1, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        mock_prior_instance = MagicMock()
        mock_prior_instance.id = prior_instance_id
        mock_prior_instance.user_profile_id = uuid4()
        prior_instance_result = MagicMock()
        prior_instance_result.scalar_one_or_none.return_value = mock_prior_instance

        active_conflict_result = MagicMock()
        active_conflict_result.scalar.return_value = 0

        mock_prior_memory = MagicMock()
        mock_prior_memory.message_history = []
        mock_prior_memory.token_count = 0
        mock_prior_memory.recent_actions = []
        mock_prior_memory.seen_request_ids = []
        mock_prior_memory.acted_on_request_ids = []
        mock_prior_memory.compaction_strategy = None
        mock_prior_memory.last_compacted_at = None
        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = mock_prior_memory

        mock_session.execute = AsyncMock(
            side_effect=[
                count_result,
                agent_name_result,
                prior_instance_result,
                active_conflict_result,
                prior_memory_result,
            ]
        )

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
            spawn_agents_step.__wrapped__(str(uuid4()), config, active_count=0, total_spawned=1)

        user_profiles = [o for o in added_objects if isinstance(o, UserProfile)]
        community_members = [o for o in added_objects if isinstance(o, CommunityMember)]
        assert len(user_profiles) == 0
        assert len(community_members) == 0

    def test_first_spawn_creates_new_user_profile(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step
        from src.users.profile_models import CommunityMember, UserProfile

        profile_id = str(uuid4())
        config = _make_config(max_active_agents=1, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        no_prior_instance_result = MagicMock()
        no_prior_instance_result.scalar_one_or_none.return_value = None

        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[
                count_result,
                agent_name_result,
                no_prior_instance_result,
                prior_memory_result,
            ]
        )

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

        user_profiles = [o for o in added_objects if isinstance(o, UserProfile)]
        community_members = [o for o in added_objects if isinstance(o, CommunityMember)]
        assert len(user_profiles) == 1
        assert len(community_members) == 1

    def test_active_conflict_creates_new_user_profile(self) -> None:
        from src.simulation.models import SimAgentInstance
        from src.simulation.workflows.orchestrator_workflow import spawn_agents_step
        from src.users.profile_models import CommunityMember, UserProfile

        profile_id = str(uuid4())
        prior_instance_id = uuid4()
        prior_user_profile_id = uuid4()
        config = _make_config(max_active_agents=2, agent_profile_ids=[profile_id])

        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        agent_name_result = MagicMock()
        agent_name_result.scalar_one_or_none.return_value = "TestAgent"

        mock_prior_instance = MagicMock()
        mock_prior_instance.id = prior_instance_id
        mock_prior_instance.user_profile_id = prior_user_profile_id
        prior_instance_result = MagicMock()
        prior_instance_result.scalar_one_or_none.return_value = mock_prior_instance

        active_conflict_result = MagicMock()
        active_conflict_result.scalar.return_value = 1

        prior_memory_result = MagicMock()
        prior_memory_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[
                count_result,
                agent_name_result,
                prior_instance_result,
                active_conflict_result,
                prior_memory_result,
            ]
        )

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
                str(uuid4()), config, active_count=1, total_spawned=2
            )

        assert len(result) == 1

        user_profiles = [o for o in added_objects if isinstance(o, UserProfile)]
        community_members = [o for o in added_objects if isinstance(o, CommunityMember)]
        assert len(user_profiles) == 1
        assert len(community_members) == 1

        instance_objects = [o for o in added_objects if isinstance(o, SimAgentInstance)]
        assert len(instance_objects) == 1
        assert instance_objects[0].user_profile_id != prior_user_profile_id


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
        mock_dbos.get_workflow_status.assert_called_once_with(f"turn-{agent_id}-gen1-1-retry0")
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
        mock_dbos.get_workflow_status.assert_called_once_with(f"turn-{agent_id}-gen1-1-retry0")
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

        mock_dbos.get_workflow_status.assert_called_once_with(f"turn-{agent_id}-gen1-4-retry1")


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
            result = schedule_turns_step(str(uuid4()), config)

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
            result = schedule_turns_step(str(uuid4()), config)

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
            result = schedule_turns_step(str(uuid4()), config)

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
            result = schedule_turns_step(str(uuid4()), config)

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
            schedule_turns_step(str(uuid4()), config)

        mock_dispatch.assert_awaited_once_with(instance_id, 3, 1, generation=1)

    def test_schedule_turns_circuit_breaker_trips(self) -> None:
        from src.dbos_workflows.circuit_breaker import CircuitBreaker, CircuitOpenError

        breaker = CircuitBreaker(threshold=3, reset_timeout=300)

        for _ in range(3):
            breaker.record_failure()

        with pytest.raises(CircuitOpenError):
            breaker.check()

    def test_circuit_breaker_stuck_log_after_consecutive_skips(self) -> None:
        import logging

        from src.dbos_workflows.circuit_breaker import CircuitBreaker, CircuitOpenError
        from src.simulation.workflows.orchestrator_workflow import (
            CIRCUIT_BREAKER_STUCK_THRESHOLD,
        )

        breaker = CircuitBreaker(threshold=2, reset_timeout=300)
        for _ in range(2):
            breaker.record_failure()

        consecutive_open_skips = 0
        log_messages: list[tuple[int, str]] = []

        for _ in range(CIRCUIT_BREAKER_STUCK_THRESHOLD + 1):
            try:
                breaker.check()
            except CircuitOpenError:
                consecutive_open_skips += 1
                if consecutive_open_skips >= CIRCUIT_BREAKER_STUCK_THRESHOLD:
                    log_messages.append((logging.ERROR, "circuit_breaker_stuck"))
                else:
                    log_messages.append((logging.WARNING, "skipping"))

        assert len([m for m in log_messages if m[0] == logging.ERROR]) == 2
        assert log_messages[0][0] == logging.WARNING
        assert log_messages[1][0] == logging.WARNING
        assert log_messages[2][0] == logging.ERROR


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

    def test_update_metrics_preserves_scoring_keys(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import update_metrics_step

        mock_session = AsyncMock()
        metrics_result = MagicMock()
        metrics_result.scalar_one_or_none.return_value = {
            "turns_dispatched": 10,
            "agents_spawned": 3,
            "agents_removed": 0,
            "iterations": 2,
            "scores_computed": 42,
            "last_scoring_tier": "BASIC",
            "tiers_reached": ["MINIMAL", "BASIC"],
            "scorers_used": ["BayesianAverageScorer"],
            "tier_distribution": {"MINIMAL": 10, "BASIC": 32},
            "scorer_breakdown": {"BayesianAverageScorer": 42},
        }
        completed_result = MagicMock()
        completed_result.scalar.return_value = 8
        mock_session.execute = AsyncMock(side_effect=[metrics_result, completed_result, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = update_metrics_step.__wrapped__(
                str(uuid4()),
                dispatched_count=2,
                spawned_count=1,
                removed_count=0,
            )

        assert result["turns_dispatched"] == 12
        assert result["iterations"] == 3
        assert result["scores_computed"] == 42
        assert result["last_scoring_tier"] == "BASIC"
        assert result["tiers_reached"] == ["MINIMAL", "BASIC"]
        assert result["scorers_used"] == ["BayesianAverageScorer"]
        assert result["tier_distribution"] == {"MINIMAL": 10, "BASIC": 32}
        assert result["scorer_breakdown"] == {"BayesianAverageScorer": 42}

    def test_update_metrics_preserves_iteration_skip_keys(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import update_metrics_step

        mock_session = AsyncMock()
        metrics_result = MagicMock()
        metrics_result.scalar_one_or_none.return_value = {
            "turns_dispatched": 10,
            "agents_spawned": 5,
            "agents_removed": 0,
            "iterations": 3,
            "skipped_no_content_iter_3": 4,
        }
        completed_result = MagicMock()
        completed_result.scalar.return_value = 8
        mock_session.execute = AsyncMock(side_effect=[metrics_result, completed_result, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            result = update_metrics_step.__wrapped__(
                str(uuid4()),
                dispatched_count=2,
                spawned_count=0,
                removed_count=0,
            )

        assert "_skipped_no_content" not in result
        assert "skipped_no_content_iter_3" in result
        assert result["skipped_no_content_iter_3"] == 4


class TestSetCurrentIterationStep:
    def test_set_current_iteration_executes_sql_update(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import set_current_iteration_step

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            set_current_iteration_step.__wrapped__(str(uuid4()), iteration=7)

        assert mock_session.execute.await_count == 1
        assert mock_session.commit.await_count == 1


class TestReadIterationSkipCountStep:
    def test_reads_count_and_deletes_key(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import read_iteration_skip_count_step

        mock_session = AsyncMock()
        metrics_result = MagicMock()
        metrics_result.scalar_one_or_none.return_value = {
            "skipped_no_content_iter_5": 3,
            "turns_dispatched": 10,
        }
        mock_session.execute = AsyncMock(side_effect=[metrics_result, None])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            count = read_iteration_skip_count_step.__wrapped__(str(uuid4()), iteration=5)

        assert count == 3
        assert mock_session.execute.await_count == 2
        assert mock_session.commit.await_count == 1

    def test_returns_zero_when_key_missing(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import read_iteration_skip_count_step

        mock_session = AsyncMock()
        metrics_result = MagicMock()
        metrics_result.scalar_one_or_none.return_value = {
            "turns_dispatched": 10,
        }
        mock_session.execute = AsyncMock(side_effect=[metrics_result])
        mock_session.commit = AsyncMock()

        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with _patch_run_sync(), _patch_session(mock_session_ctx):
            count = read_iteration_skip_count_step.__wrapped__(str(uuid4()), iteration=5)

        assert count == 0
        assert mock_session.execute.await_count == 1
        assert mock_session.commit.await_count == 0


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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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

    def test_set_run_status_step_with_expected_generation_mismatch(self) -> None:
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
            result = set_run_status_step.__wrapped__(
                run_id,
                "failed",
                expected_status="running",
                expected_generation=2,
            )

        assert result is False
        stmt = mock_session.execute.call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        compiled_str = str(compiled)
        assert "generation = 2" in compiled_str
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

    def test_set_run_status_step_persists_error_message_for_failed(self) -> None:
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
            result = set_run_status_step.__wrapped__(
                run_id,
                "failed",
                error_message="required scoring snapshot persistence failed",
            )

        assert result is True
        stmt = mock_session.execute.call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        compiled_str = str(compiled)
        assert "error_message" in compiled_str
        assert "required scoring snapshot persistence failed" in compiled_str


class TestDispatchOrchestrator:
    @pytest.mark.asyncio
    async def test_dispatch_orchestrator_enqueues_via_queue(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import (
            dispatch_orchestrator,
            run_orchestrator,
        )

        run_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = f"orchestrator-{run_id}-gen1"

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.simulation_orchestrator_queue"
            ) as mock_queue,
            patch("dbos.SetWorkflowID"),
            patch("dbos.SetEnqueueOptions"),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            mock_queue.enqueue.return_value = mock_handle
            workflow_id = await dispatch_orchestrator(run_id)

        assert workflow_id == f"orchestrator-{run_id}-gen1"
        mock_queue.enqueue.assert_called_once_with(run_orchestrator, str(run_id))

    @pytest.mark.asyncio
    async def test_dispatch_orchestrator_uses_deduplication_id(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import dispatch_orchestrator

        run_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = f"orchestrator-{run_id}-gen1"

        captured_wf_ids: list[str] = []
        captured_dedup_ids: list[str] = []

        def capture_set_wf_id(wf_id):
            captured_wf_ids.append(wf_id)
            return MagicMock()

        def capture_set_enqueue_opts(*, deduplication_id):
            captured_dedup_ids.append(deduplication_id)
            return MagicMock()

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.simulation_orchestrator_queue"
            ) as mock_queue,
            patch("dbos.SetWorkflowID", side_effect=capture_set_wf_id),
            patch("dbos.SetEnqueueOptions", side_effect=capture_set_enqueue_opts),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            mock_queue.enqueue.return_value = mock_handle
            await dispatch_orchestrator(run_id)
            await dispatch_orchestrator(run_id)

        assert captured_wf_ids[0] == captured_wf_ids[1]
        assert captured_dedup_ids[0] == captured_dedup_ids[1]
        assert captured_wf_ids[0] == f"orchestrator-{run_id}-gen1"

    @pytest.mark.asyncio
    async def test_dispatch_orchestrator_different_generation_different_workflow_id(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import dispatch_orchestrator

        run_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = "test-wf"

        captured_wf_ids: list[str] = []

        def capture_set_wf_id(wf_id):
            captured_wf_ids.append(wf_id)
            return MagicMock()

        with (
            patch(
                "src.simulation.workflows.orchestrator_workflow.simulation_orchestrator_queue"
            ) as mock_queue,
            patch("dbos.SetWorkflowID", side_effect=capture_set_wf_id),
            patch("dbos.SetEnqueueOptions"),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            mock_queue.enqueue.return_value = mock_handle
            await dispatch_orchestrator(run_id, generation=1)
            await dispatch_orchestrator(run_id, generation=2)

        assert captured_wf_ids[0] == f"orchestrator-{run_id}-gen1"
        assert captured_wf_ids[1] == f"orchestrator-{run_id}-gen2"
        assert captured_wf_ids[0] != captured_wf_ids[1]


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

    def test_run_scoring_step_has_max_attempts_3(self) -> None:
        import inspect

        from src.simulation.workflows.orchestrator_workflow import run_scoring_step

        source = inspect.getsource(run_scoring_step)
        assert "max_attempts=3" in source


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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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

    def test_orchestrator_continues_after_scoring_failure(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        iteration_count = [0]

        def mock_status(_):
            iteration_count[0] += 1
            if iteration_count[0] > 3:
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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
                side_effect=RuntimeError("scoring exploded"),
            ) as mock_scoring,
            patch(
                "src.simulation.workflows.orchestrator_workflow.set_run_status_step",
            ) as mock_set_status,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ) as mock_finalize,
            patch("src.simulation.workflows.orchestrator_workflow.SCORING_INTERVAL", 1),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        assert result["status"] == "cancelled"
        assert mock_scoring.call_count >= 2
        failed_calls = [
            c for c in mock_set_status.call_args_list if len(c.args) >= 2 and c.args[1] == "failed"
        ]
        assert len(failed_calls) == 0
        mock_finalize.assert_called_once_with(run_id, "cancelled")


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
                return_value={
                    "active_count": 3,
                    "total_spawned": 5,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
    def test_exception_preserves_consecutive_empty_and_triggers_auto_pause(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        config = _make_config()

        content_call_count = [0]

        def mock_content_check(_):
            content_call_count[0] += 1
            if content_call_count[0] <= 9:
                return {"has_content": False, "pending_requests": 0, "unrated_notes": 0}
            if content_call_count[0] == 10:
                raise RuntimeError("DB connection lost")
            return {"has_content": False, "pending_requests": 0, "unrated_notes": 0}

        paused = [False]

        def mock_status(_):
            if paused[0]:
                return "cancelled"
            return "running"

        def mock_set_status(run_id, status, expected_status=None):
            if status == "paused":
                paused[0] = True
            return True

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
                side_effect=mock_set_status,
            ) as mock_pause,
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
        mock_pause.assert_any_call(run_id, "paused", expected_status="running")
        assert content_call_count[0] == 11


class TestRefreshConfigStep:
    def test_refresh_config_reads_orchestrator_from_db(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import refresh_config_step

        run_id = uuid4()
        cs_id = uuid4()

        mock_orchestrator = MagicMock()
        mock_orchestrator.turn_cadence_seconds = 15
        mock_orchestrator.max_active_agents = 20
        mock_orchestrator.max_total_spawns = 2000
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

        assert result["max_active_agents"] == 20
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
        mock_orchestrator.max_active_agents = 5
        mock_orchestrator.max_total_spawns = 2000
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
        initial_config = _make_config(max_active_agents=5)
        refreshed_config = _make_config(max_active_agents=20, turn_cadence_seconds=5)

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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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


class TestGenerationGuard:
    def test_orchestrator_exits_when_generation_changes_after_refresh(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        initial_config = _make_config()
        initial_config["generation"] = 1

        refreshed_config = _make_config()
        refreshed_config["generation"] = 2

        status_calls = iter(["paused", "running"])

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
            ) as mock_content,
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
            ) as mock_snapshot,
            patch(
                "src.simulation.workflows.orchestrator_workflow.spawn_agents_step",
            ) as mock_spawn,
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
            ) as mock_schedule,
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
            ) as mock_metrics,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
            ) as mock_finalize,
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-old-gen"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_refresh.assert_called_once_with(run_id)
        mock_content.assert_not_called()
        mock_snapshot.assert_not_called()
        mock_spawn.assert_not_called()
        mock_schedule.assert_not_called()
        mock_metrics.assert_not_called()
        mock_finalize.assert_not_called()
        assert result["status"] == "superseded"
        assert result["simulation_run_id"] == run_id

    def test_orchestrator_continues_when_generation_unchanged_after_refresh(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        initial_config = _make_config()
        initial_config["generation"] = 1

        refreshed_config = _make_config()
        refreshed_config["generation"] = 1

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
                return_value={
                    "active_count": 0,
                    "total_spawned": 0,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
            ) as mock_finalize,
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_refresh.assert_called_once_with(run_id)
        mock_finalize.assert_called_once()
        assert result["status"] == "cancelled"

    def test_orchestrator_checks_generation_even_when_refresh_fails(self) -> None:
        from src.simulation.workflows.orchestrator_workflow import run_orchestrator

        run_id = str(uuid4())
        initial_config = _make_config()
        initial_config["generation"] = 1

        status_calls = iter(["paused", "running"])

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
                side_effect=Exception("DB connection lost"),
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_generation_step",
                return_value=2,
            ) as mock_check_gen,
            patch(
                "src.simulation.workflows.orchestrator_workflow.check_content_availability_step",
            ) as mock_content,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
            ) as mock_finalize,
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-old-gen"
            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_check_gen.assert_called_once_with(run_id)
        mock_content.assert_not_called()
        mock_finalize.assert_not_called()
        assert result["status"] == "superseded"


class TestSkippedNoContentConsecutiveEmpty:
    def test_all_agents_skipped_increments_consecutive_empty(self) -> None:
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
                return_value={"has_content": True, "pending_requests": 5, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={
                    "active_count": 3,
                    "total_spawned": 3,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
                "src.simulation.workflows.orchestrator_workflow.set_current_iteration_step",
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 3, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={
                    "turns_dispatched": 3,
                    "iterations": 1,
                },
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.read_iteration_skip_count_step",
                return_value=3,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.set_run_status_step",
            ) as mock_set_status,
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
            mock_dbos.workflow_id = "wf-test-skip-empty"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_set_status.assert_called_once_with(run_id, "paused", expected_status="running")
        assert result["status"] == "cancelled"

    def test_some_agents_not_skipped_does_not_increment(self) -> None:
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
                return_value={"has_content": True, "pending_requests": 5, "unrated_notes": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.get_population_snapshot_step",
                return_value={
                    "active_count": 3,
                    "total_spawned": 3,
                    "total_removed_for_cause": 0,
                    "total_removed_by_rate": 0,
                },
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
                "src.simulation.workflows.orchestrator_workflow.set_current_iteration_step",
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.schedule_turns_step",
                return_value={"dispatched_count": 3, "skipped_count": 0},
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.update_metrics_step",
                return_value={
                    "turns_dispatched": 3,
                    "iterations": 1,
                },
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.read_iteration_skip_count_step",
                return_value=1,
            ),
            patch(
                "src.simulation.workflows.orchestrator_workflow.set_run_status_step",
            ) as mock_set_status,
            patch(
                "src.simulation.workflows.orchestrator_workflow.finalize_run_step",
                return_value={"final_status": "cancelled", "instances_finalized": 0},
            ),
            patch("src.simulation.workflows.orchestrator_workflow.DBOS") as mock_dbos,
            patch("src.simulation.workflows.orchestrator_workflow.TokenGate"),
        ):
            mock_dbos.workflow_id = "wf-test-partial-skip"

            result = run_orchestrator.__wrapped__(simulation_run_id=run_id)

        mock_set_status.assert_not_called()
        assert result["status"] == "cancelled"
