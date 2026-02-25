from __future__ import annotations

import random
from typing import Any
from uuid import UUID

import pendulum
from dbos import DBOS, Queue
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from src.dbos_workflows.circuit_breaker import CircuitBreaker, CircuitOpenError
from src.dbos_workflows.token_bucket.config import WorkflowWeight
from src.dbos_workflows.token_bucket.gate import TokenGate
from src.monitoring import get_logger
from src.simulation.models import SimAgentInstance, SimulationOrchestrator, SimulationRun
from src.utils.async_compat import run_sync

logger = get_logger(__name__)

MAX_ITERATIONS: int = 10_000
MAX_TURN_RETRIES: int = 3
MAX_CONSECUTIVE_EMPTY: int = 10
SPAWN_BATCH_SIZE: int = 5
SCORING_INTERVAL: int = 10
CIRCUIT_BREAKER_THRESHOLD: int = 5
CIRCUIT_BREAKER_RESET_TIMEOUT: float = 300.0

simulation_orchestrator_queue = Queue(
    name="simulation_orchestrator",
    worker_concurrency=3,
    concurrency=6,
)


@DBOS.step(
    retries_allowed=True,
    max_attempts=3,
    interval_seconds=2.0,
    backoff_rate=2.0,
)
def initialize_run_step(simulation_run_id: str) -> dict[str, Any]:
    from src.database import get_session_maker

    async def _init() -> dict[str, Any]:
        run_uuid = UUID(simulation_run_id)
        now = pendulum.now("UTC")

        async with get_session_maker()() as session:
            atomic_update = (
                update(SimulationRun)
                .where(
                    SimulationRun.id == run_uuid,
                    SimulationRun.status.in_(["pending", "running"]),
                )
                .values(status="running", started_at=now)
                .returning(SimulationRun.id)
            )
            update_result = await session.execute(atomic_update)
            updated_id = update_result.scalar_one_or_none()

            if updated_id is None:
                check_result = await session.execute(
                    select(SimulationRun.status).where(SimulationRun.id == run_uuid)
                )
                existing_status = check_result.scalar_one_or_none()
                if existing_status is None:
                    raise ValueError(f"SimulationRun not found: {simulation_run_id}")
                raise ValueError(
                    f"SimulationRun {simulation_run_id} is '{existing_status}', "
                    f"expected 'pending' or 'running'"
                )

            run_query = (
                select(SimulationRun)
                .options(selectinload(SimulationRun.orchestrator))
                .where(SimulationRun.id == run_uuid)
            )
            run_result = await session.execute(run_query)
            run = run_result.scalar_one()
            orchestrator: SimulationOrchestrator = run.orchestrator

            await session.commit()

            return {
                "turn_cadence_seconds": orchestrator.turn_cadence_seconds,
                "max_agents": orchestrator.max_agents,
                "removal_rate": orchestrator.removal_rate,
                "max_turns_per_agent": orchestrator.max_turns_per_agent,
                "agent_profile_ids": orchestrator.agent_profile_ids or [],
                "community_server_id": str(run.community_server_id),
            }

    return run_sync(_init())


@DBOS.step(
    retries_allowed=True,
    max_attempts=3,
    interval_seconds=2.0,
    backoff_rate=2.0,
)
def check_run_status_step(simulation_run_id: str) -> str:
    from src.database import get_session_maker

    async def _check() -> str:
        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun.status).where(SimulationRun.id == UUID(simulation_run_id))
            )
            status = result.scalar_one_or_none()
            if status is None:
                raise ValueError(f"SimulationRun not found: {simulation_run_id}")
            return status

    return run_sync(_check())


@DBOS.step()
def get_population_snapshot_step(simulation_run_id: str) -> dict[str, int]:
    from src.database import get_session_maker

    async def _snapshot() -> dict[str, int]:
        run_uuid = UUID(simulation_run_id)
        async with get_session_maker()() as session:
            active_result = await session.execute(
                select(func.count()).where(
                    SimAgentInstance.simulation_run_id == run_uuid,
                    SimAgentInstance.state == "active",
                )
            )
            active_count = active_result.scalar() or 0

            total_result = await session.execute(
                select(func.count()).where(
                    SimAgentInstance.simulation_run_id == run_uuid,
                )
            )
            total_spawned = total_result.scalar() or 0

            removed_result = await session.execute(
                select(func.count()).where(
                    SimAgentInstance.simulation_run_id == run_uuid,
                    SimAgentInstance.state == "removed",
                )
            )
            total_removed = removed_result.scalar() or 0

            return {
                "active_count": active_count,
                "total_spawned": total_spawned,
                "total_removed": total_removed,
            }

    return run_sync(_snapshot())


