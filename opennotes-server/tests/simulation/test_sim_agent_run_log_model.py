from uuid import uuid4

import pendulum
import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_create_sim_agent_run_log_defaults(db):
    from src.simulation.models import SimAgentRunLog

    log = SimAgentRunLog(
        agent_instance_id=uuid4(),
        simulation_run_id=uuid4(),
        restart_number=0,
        state_at_end="active",
    )
    db.add(log)
    await db.flush()
    log_id = log.id
    await db.commit()

    result = await db.execute(select(SimAgentRunLog).where(SimAgentRunLog.id == log_id))
    row = result.scalar_one()
    assert row.turns_in_segment == 0
    assert row.state_at_end == "active"
    assert row.started_at is None
    assert row.completed_at is None
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_sim_agent_run_log_with_timestamps(db):
    from src.simulation.models import SimAgentRunLog

    now = pendulum.now("UTC")
    log = SimAgentRunLog(
        agent_instance_id=uuid4(),
        simulation_run_id=uuid4(),
        restart_number=1,
        turns_in_segment=42,
        state_at_end="completed",
        started_at=now.subtract(hours=1),
        completed_at=now,
    )
    db.add(log)
    await db.flush()
    log_id = log.id
    await db.commit()

    result = await db.execute(select(SimAgentRunLog).where(SimAgentRunLog.id == log_id))
    row = result.scalar_one()
    assert row.turns_in_segment == 42
    assert row.state_at_end == "completed"
    assert row.started_at is not None
    assert row.completed_at is not None
    assert row.restart_number == 1


@pytest.mark.asyncio
async def test_sim_agent_run_log_multiple_per_instance(db):
    from src.simulation.models import SimAgentRunLog

    instance_id = uuid4()
    run_id = uuid4()

    log1 = SimAgentRunLog(
        agent_instance_id=instance_id,
        simulation_run_id=run_id,
        restart_number=0,
        turns_in_segment=10,
        state_at_end="paused",
    )
    log2 = SimAgentRunLog(
        agent_instance_id=instance_id,
        simulation_run_id=run_id,
        restart_number=1,
        turns_in_segment=15,
        state_at_end="completed",
    )
    db.add_all([log1, log2])
    await db.flush()
    await db.commit()

    result = await db.execute(
        select(SimAgentRunLog).where(SimAgentRunLog.agent_instance_id == instance_id)
    )
    rows = result.scalars().all()
    assert len(rows) == 2


async def _create_run_with_deps(db):
    from src.llm_config.models import CommunityServer
    from src.simulation.models import SimulationOrchestrator, SimulationRun

    cs = CommunityServer(
        platform="discord",
        platform_community_server_id=f"guild-{uuid4().hex[:8]}",
        name=f"LogGuild-{uuid4().hex[:6]}",
    )
    db.add(cs)
    await db.flush()
    orch = SimulationOrchestrator(name=f"orch-{uuid4().hex[:8]}")
    db.add(orch)
    await db.flush()
    run = SimulationRun(orchestrator_id=orch.id, community_server_id=cs.id)
    db.add(run)
    await db.flush()
    return run, cs


@pytest.mark.asyncio
async def test_sim_agent_instance_cumulative_turn_count_default(db):
    from src.simulation.models import SimAgent, SimAgentInstance
    from src.users.profile_models import UserProfile

    run, _ = await _create_run_with_deps(db)
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="tester",
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
    )
    db.add(inst)
    await db.flush()
    inst_id = inst.id
    await db.commit()

    result = await db.execute(select(SimAgentInstance).where(SimAgentInstance.id == inst_id))
    row = result.scalar_one()
    assert row.cumulative_turn_count == 0
    assert row.current_run_log_id is None


@pytest.mark.asyncio
async def test_sim_agent_instance_current_run_log_fk(db):
    from src.simulation.models import SimAgent, SimAgentInstance, SimAgentRunLog
    from src.users.profile_models import UserProfile

    run, _ = await _create_run_with_deps(db)
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="fk-tester",
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
    )
    db.add(inst)
    await db.flush()

    log = SimAgentRunLog(
        agent_instance_id=inst.id,
        simulation_run_id=run.id,
        restart_number=0,
        state_at_end="active",
    )
    db.add(log)
    await db.flush()

    inst.current_run_log_id = log.id
    await db.flush()
    inst_id = inst.id
    await db.commit()

    result = await db.execute(select(SimAgentInstance).where(SimAgentInstance.id == inst_id))
    row = result.scalar_one()
    assert row.current_run_log_id == log.id
