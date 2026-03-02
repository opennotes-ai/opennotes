from uuid import uuid4

import pendulum
import pytest
from sqlalchemy import select

from src.simulation.models import (
    SimAgent,
    SimAgentInstance,
    SimAgentRunLog,
    SimulationOrchestrator,
    SimulationRun,
    SimulationRunConfig,
)
from src.simulation.restart import RestartSnapshot, snapshot_restart_state


async def _setup_run(db, *, restart_count=0, scoring_config=None):
    from src.llm_config.models import CommunityServer

    cs = CommunityServer(
        platform="discord",
        platform_community_server_id=f"guild-{uuid4().hex[:8]}",
        name=f"RestartGuild-{uuid4().hex[:6]}",
    )
    db.add(cs)
    await db.flush()

    orch = SimulationOrchestrator(
        name=f"orch-{uuid4().hex[:8]}",
        max_turns_per_agent=50,
        turn_cadence_seconds=30,
        max_agents=5,
        removal_rate=0.2,
        scoring_config=scoring_config,
    )
    db.add(orch)
    await db.flush()

    now = pendulum.now("UTC")
    run = SimulationRun(
        orchestrator_id=orch.id,
        community_server_id=cs.id,
        status="running",
        restart_count=restart_count,
        started_at=now.subtract(hours=1),
    )
    db.add(run)
    await db.flush()

    return run, orch, cs


async def _add_agent_instance(db, run, *, state="active", turn_count=10):
    from src.users.profile_models import UserProfile

    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="test personality",
        model_name="gpt-4o",
    )
    db.add(agent)
    await db.flush()

    profile = UserProfile(display_name=f"sim-{uuid4().hex[:6]}", is_human=False)
    db.add(profile)
    await db.flush()

    inst = SimAgentInstance(
        simulation_run_id=run.id,
        agent_profile_id=agent.id,
        user_profile_id=profile.id,
        state=state,
        turn_count=turn_count,
    )
    db.add(inst)
    await db.flush()
    return inst


@pytest.mark.asyncio
async def test_snapshot_creates_config_entry(db):
    run, orch, _ = await _setup_run(db, scoring_config={"scorer": "bayesian"})
    await _add_agent_instance(db, run)

    result = await snapshot_restart_state(db, run.id)

    assert isinstance(result, RestartSnapshot)
    assert result.config_id is not None

    config = (
        await db.execute(
            select(SimulationRunConfig).where(SimulationRunConfig.id == result.config_id)
        )
    ).scalar_one()

    assert config.simulation_run_id == run.id
    assert config.restart_number == run.restart_count
    assert config.max_turns_per_agent == orch.max_turns_per_agent
    assert config.turn_cadence_seconds == orch.turn_cadence_seconds
    assert config.max_agents == orch.max_agents
    assert config.removal_rate == pytest.approx(orch.removal_rate)
    assert config.scoring_config == {"scorer": "bayesian"}


@pytest.mark.asyncio
async def test_snapshot_creates_agent_run_logs(db):
    run, _, _ = await _setup_run(db)
    await _add_agent_instance(db, run, state="active", turn_count=10)
    await _add_agent_instance(db, run, state="paused", turn_count=5)

    result = await snapshot_restart_state(db, run.id)

    assert len(result.log_ids) == 2

    for log_id in result.log_ids:
        log = (
            await db.execute(select(SimAgentRunLog).where(SimAgentRunLog.id == log_id))
        ).scalar_one()
        assert log.simulation_run_id == run.id
        assert log.restart_number == run.restart_count


@pytest.mark.asyncio
async def test_snapshot_excludes_removed_agents(db):
    run, _, _ = await _setup_run(db)
    await _add_agent_instance(db, run, state="active", turn_count=10)
    await _add_agent_instance(db, run, state="removed", turn_count=3)
    await _add_agent_instance(db, run, state="completed", turn_count=20)

    result = await snapshot_restart_state(db, run.id)

    assert len(result.log_ids) == 2


@pytest.mark.asyncio
async def test_snapshot_captures_agent_state_and_turns(db):
    run, _, _ = await _setup_run(db)
    inst = await _add_agent_instance(db, run, state="active", turn_count=42)

    result = await snapshot_restart_state(db, run.id)

    log = (
        await db.execute(select(SimAgentRunLog).where(SimAgentRunLog.id == result.log_ids[0]))
    ).scalar_one()

    assert log.agent_instance_id == inst.id
    assert log.turns_in_segment == 42
    assert log.state_at_end == "active"
    assert log.started_at == run.started_at
    assert log.completed_at == run.completed_at


@pytest.mark.asyncio
async def test_snapshot_with_nonzero_restart_count(db):
    run, _orch, _ = await _setup_run(db, restart_count=3)
    await _add_agent_instance(db, run, state="active", turn_count=7)

    result = await snapshot_restart_state(db, run.id)

    config = (
        await db.execute(
            select(SimulationRunConfig).where(SimulationRunConfig.id == result.config_id)
        )
    ).scalar_one()
    assert config.restart_number == 3

    log = (
        await db.execute(select(SimAgentRunLog).where(SimAgentRunLog.id == result.log_ids[0]))
    ).scalar_one()
    assert log.restart_number == 3


@pytest.mark.asyncio
async def test_snapshot_with_no_agents(db):
    run, _, _ = await _setup_run(db)

    result = await snapshot_restart_state(db, run.id)

    assert result.config_id is not None
    assert result.log_ids == []


@pytest.mark.asyncio
async def test_snapshot_returns_correct_ids_for_fk_linkage(db):
    run, _, _ = await _setup_run(db)
    await _add_agent_instance(db, run, state="active", turn_count=5)

    result = await snapshot_restart_state(db, run.id)

    assert (
        await db.execute(
            select(SimulationRunConfig).where(SimulationRunConfig.id == result.config_id)
        )
    ).scalar_one() is not None

    for log_id in result.log_ids:
        assert (
            await db.execute(select(SimAgentRunLog).where(SimAgentRunLog.id == log_id))
        ).scalar_one() is not None