@DBOS.step(
    retries_allowed=True,
    max_attempts=3,
    interval_seconds=2.0,
    backoff_rate=2.0,
)
def spawn_agents_step(
    simulation_run_id: str,
    config: dict[str, Any],
    active_count: int,
    total_spawned: int,
) -> list[str]:
    from src.database import get_session_maker
    from src.simulation.models import SimAgent
    from src.users.profile_models import CommunityMember, UserProfile

    max_agents = config["max_agents"]
    agent_profile_ids = config["agent_profile_ids"]
    community_server_id = config["community_server_id"]

    if active_count >= max_agents or not agent_profile_ids:
        return []

    to_spawn = min(SPAWN_BATCH_SIZE, max_agents - active_count)

    async def _spawn() -> list[str]:
        run_uuid = UUID(simulation_run_id)
        cs_uuid = UUID(community_server_id)
        new_instance_ids: list[str] = []
        now = pendulum.now("UTC")

        async with get_session_maker()() as session:
            current_count_result = await session.execute(
                select(func.count()).where(
                    SimAgentInstance.simulation_run_id == run_uuid,
                )
            )
            current_total = current_count_result.scalar() or 0
            adjusted_to_spawn = min(to_spawn, max_agents - active_count)
            if current_total >= max_agents:
                return []

            for i in range(adjusted_to_spawn):
                profile_index = (total_spawned + i) % len(agent_profile_ids)
                profile_id_str = agent_profile_ids[profile_index]
                profile_uuid = UUID(profile_id_str)

                agent_result = await session.execute(
                    select(SimAgent.name).where(SimAgent.id == profile_uuid)
                )
                agent_name = agent_result.scalar_one_or_none() or "Unknown"

                instance_number = total_spawned + i + 1
                display_name = f"SimAgent-{agent_name}-{instance_number}"

                user_profile = UserProfile(
                    display_name=display_name,
                    is_human=False,
                    is_active=True,
                )
                session.add(user_profile)
                await session.flush()

                community_member = CommunityMember(
                    community_id=cs_uuid,
                    profile_id=user_profile.id,
                    role="member",
                    joined_at=now,
                    is_active=True,
                )
                session.add(community_member)

                instance = SimAgentInstance(
                    simulation_run_id=run_uuid,
                    agent_profile_id=profile_uuid,
                    user_profile_id=user_profile.id,
                    state="active",
                    turn_count=0,
                )
                session.add(instance)
                await session.flush()

                new_instance_ids.append(str(instance.id))

            await session.commit()

        return new_instance_ids

    return run_sync(_spawn())


