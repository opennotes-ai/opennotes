from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_create_sim_agent_profile(db):
    from src.simulation.models import SimAgent

    agent = SimAgent(
        name=f"test-agent-{uuid4().hex[:8]}",
        personality="You are a helpful community member who writes balanced notes.",
        model_name="gpt-4o",
        model_params={"temperature": 0.7, "max_tokens": 1024},
        tool_config={"allowed_tools": ["write_note", "rate_note"]},
        memory_compaction_strategy="sliding_window",
        memory_compaction_config={"window_size": 20},
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    result = await db.execute(select(SimAgent).where(SimAgent.id == agent.id))
    row = result.scalar_one()
    assert row.name == agent.name
    assert row.personality == "You are a helpful community member who writes balanced notes."
    assert row.model_name == "gpt-4o"
    assert row.model_params == {"temperature": 0.7, "max_tokens": 1024}
    assert row.tool_config == {"allowed_tools": ["write_note", "rate_note"]}
    assert row.memory_compaction_strategy == "sliding_window"
    assert row.memory_compaction_config == {"window_size": 20}
    assert row.created_at is not None
    assert row.deleted_at is None


@pytest.mark.asyncio
async def test_sim_agent_name_unique(db):
    from src.simulation.models import SimAgent

    name = f"unique-agent-{uuid4().hex[:8]}"
    agent1 = SimAgent(name=name, personality="p1", model_name="gpt-4o")
    db.add(agent1)
    await db.commit()

    agent2 = SimAgent(name=name, personality="p2", model_name="gpt-4o")
    db.add(agent2)
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_sim_agent_soft_delete(db):
    from src.simulation.models import SimAgent

    agent = SimAgent(
        name=f"soft-del-{uuid4().hex[:8]}",
        personality="deletable",
        model_name="gpt-4o",
    )
    db.add(agent)
    await db.flush()
    agent.soft_delete()
    await db.commit()
    assert agent.is_deleted is True
    assert agent.deleted_at is not None
