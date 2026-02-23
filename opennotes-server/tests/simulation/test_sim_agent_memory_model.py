from uuid import uuid4

import pytest
from sqlalchemy import select


async def _create_agent_instance(db):
    from src.llm_config.models import CommunityServer
    from src.simulation.models import (
        SimAgent,
        SimAgentInstance,
        SimulationOrchestrator,
        SimulationRun,
    )
    from src.users.profile_models import UserProfile

    cs = CommunityServer(
        platform="discord",
        platform_community_server_id=f"guild-{uuid4().hex[:8]}",
        name=f"MemGuild-{uuid4().hex[:6]}",
    )
    db.add(cs)
    await db.flush()
    orch = SimulationOrchestrator(name=f"orch-{uuid4().hex[:8]}")
    db.add(orch)
    await db.flush()
    run = SimulationRun(orchestrator_id=orch.id, community_server_id=cs.id)
    db.add(run)
    await db.flush()
    agent = SimAgent(
        name=f"agent-{uuid4().hex[:8]}",
        personality="test",
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
    return inst.id


@pytest.mark.asyncio
async def test_create_sim_agent_memory(db):
    from src.simulation.models import SimAgentMemory

    instance_id = await _create_agent_instance(db)
    memory = SimAgentMemory(
        agent_instance_id=instance_id,
        message_history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ],
        turn_count=2,
        token_count=50,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    result = await db.execute(select(SimAgentMemory).where(SimAgentMemory.id == memory.id))
    row = result.scalar_one()
    assert len(row.message_history) == 2
    assert row.turn_count == 2
    assert row.token_count == 50
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_sim_agent_memory_compaction_metadata(db):
    import pendulum

    from src.simulation.models import SimAgentMemory

    instance_id = await _create_agent_instance(db)
    now = pendulum.now("UTC")
    memory = SimAgentMemory(
        agent_instance_id=instance_id,
        message_history=[],
        turn_count=10,
        last_compacted_at=now,
        compaction_strategy="sliding_window",
        token_count=500,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    result = await db.execute(select(SimAgentMemory).where(SimAgentMemory.id == memory.id))
    row = result.scalar_one()
    assert row.last_compacted_at is not None
    assert row.compaction_strategy == "sliding_window"
    assert row.token_count == 500


@pytest.mark.asyncio
async def test_sim_agent_memory_default_values(db):
    from src.simulation.models import SimAgentMemory

    instance_id = await _create_agent_instance(db)
    memory = SimAgentMemory(
        agent_instance_id=instance_id,
    )
    db.add(memory)
    await db.flush()
    await db.refresh(memory)

    assert memory.turn_count == 0
    assert memory.token_count == 0
    assert memory.last_compacted_at is None
    assert memory.compaction_strategy is None
    assert memory.message_history == []


@pytest.mark.asyncio
async def test_sim_agent_memory_message_history_stores_jsonb(db):
    from src.simulation.models import SimAgentMemory

    instance_id = await _create_agent_instance(db)
    messages = [
        {
            "kind": "request",
            "parts": [{"part_kind": "user-prompt", "content": "What is 2+2?"}],
        },
        {
            "kind": "response",
            "parts": [{"part_kind": "text", "content": "4"}],
            "model_name": "gpt-4o",
        },
    ]
    memory = SimAgentMemory(
        agent_instance_id=instance_id,
        message_history=messages,
        turn_count=1,
        token_count=20,
    )
    db.add(memory)
    await db.commit()

    result = await db.execute(select(SimAgentMemory).where(SimAgentMemory.id == memory.id))
    row = result.scalar_one()
    assert row.message_history == messages
    assert row.message_history[0]["kind"] == "request"
    assert row.message_history[1]["model_name"] == "gpt-4o"
