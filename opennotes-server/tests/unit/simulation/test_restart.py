from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pendulum
import pytest

from src.simulation.models import (
    SimAgentRunLog,
    SimulationRunConfig,
)
from src.simulation.restart import RestartSnapshot, snapshot_restart_state


def _mock_orchestrator(**overrides: object) -> MagicMock:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "name": "test-orch",
        "max_turns_per_agent": 50,
        "turn_cadence_seconds": 30,
        "max_agents": 8,
        "removal_rate": 0.1,
        "scoring_config": {"scorer": "bayesian"},
        "is_active": True,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _mock_run(orchestrator: MagicMock, **overrides: object) -> MagicMock:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "orchestrator_id": orchestrator.id,
        "community_server_id": uuid4(),
        "status": "running",
        "restart_count": 2,
        "cumulative_turns": 100,
        "started_at": pendulum.now("UTC").subtract(hours=1),
        "completed_at": None,
        "orchestrator": orchestrator,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _mock_agent_instance(**overrides: object) -> MagicMock:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "simulation_run_id": uuid4(),
        "agent_profile_id": uuid4(),
        "user_profile_id": uuid4(),
        "state": "active",
        "turn_count": 10,
        "cumulative_turn_count": 25,
        "retry_count": 0,
        "last_turn_at": None,
        "removal_reason": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _mock_scalar_one(obj: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = obj
    return result


def _mock_scalars_all(items: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _build_session(
    run: MagicMock,
    agents: list[MagicMock],
) -> AsyncMock:
    session = AsyncMock()
    added_objects: list[object] = []

    session.execute = AsyncMock(
        side_effect=[
            _mock_scalar_one(run),
            _mock_scalars_all(agents),
        ]
    )

    def track_add(obj: object) -> None:
        added_objects.append(obj)

    session.add = MagicMock(side_effect=track_add)

    async def assign_ids_on_flush() -> None:
        for obj in added_objects:
            if getattr(obj, "id", None) is None:
                object.__setattr__(obj, "id", uuid4())

    session.flush = AsyncMock(side_effect=assign_ids_on_flush)
    session._added_objects = added_objects
    return session


class TestSnapshotCreatesRunConfig:
    @pytest.mark.asyncio
    async def test_creates_config_with_orchestrator_settings(self) -> None:
        orch = _mock_orchestrator(
            max_turns_per_agent=50,
            turn_cadence_seconds=30,
            max_agents=8,
            removal_rate=0.1,
            scoring_config={"scorer": "bayesian"},
        )
        run = _mock_run(orch, restart_count=2)
        session = _build_session(run, [])

        await snapshot_restart_state(session, run.id)

        added_configs = [o for o in session._added_objects if isinstance(o, SimulationRunConfig)]
        assert len(added_configs) == 1
        config = added_configs[0]
        assert config.simulation_run_id == run.id
        assert config.restart_number == 2
        assert config.max_turns_per_agent == 50
        assert config.turn_cadence_seconds == 30
        assert config.max_agents == 8
        assert config.removal_rate == 0.1
        assert config.scoring_config == {"scorer": "bayesian"}

    @pytest.mark.asyncio
    async def test_config_captures_null_scoring_config(self) -> None:
        orch = _mock_orchestrator(scoring_config=None)
        run = _mock_run(orch)
        session = _build_session(run, [])

        await snapshot_restart_state(session, run.id)

        added_configs = [o for o in session._added_objects if isinstance(o, SimulationRunConfig)]
        assert added_configs[0].scoring_config is None


class TestSnapshotCreatesAgentRunLogs:
    @pytest.mark.asyncio
    async def test_creates_log_for_each_non_removed_agent(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch, restart_count=3)
        agents = [
            _mock_agent_instance(simulation_run_id=run.id, state="active", turn_count=10),
            _mock_agent_instance(simulation_run_id=run.id, state="paused", turn_count=5),
        ]
        session = _build_session(run, agents)

        result = await snapshot_restart_state(session, run.id)

        logs = [o for o in session._added_objects if isinstance(o, SimAgentRunLog)]
        assert len(logs) == 2
        assert len(result.log_ids) == 2

    @pytest.mark.asyncio
    async def test_excluded_removed_agents_from_logs(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch)
        active_agent = _mock_agent_instance(simulation_run_id=run.id, state="active", turn_count=10)
        session = _build_session(run, [active_agent])

        await snapshot_restart_state(session, run.id)

        logs = [o for o in session._added_objects if isinstance(o, SimAgentRunLog)]
        assert len(logs) == 1
        assert logs[0].agent_instance_id == active_agent.id

    @pytest.mark.asyncio
    async def test_turns_in_segment_captures_agent_turn_count(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch)
        agent = _mock_agent_instance(simulation_run_id=run.id, state="active", turn_count=42)
        session = _build_session(run, [agent])

        await snapshot_restart_state(session, run.id)

        logs = [o for o in session._added_objects if isinstance(o, SimAgentRunLog)]
        assert logs[0].turns_in_segment == 42

    @pytest.mark.asyncio
    async def test_state_at_end_captures_agent_state(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch)
        agent = _mock_agent_instance(simulation_run_id=run.id, state="paused", turn_count=7)
        session = _build_session(run, [agent])

        await snapshot_restart_state(session, run.id)

        logs = [o for o in session._added_objects if isinstance(o, SimAgentRunLog)]
        assert logs[0].state_at_end == "paused"

    @pytest.mark.asyncio
    async def test_log_restart_number_matches_run(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch, restart_count=5)
        agent = _mock_agent_instance(simulation_run_id=run.id, state="active", turn_count=1)
        session = _build_session(run, [agent])

        await snapshot_restart_state(session, run.id)

        logs = [o for o in session._added_objects if isinstance(o, SimAgentRunLog)]
        assert logs[0].restart_number == 5

    @pytest.mark.asyncio
    async def test_log_timestamps_from_run(self) -> None:
        orch = _mock_orchestrator()
        started = pendulum.now("UTC").subtract(hours=2)
        completed = pendulum.now("UTC")
        run = _mock_run(orch, started_at=started, completed_at=completed)
        agent = _mock_agent_instance(simulation_run_id=run.id, state="active", turn_count=1)
        session = _build_session(run, [agent])

        await snapshot_restart_state(session, run.id)

        logs = [o for o in session._added_objects if isinstance(o, SimAgentRunLog)]
        assert logs[0].started_at == started
        assert logs[0].completed_at == completed


class TestSnapshotReturnValue:
    @pytest.mark.asyncio
    async def test_returns_restart_snapshot(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch)
        agent = _mock_agent_instance(simulation_run_id=run.id, state="active", turn_count=1)
        session = _build_session(run, [agent])

        result = await snapshot_restart_state(session, run.id)

        assert isinstance(result, RestartSnapshot)

    @pytest.mark.asyncio
    async def test_config_id_matches_created_config(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch)
        session = _build_session(run, [])

        result = await snapshot_restart_state(session, run.id)

        configs = [o for o in session._added_objects if isinstance(o, SimulationRunConfig)]
        assert result.config_id == configs[0].id

    @pytest.mark.asyncio
    async def test_log_ids_match_created_logs(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch)
        agents = [
            _mock_agent_instance(simulation_run_id=run.id, state="active", turn_count=i)
            for i in range(3)
        ]
        session = _build_session(run, agents)

        result = await snapshot_restart_state(session, run.id)

        logs = [o for o in session._added_objects if isinstance(o, SimAgentRunLog)]
        assert result.log_ids == [log.id for log in logs]

    @pytest.mark.asyncio
    async def test_empty_log_ids_when_no_agents(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch)
        session = _build_session(run, [])

        result = await snapshot_restart_state(session, run.id)

        assert result.log_ids == []


class TestSnapshotFlushBehavior:
    @pytest.mark.asyncio
    async def test_flush_called_for_config_and_each_agent(self) -> None:
        orch = _mock_orchestrator()
        run = _mock_run(orch)
        agents = [
            _mock_agent_instance(simulation_run_id=run.id, state="active", turn_count=i)
            for i in range(2)
        ]
        session = _build_session(run, agents)

        await snapshot_restart_state(session, run.id)

        assert session.flush.call_count == 3
