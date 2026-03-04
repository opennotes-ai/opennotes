from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pendulum
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.simulation.models import (
    SimAgentInstance,
    SimAgentRunLog,
    SimulationOrchestrator,
    SimulationRun,
    SimulationRunConfig,
)

REMOVAL_RATE = "removal_rate"
MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
SIMULATION_CANCELLED = "simulation_cancelled"
SIMULATION_COMPLETED = "simulation_completed"

RESTARTABLE_REMOVAL_REASONS: frozenset[str] = frozenset(
    {REMOVAL_RATE, SIMULATION_COMPLETED, SIMULATION_CANCELLED, MAX_RETRIES_EXCEEDED}
)
FOR_CAUSE_REMOVAL_REASONS: frozenset[str] = frozenset({MAX_RETRIES_EXCEEDED})


def restartable_agents_filter(simulation_run_id: UUID):
    return and_(
        SimAgentInstance.simulation_run_id == simulation_run_id,
        or_(
            SimAgentInstance.state != "removed",
            SimAgentInstance.removal_reason.in_(RESTARTABLE_REMOVAL_REASONS),
        ),
    )


@dataclass
class RestartSnapshot:
    config_id: UUID
    log_ids: list[UUID]


async def snapshot_restart_state(
    session: AsyncSession,
    simulation_run_id: UUID,
) -> RestartSnapshot:
    run_result = await session.execute(
        select(SimulationRun)
        .options(selectinload(SimulationRun.orchestrator))
        .where(SimulationRun.id == simulation_run_id)
    )
    run = run_result.scalar_one()
    orch: SimulationOrchestrator = run.orchestrator

    config = SimulationRunConfig(
        simulation_run_id=simulation_run_id,
        restart_number=run.restart_count,
        max_turns_per_agent=orch.max_turns_per_agent,
        turn_cadence_seconds=orch.turn_cadence_seconds,
        max_agents=orch.max_agents,
        removal_rate=orch.removal_rate,
        scoring_config=orch.scoring_config,
    )
    session.add(config)
    await session.flush()

    instances_result = await session.execute(
        select(SimAgentInstance).where(restartable_agents_filter(simulation_run_id))
    )
    log_ids: list[UUID] = []
    for inst in instances_result.scalars().all():
        log = SimAgentRunLog(
            agent_instance_id=inst.id,
            simulation_run_id=simulation_run_id,
            restart_number=run.restart_count,
            turns_in_segment=inst.turn_count,
            state_at_end=inst.state,
            started_at=run.started_at,
            completed_at=run.completed_at or pendulum.now("UTC"),
        )
        session.add(log)
        await session.flush()
        log_ids.append(log.id)

        await session.execute(
            update(SimAgentInstance)
            .where(SimAgentInstance.id == inst.id)
            .values(current_run_log_id=log.id)
        )

    return RestartSnapshot(config_id=config.id, log_ids=log_ids)
