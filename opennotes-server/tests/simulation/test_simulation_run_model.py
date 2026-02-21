from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError


async def _create_orchestrator_and_cs(db):
    from src.llm_config.models import CommunityServer
    from src.simulation.models import SimulationOrchestrator

    cs = CommunityServer(
        platform="discord",
        platform_community_server_id=f"guild-{uuid4().hex[:8]}",
        name=f"RunGuild-{uuid4().hex[:6]}",
    )
    db.add(cs)
    await db.flush()
    orch = SimulationOrchestrator(name=f"orch-{uuid4().hex[:8]}")
    db.add(orch)
    await db.flush()
    return orch, cs


@pytest.mark.asyncio
async def test_create_simulation_run(db):
    from src.simulation.models import SimulationRun

    orch, cs = await _create_orchestrator_and_cs(db)
    run = SimulationRun(
        orchestrator_id=orch.id,
        community_server_id=cs.id,
    )
    db.add(run)
    await db.flush()
    run_id = run.id
    await db.commit()

    result = await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))
    row = result.scalar_one()
    assert row.status == "pending"
    assert row.started_at is None
    assert row.completed_at is None
    assert row.error_message is None


@pytest.mark.asyncio
async def test_simulation_run_status_check_constraint(db):
    from src.simulation.models import SimulationRun

    orch, cs = await _create_orchestrator_and_cs(db)
    run = SimulationRun(
        orchestrator_id=orch.id,
        community_server_id=cs.id,
        status="invalid_status",
    )
    db.add(run)
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_simulation_run_metrics_jsonb(db):
    from src.simulation.models import SimulationRun

    orch, cs = await _create_orchestrator_and_cs(db)
    metrics = {
        "total_turns": 42,
        "notes_created": 10,
        "ratings_created": 25,
        "scores_computed": 3,
    }
    run = SimulationRun(
        orchestrator_id=orch.id,
        community_server_id=cs.id,
        metrics=metrics,
    )
    db.add(run)
    await db.flush()
    run_id = run.id
    await db.commit()

    result = await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))
    row = result.scalar_one()
    assert row.metrics == metrics


@pytest.mark.asyncio
async def test_simulation_run_config_snapshot(db):
    from src.simulation.models import SimulationRun

    orch, cs = await _create_orchestrator_and_cs(db)
    snapshot = {"turn_cadence_seconds": 60, "max_agents": 10, "removal_rate": 0.1}
    run = SimulationRun(
        orchestrator_id=orch.id,
        community_server_id=cs.id,
        config_snapshot=snapshot,
    )
    db.add(run)
    await db.flush()
    run_id = run.id
    await db.commit()

    result = await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))
    row = result.scalar_one()
    assert row.config_snapshot == snapshot


@pytest.mark.asyncio
async def test_simulation_run_soft_delete(db):
    from src.simulation.models import SimulationRun

    orch, cs = await _create_orchestrator_and_cs(db)
    run = SimulationRun(
        orchestrator_id=orch.id,
        community_server_id=cs.id,
    )
    db.add(run)
    await db.flush()
    run.soft_delete()
    await db.commit()
    assert run.is_deleted is True


@pytest.mark.asyncio
async def test_simulation_run_orchestrator_fk_restrict(db):
    from src.simulation.models import SimulationOrchestrator, SimulationRun

    orch, cs = await _create_orchestrator_and_cs(db)
    run = SimulationRun(orchestrator_id=orch.id, community_server_id=cs.id)
    db.add(run)
    await db.commit()

    await db.execute(delete(SimulationOrchestrator).where(SimulationOrchestrator.id == orch.id))
    with pytest.raises(IntegrityError):
        await db.commit()