@DBOS.step()
def remove_agents_step(
    simulation_run_id: str,
    config: dict[str, Any],
    active_count: int,
) -> list[str]:
    removal_rate = config["removal_rate"]

    if removal_rate <= 0 or active_count <= 1:
        return []

    if random.random() >= removal_rate:
        return []

    from src.database import get_session_maker

    async def _remove() -> list[str]:
        run_uuid = UUID(simulation_run_id)
        now = pendulum.now("UTC")

        async with get_session_maker()() as session:
            oldest_query = (
                select(SimAgentInstance.id)
                .where(
                    SimAgentInstance.simulation_run_id == run_uuid,
                    SimAgentInstance.state == "active",
                )
                .order_by(SimAgentInstance.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            oldest_result = await session.execute(oldest_query)
            oldest_id = oldest_result.scalar_one_or_none()

            if oldest_id is None:
                return []

            remove_result = await session.execute(
                update(SimAgentInstance)
                .where(
                    SimAgentInstance.id == oldest_id,
                    SimAgentInstance.state == "active",
                )
                .values(
                    state="removed",
                    removal_reason="removal_rate",
                    deleted_at=now,
                )
                .returning(SimAgentInstance.id)
            )
            removed_id = remove_result.scalar_one_or_none()
            await session.commit()

            if removed_id is None:
                return []

            return [str(removed_id)]

    return run_sync(_remove())


@DBOS.step()
def detect_stuck_agents_step(simulation_run_id: str) -> dict[str, int]:
    from src.database import get_session_maker

    async def _get_active_agents() -> list[tuple]:
        run_uuid = UUID(simulation_run_id)
        async with get_session_maker()() as session:
            result = await session.execute(
                select(
                    SimAgentInstance.id,
                    SimAgentInstance.turn_count,
                    SimAgentInstance.retry_count,
                ).where(
                    SimAgentInstance.simulation_run_id == run_uuid,
                    SimAgentInstance.state == "active",
                )
            )
            return list(result.all())

    agents = run_sync(_get_active_agents())

    agents_to_retry: list[tuple] = []
    for agent_id, turn_count, retry_count in agents:
        wf_id = f"turn-{agent_id}-{turn_count + 1}-retry{retry_count}"
        wf_status = DBOS.get_workflow_status(wf_id)
        if wf_status is not None and wf_status.status == "ERROR":
            agents_to_retry.append((agent_id, retry_count))

    if agents_to_retry:

        async def _update_retries() -> None:
            async with get_session_maker()() as session:
                for agent_id, retry_count in agents_to_retry:
                    await session.execute(
                        update(SimAgentInstance)
                        .where(SimAgentInstance.id == agent_id)
                        .values(retry_count=retry_count + 1)
                    )
                await session.commit()

        run_sync(_update_retries())

    return {"retried": len(agents_to_retry)}


@DBOS.step()
def check_content_availability_step(community_server_id: str) -> dict[str, Any]:
    from src.database import get_session_maker
    from src.notes.models import Note, Request

    async def _check() -> dict[str, Any]:
        cs_id = UUID(community_server_id)
        async with get_session_maker()() as session:
            req_result = await session.execute(
                select(func.count())
                .select_from(Request)
                .where(
                    Request.community_server_id == cs_id,
                    Request.status == "PENDING",
                    Request.deleted_at.is_(None),
                )
            )
            pending_requests = req_result.scalar() or 0

            note_result = await session.execute(
                select(func.count())
                .select_from(Note)
                .where(
                    Note.community_server_id == cs_id,
                    Note.status == "NEEDS_MORE_RATINGS",
                    Note.deleted_at.is_(None),
                )
            )
            unrated_notes = note_result.scalar() or 0

            return {
                "has_content": pending_requests > 0 or unrated_notes > 0,
                "pending_requests": pending_requests,
                "unrated_notes": unrated_notes,
            }

    return run_sync(_check())


@DBOS.step()
def schedule_turns_step(
    simulation_run_id: str,
    config: dict[str, Any],
) -> dict[str, int]:
    from src.database import get_session_maker

    max_turns = config["max_turns_per_agent"]

    async def _schedule() -> dict[str, int]:
        from src.simulation.workflows.agent_turn_workflow import dispatch_agent_turn

        run_uuid = UUID(simulation_run_id)
        now = pendulum.now("UTC")

        async with get_session_maker()() as session:
            active_query = select(
                SimAgentInstance.id,
                SimAgentInstance.turn_count,
                SimAgentInstance.retry_count,
            ).where(
                SimAgentInstance.simulation_run_id == run_uuid,
                SimAgentInstance.state == "active",
            )
            result = await session.execute(active_query)
            instances = result.all()

        dispatched_count = 0
        skipped_count = 0
        retry_exhausted_ids: list = []

        for instance_id, turn_count, retry_count in instances:
            if turn_count >= max_turns:
                skipped_count += 1
                continue

            if retry_count >= MAX_TURN_RETRIES:
                retry_exhausted_ids.append(instance_id)
                continue

            await dispatch_agent_turn(instance_id, turn_count + 1, retry_count)
            dispatched_count += 1

        if retry_exhausted_ids:
            async with get_session_maker()() as session:
                await session.execute(
                    update(SimAgentInstance)
                    .where(
                        SimAgentInstance.id.in_(retry_exhausted_ids),
                        SimAgentInstance.state == "active",
                    )
                    .values(
                        state="removed",
                        removal_reason="max_retries_exceeded",
                        deleted_at=now,
                    )
                )
                await session.commit()

        return {
            "dispatched_count": dispatched_count,
            "skipped_count": skipped_count,
            "removed_for_retries": len(retry_exhausted_ids),
        }

    return run_sync(_schedule())


@DBOS.step()
def update_metrics_step(
    simulation_run_id: str,
    dispatched_count: int,
    spawned_count: int,
    removed_count: int,
) -> dict[str, Any]:
    from src.database import get_session_maker

    async def _update() -> dict[str, Any]:
        run_uuid = UUID(simulation_run_id)

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun.metrics).where(SimulationRun.id == run_uuid)
            )
            current_metrics = result.scalar_one_or_none() or {}

            completed_result = await session.execute(
                select(func.coalesce(func.sum(SimAgentInstance.turn_count), 0)).where(
                    SimAgentInstance.simulation_run_id == run_uuid,
                )
            )
            turns_completed = completed_result.scalar() or 0

            updated_metrics = {
                "turns_dispatched": current_metrics.get("turns_dispatched", 0) + dispatched_count,
                "turns_completed": turns_completed,
                "total_turns": turns_completed,
                "agents_spawned": current_metrics.get("agents_spawned", 0) + spawned_count,
                "agents_removed": current_metrics.get("agents_removed", 0) + removed_count,
                "iterations": current_metrics.get("iterations", 0) + 1,
            }

            await session.execute(
                update(SimulationRun)
                .where(SimulationRun.id == run_uuid)
                .values(metrics=updated_metrics)
            )
            await session.commit()

            return updated_metrics

    return run_sync(_update())


