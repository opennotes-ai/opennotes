from uuid import uuid4

import pytest
from sqlalchemy import select


async def _create_orchestrator_and_cs(db):
    from src.llm_config.models import CommunityServer
    from src.simulation.models import SimulationOrchestrator

    cs = CommunityServer(
        platform="discord",
        platform_community_server_id=f"guild-{uuid4().hex[:8]}",
        name=f"CfgGuild-{uuid4().hex[:6]}",
    )
    db.add(cs)
    await db.flush()
    orch = SimulationOrchestrator(name=f"orch-{uuid4().hex[:8]}")
    db.add(orch)
    await db.flush()
    return orch, cs


@pytest.mark.asyncio
async def test_create_simulation_run_config_defaults(db):
    from src.simulation.models import SimulationRunConfig

    config = SimulationRunConfig(
        simulation_run_id=uuid4(),
        max_turns_per_agent=100,
        turn_cadence_seconds=60,
        max_agents=10,
        removal_rate=0.1,
    )
    db.add(config)
    await db.flush()
    config_id = config.id
    await db.commit()

    result = await db.execute(
        select(SimulationRunConfig).where(SimulationRunConfig.id == config_id)
    )
    row = result.scalar_one()
    assert row.restart_number == 0
    assert row.max_turns_per_agent == 100
    assert row.turn_cadence_seconds == 60
    assert row.max_agents == 10
    assert row.removal_rate == pytest.approx(0.1)
    assert row.scoring_config is None
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_simulation_run_config_with_scoring_config(db):
    from src.simulation.models import SimulationRunConfig

    scoring = {"scorer": "bayesian", "threshold": 0.5}
    config = SimulationRunConfig(
        simulation_run_id=uuid4(),
        max_turns_per_agent=50,
        turn_cadence_seconds=30,
        max_agents=5,
        removal_rate=0.0,
        scoring_config=scoring,
    )
    db.add(config)
    await db.flush()
    config_id = config.id
    await db.commit()

    result = await db.execute(
        select(SimulationRunConfig).where(SimulationRunConfig.id == config_id)
    )
    row = result.scalar_one()
    assert row.scoring_config == scoring


@pytest.mark.asyncio
async def test_simulation_run_config_restart_number(db):
    from src.simulation.models import SimulationRunConfig

    run_id = uuid4()
    config = SimulationRunConfig(
        simulation_run_id=run_id,
        restart_number=3,
        max_turns_per_agent=100,
        turn_cadence_seconds=60,
        max_agents=10,
        removal_rate=0.1,
    )
    db.add(config)
    await db.flush()
    config_id = config.id
    await db.commit()

    result = await db.execute(
        select(SimulationRunConfig).where(SimulationRunConfig.id == config_id)
    )
    row = result.scalar_one()
    assert row.restart_number == 3
    assert row.simulation_run_id == run_id


@pytest.mark.asyncio
async def test_simulation_run_current_config_fk(db):
    from src.simulation.models import SimulationRun, SimulationRunConfig

    orch, cs = await _create_orchestrator_and_cs(db)
    run = SimulationRun(orchestrator_id=orch.id, community_server_id=cs.id)
    db.add(run)
    await db.flush()

    config = SimulationRunConfig(
        simulation_run_id=run.id,
        max_turns_per_agent=100,
        turn_cadence_seconds=60,
        max_agents=10,
        removal_rate=0.1,
    )
    db.add(config)
    await db.flush()

    run.current_config_id = config.id
    await db.flush()
    run_id = run.id
    await db.commit()

    result = await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))
    row = result.scalar_one()
    assert row.current_config_id == config.id


@pytest.mark.asyncio
async def test_simulation_run_cumulative_turns_default(db):
    from src.simulation.models import SimulationRun

    orch, cs = await _create_orchestrator_and_cs(db)
    run = SimulationRun(orchestrator_id=orch.id, community_server_id=cs.id)
    db.add(run)
    await db.flush()
    run_id = run.id
    await db.commit()

    result = await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))
    row = result.scalar_one()
    assert row.cumulative_turns == 0
    assert row.restart_count == 0
