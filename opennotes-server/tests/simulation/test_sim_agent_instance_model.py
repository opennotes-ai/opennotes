from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError


async def _create_run_with_deps(db):
    from src.llm_config.models import CommunityServer
    from src.simulation.models import SimulationOrchestrator, SimulationRun

    cs = CommunityServer(
        platform="discord",
        platform_community_server_id=f"guild-{uuid4().hex[:8]}",
        name=f"TestGuild-{uuid4().hex[:6]}",
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
async def test_create_agent_instance(db):
    from src.simulation.models import SimAgent, SimAgentInstance
    from src.users.profile_models import UserProfile

    run, _ = await _create_run_with_deps(db)
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="helpful",
        model_name="gpt-4o",
    )
    db.add(agent)
    await db.flush()
    profile = UserProfile(display_name=f"sim-user-{uuid4().hex[:6]}", is_human=False)
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
    assert row.state == "active"
    assert row.turn_count == 0
    assert row.last_turn_at is None
    assert row.removal_reason is None


@pytest.mark.asyncio
async def test_agent_instance_state_check_constraint(db):
    from src.simulation.models import SimAgent, SimAgentInstance
    from src.users.profile_models import UserProfile

    run, _ = await _create_run_with_deps(db)
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="x",
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
        state="bogus",
    )
    db.add(inst)
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_agent_instance_cascade_delete_on_run(db):
    from src.simulation.models import SimAgent, SimAgentInstance, SimulationRun
    from src.users.profile_models import UserProfile

    run, _ = await _create_run_with_deps(db)
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="y",
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
    run_id = run.id
    await db.commit()

    await db.execute(delete(SimulationRun).where(SimulationRun.id == run_id))
    await db.commit()

    result = await db.execute(select(SimAgentInstance).where(SimAgentInstance.id == inst_id))
    row = result.scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_agent_instance_soft_delete(db):
    from src.simulation.models import SimAgent, SimAgentInstance
    from src.users.profile_models import UserProfile

    run, _ = await _create_run_with_deps(db)
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="z",
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
    inst.soft_delete()
    await db.commit()
    assert inst.is_deleted is True


@pytest.mark.asyncio
async def test_agent_instance_removal_reason(db):
    from src.simulation.models import SimAgent, SimAgentInstance
    from src.users.profile_models import UserProfile

    run, _ = await _create_run_with_deps(db)
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="w",
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
        state="removed",
        removal_reason="max_turns_reached",
    )
    db.add(inst)
    await db.flush()
    inst_id = inst.id
    await db.commit()

    result = await db.execute(select(SimAgentInstance).where(SimAgentInstance.id == inst_id))
    row = result.scalar_one()
    assert row.state == "removed"
    assert row.removal_reason == "max_turns_reached"


@pytest.mark.asyncio
async def test_agent_instance_turn_count_nonneg(db):
    from src.simulation.models import SimAgent, SimAgentInstance
    from src.users.profile_models import UserProfile

    run, _ = await _create_run_with_deps(db)
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="v",
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
        turn_count=-1,
    )
    db.add(inst)
    with pytest.raises(IntegrityError):
        await db.commit()