@DBOS.step(
    retries_allowed=True,
    max_attempts=2,
    interval_seconds=5.0,
    backoff_rate=2.0,
)
def run_scoring_step(simulation_run_id: str) -> dict[str, Any]:
    from src.database import get_session_maker
    from src.simulation.scoring_integration import trigger_scoring_for_simulation

    async def _score() -> dict[str, Any]:
        async with get_session_maker()() as session:
            result = await trigger_scoring_for_simulation(UUID(simulation_run_id), session)
            return {
                "scores_computed": result.scores_computed,
                "tier": result.tier_name,
                "scorer": result.scorer_type,
            }

    return run_sync(_score())


@DBOS.step(
    retries_allowed=True,
    max_attempts=3,
    interval_seconds=2.0,
    backoff_rate=2.0,
)
def finalize_run_step(simulation_run_id: str, final_status: str) -> dict[str, Any]:
    from src.database import get_session_maker

    async def _finalize() -> dict[str, Any]:
        run_uuid = UUID(simulation_run_id)
        now = pendulum.now("UTC")

        async with get_session_maker()() as session:
            active_result = await session.execute(
                select(func.count()).where(
                    SimAgentInstance.simulation_run_id == run_uuid,
                    SimAgentInstance.state == "active",
                )
            )
            remaining_active = active_result.scalar() or 0

            completion_state = "completed" if final_status == "completed" else "removed"
            removal_reason = (
                "simulation_cancelled" if final_status == "cancelled" else "simulation_completed"
            )

            if remaining_active > 0:
                await session.execute(
                    update(SimAgentInstance)
                    .where(
                        SimAgentInstance.simulation_run_id == run_uuid,
                        SimAgentInstance.state == "active",
                    )
                    .values(
                        state=completion_state,
                        removal_reason=removal_reason,
                        deleted_at=now,
                    )
                )

            await session.execute(
                update(SimulationRun)
                .where(SimulationRun.id == run_uuid)
                .values(status=final_status, completed_at=now)
            )
            await session.commit()

            return {
                "final_status": final_status,
                "instances_finalized": remaining_active,
            }

    return run_sync(_finalize())


def _finalize_with_fallback(
    simulation_run_id: str,
    final_status: str,
) -> tuple[dict[str, Any], str]:
    try:
        result = finalize_run_step(simulation_run_id, final_status)
        return result, final_status
    except Exception:
        logger.exception(
            "Failed to finalize run, attempting to set failed status",
            extra={"simulation_run_id": simulation_run_id},
        )
    try:
        result = finalize_run_step(simulation_run_id, "failed")
        return result, "failed"
    except Exception:
        logger.exception(
            "Failed to set failed status on run",
            extra={"simulation_run_id": simulation_run_id},
        )
    return {"final_status": "failed", "instances_finalized": 0}, "failed"


