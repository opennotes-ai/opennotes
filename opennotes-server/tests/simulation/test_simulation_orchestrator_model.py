from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_create_orchestrator_defaults(db):
    from src.simulation.models import SimulationOrchestrator

    orch = SimulationOrchestrator(name=f"test-orch-{uuid4().hex[:8]}")
    db.add(orch)
    await db.flush()
    orch_id = orch.id
    await db.commit()

    result = await db.execute(
        select(SimulationOrchestrator).where(SimulationOrchestrator.id == orch_id)
    )
    row = result.scalar_one()
    assert row.turn_cadence_seconds == 60
    assert row.max_agents == 10
    assert row.removal_rate == 0.0
    assert row.max_turns_per_agent == 100
    assert row.is_active is True
    assert row.community_server_id is None
    assert row.deleted_at is None


@pytest.mark.asyncio
async def test_orchestrator_name_unique(db):
    from src.simulation.models import SimulationOrchestrator

    name = f"dup-orch-{uuid4().hex[:8]}"
    db.add(SimulationOrchestrator(name=name))
    await db.commit()

    db.add(SimulationOrchestrator(name=name))
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_orchestrator_soft_delete(db):
    from src.simulation.models import SimulationOrchestrator

    orch = SimulationOrchestrator(name=f"del-orch-{uuid4().hex[:8]}")
    db.add(orch)
    await db.flush()
    orch.soft_delete()
    await db.commit()
    assert orch.is_deleted is True
    assert orch.deleted_at is not None


@pytest.mark.asyncio
async def test_orchestrator_community_server_fk(db, playground_community_server):
    from src.simulation.models import SimulationOrchestrator

    orch = SimulationOrchestrator(
        name=f"linked-orch-{uuid4().hex[:8]}",
        community_server_id=playground_community_server,
    )
    db.add(orch)
    await db.commit()
    await db.refresh(orch)
    assert orch.community_server_id == playground_community_server


@pytest.mark.asyncio
async def test_orchestrator_check_constraints_removal_rate(db):
    from src.simulation.models import SimulationOrchestrator

    orch = SimulationOrchestrator(name=f"bad-rate-{uuid4().hex[:8]}", removal_rate=1.5)
    db.add(orch)
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_orchestrator_check_constraints_cadence(db):
    from src.simulation.models import SimulationOrchestrator

    orch = SimulationOrchestrator(name=f"bad-cadence-{uuid4().hex[:8]}", turn_cadence_seconds=0)
    db.add(orch)
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_orchestrator_jsonb_fields(db):
    from src.simulation.models import SimulationOrchestrator

    profile_ids = [str(uuid4()), str(uuid4())]
    scoring = {"target_tier": "FULL", "scorers": ["matrix_factorization"]}
    orch = SimulationOrchestrator(
        name=f"jsonb-orch-{uuid4().hex[:8]}",
        agent_profile_ids=profile_ids,
        scoring_config=scoring,
    )
    db.add(orch)
    await db.flush()
    orch_id = orch.id
    await db.commit()

    result = await db.execute(
        select(SimulationOrchestrator).where(SimulationOrchestrator.id == orch_id)
    )
    row = result.scalar_one()
    assert row.agent_profile_ids == profile_ids
    assert row.scoring_config == scoring