@DBOS.workflow()
def run_orchestrator(simulation_run_id: str) -> dict[str, Any]:  # noqa: PLR0912
    gate = TokenGate(pool="default", weight=WorkflowWeight.SIMULATION_ORCHESTRATOR)
    gate.acquire()
    try:
        workflow_id = DBOS.workflow_id
        assert workflow_id is not None

        logger.info(
            "Starting orchestrator workflow",
            extra={
                "workflow_id": workflow_id,
                "simulation_run_id": simulation_run_id,
            },
        )

        try:
            config = initialize_run_step(simulation_run_id)
        except Exception:
            logger.exception(
                "Failed to initialize orchestrator",
                extra={"simulation_run_id": simulation_run_id},
            )
            return {
                "simulation_run_id": simulation_run_id,
                "status": "failed",
                "error": "init_failed",
            }

        circuit_breaker = CircuitBreaker(
            threshold=CIRCUIT_BREAKER_THRESHOLD,
            reset_timeout=CIRCUIT_BREAKER_RESET_TIMEOUT,
        )

        final_status = "completed"
        iteration = 0
        consecutive_empty = 0

        while iteration < MAX_ITERATIONS:
            iteration += 1

            status = check_run_status_step(simulation_run_id)

            if status == "cancelled":
                final_status = "cancelled"
                break

            if status in ("completed", "failed"):
                final_status = status
                break

            if status == "paused":
                DBOS.sleep(config["turn_cadence_seconds"])
                continue

            try:
                content_check = check_content_availability_step(config["community_server_id"])
                if not content_check["has_content"]:
                    consecutive_empty += 1
                    if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                        logger.warning(
                            "No content available for %d consecutive iterations, pausing",
                            consecutive_empty,
                            extra={"simulation_run_id": simulation_run_id},
                        )
                        final_status = "paused"
                        break
                    DBOS.sleep(config["turn_cadence_seconds"])
                    continue
                consecutive_empty = 0
            except Exception:
                logger.exception("Failed to check content availability")
                consecutive_empty = 0

            try:
                snapshot = get_population_snapshot_step(simulation_run_id)
            except Exception:
                logger.exception("Failed to get population snapshot")
                continue

            spawned_ids: list[str] = []
            try:
                spawned_ids = spawn_agents_step(
                    simulation_run_id,
                    config,
                    snapshot["active_count"],
                    snapshot["total_spawned"],
                )
            except Exception:
                logger.exception("Failed to spawn agents")

            removed_ids: list[str] = []
            try:
                removed_ids = remove_agents_step(
                    simulation_run_id,
                    config,
                    snapshot["active_count"] + len(spawned_ids),
                )
            except Exception:
                logger.exception("Failed to remove agents")

            try:
                detect_stuck_agents_step(simulation_run_id)
            except Exception:
                logger.exception("Failed to detect stuck agents")

            dispatched_count = 0
            removed_for_retries = 0
            try:
                circuit_breaker.check()
                turn_result = schedule_turns_step(simulation_run_id, config)
                dispatched_count = turn_result["dispatched_count"]
                removed_for_retries = turn_result.get("removed_for_retries", 0)
                circuit_breaker.record_success()
            except CircuitOpenError:
                logger.warning(
                    "Circuit breaker open, skipping turn scheduling",
                    extra={
                        "simulation_run_id": simulation_run_id,
                        "failures": circuit_breaker.failures,
                    },
                )
            except Exception:
                logger.exception("Failed to schedule turns")
                circuit_breaker.record_failure()

            try:
                update_metrics_step(
                    simulation_run_id,
                    dispatched_count=dispatched_count,
                    spawned_count=len(spawned_ids),
                    removed_count=len(removed_ids) + removed_for_retries,
                )
            except Exception:
                logger.exception("Failed to update metrics")

            if iteration % SCORING_INTERVAL == 0:
                try:
                    scoring_result = run_scoring_step(simulation_run_id)
                    logger.info(
                        "Scoring completed",
                        extra={
                            "simulation_run_id": simulation_run_id,
                            "scores_computed": scoring_result["scores_computed"],
                            "tier": scoring_result["tier"],
                        },
                    )
                except Exception:
                    logger.exception("Scoring failed, continuing")

            DBOS.sleep(config["turn_cadence_seconds"])

        if iteration >= MAX_ITERATIONS:
            logger.warning(
                "Orchestrator reached max iterations",
                extra={
                    "simulation_run_id": simulation_run_id,
                    "max_iterations": MAX_ITERATIONS,
                },
            )

        finalize_result, final_status = _finalize_with_fallback(simulation_run_id, final_status)

        logger.info(
            "Orchestrator workflow completed",
            extra={
                "workflow_id": workflow_id,
                "simulation_run_id": simulation_run_id,
                "final_status": final_status,
                "iterations": iteration,
            },
        )

        return {
            "simulation_run_id": simulation_run_id,
            "status": final_status,
            "iterations": iteration,
            "instances_finalized": finalize_result["instances_finalized"],
        }
    finally:
        gate.release()


RUN_ORCHESTRATOR_WORKFLOW_NAME: str = run_orchestrator.__qualname__


async def dispatch_orchestrator(simulation_run_id: UUID) -> str:
    import asyncio

    from dbos import EnqueueOptions

    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    wf_id = f"orchestrator-{simulation_run_id}"
    options: EnqueueOptions = {
        "queue_name": "simulation_orchestrator",
        "workflow_name": RUN_ORCHESTRATOR_WORKFLOW_NAME,
        "workflow_id": wf_id,
        "deduplication_id": wf_id,
    }
    handle = await asyncio.to_thread(
        client.enqueue,
        options,
        str(simulation_run_id),
    )

    logger.info(
        "Orchestrator workflow dispatched",
        extra={
            "simulation_run_id": str(simulation_run_id),
            "workflow_id": handle.workflow_id,
        },
    )

    return handle.workflow_id
