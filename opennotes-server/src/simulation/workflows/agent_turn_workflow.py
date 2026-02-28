from __future__ import annotations

from typing import Any
from uuid import UUID

import pendulum
from dbos import DBOS, Queue
from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.dbos_workflows.token_bucket.config import WorkflowWeight
from src.dbos_workflows.token_bucket.gate import TokenGate
from src.monitoring import get_logger
from src.simulation.models import SimAgent, SimAgentInstance, SimAgentMemory, SimulationRun
from src.simulation.schemas import SimActionType, SimAgentAction
from src.utils.async_compat import run_sync

logger = get_logger(__name__)

_message_list_ta: TypeAdapter[list[ModelMessage]] = TypeAdapter(list[ModelMessage])

simulation_turn_queue = Queue(
    name="simulation_turn",
    worker_concurrency=6,
    concurrency=24,
)


def _serialize_messages(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    return _message_list_ta.dump_python(messages, mode="json")  # type: ignore[return-value]


def _deserialize_messages(data: list[dict[str, Any]]) -> list[ModelMessage]:
    return _message_list_ta.validate_python(data)


@DBOS.step(
    retries_allowed=True,
    max_attempts=3,
    interval_seconds=2.0,
    backoff_rate=2.0,
)
def load_agent_context_step(agent_instance_id: str) -> dict[str, Any]:
    from src.database import get_session_maker

    async def _load() -> dict[str, Any]:
        async with get_session_maker()() as session:
            instance_query = (
                select(SimAgentInstance)
                .options(
                    selectinload(SimAgentInstance.agent_profile),
                    selectinload(SimAgentInstance.simulation_run),
                )
                .where(SimAgentInstance.id == UUID(agent_instance_id))
            )
            result = await session.execute(instance_query)
            instance = result.scalar_one_or_none()

            if instance is None:
                raise ValueError(f"SimAgentInstance not found: {agent_instance_id}")

            profile: SimAgent = instance.agent_profile
            run: SimulationRun = instance.simulation_run

            memory_query = select(SimAgentMemory).where(
                SimAgentMemory.agent_instance_id == UUID(agent_instance_id)
            )
            mem_result = await session.execute(memory_query)
            memory = mem_result.scalar_one_or_none()

            message_history: list[dict[str, Any]] = []
            memory_id: str | None = None
            memory_turn_count: int = 0
            recent_actions: list[str] = []
            if memory is not None:
                message_history = memory.message_history or []
                memory_id = str(memory.id)
                memory_turn_count = memory.turn_count
                recent_actions = memory.recent_actions or []

            return {
                "agent_instance_id": str(instance.id),
                "agent_profile_id": str(instance.agent_profile_id),
                "simulation_run_id": str(instance.simulation_run_id),
                "community_server_id": str(run.community_server_id),
                "user_profile_id": str(instance.user_profile_id),
                "personality": profile.personality,
                "model_name": profile.model_name,
                "model_params": profile.model_params,
                "memory_compaction_strategy": profile.memory_compaction_strategy,
                "memory_compaction_config": profile.memory_compaction_config,
                "message_history": message_history,
                "memory_id": memory_id,
                "memory_turn_count": memory_turn_count,
                "instance_turn_count": instance.turn_count,
                "recent_actions": recent_actions,
            }

    return run_sync(_load())


@DBOS.step()
def compact_memory_step(
    message_history: list[dict[str, Any]],
    turn_count: int,
    strategy: str,
    config: dict[str, Any] | None,
    compaction_interval: int,
) -> dict[str, Any]:
    if not message_history:
        return {"messages": [], "was_compacted": False}

    if turn_count == 0 or turn_count % compaction_interval != 0:
        return {"messages": message_history, "was_compacted": False}

    from src.simulation.memory.compactor_factory import CompactorFactory

    async def _compact() -> dict[str, Any]:
        try:
            messages = _deserialize_messages(message_history)
            compactor = CompactorFactory.create(strategy)
            result = await compactor.compact(messages, config or {})
            return {
                "messages": _serialize_messages(result.messages),
                "was_compacted": True,
            }
        except Exception:
            logger.exception(
                "Memory compaction failed, using original messages",
                extra={"strategy": strategy, "turn_count": turn_count},
            )
            return {"messages": message_history, "was_compacted": False}

    return run_sync(_compact())


@DBOS.step(
    retries_allowed=True,
    max_attempts=3,
    interval_seconds=2.0,
    backoff_rate=2.0,
)
def build_deps_step(
    community_server_id: str,
) -> dict[str, Any]:
    from src.database import get_session_maker
    from src.notes.models import Note, Request

    async def _build() -> dict[str, Any]:
        available_requests: list[dict[str, Any]] = []
        available_notes: list[dict[str, Any]] = []

        cs_id = UUID(community_server_id)

        async with get_session_maker()() as session:
            from src.simulation.agent import (
                MAX_CONTEXT_NOTES,
                MAX_CONTEXT_REQUESTS,
                MAX_LINKED_NOTES_PER_REQUEST,
            )

            req_query = (
                select(Request)
                .where(
                    Request.community_server_id == cs_id,
                    Request.status == "PENDING",
                    Request.deleted_at.is_(None),
                )
                .order_by(func.random())
                .limit(MAX_CONTEXT_REQUESTS)
            )
            req_result = await session.execute(req_query)
            requests = req_result.scalars().all()

            request_ids = [req.request_id for req in requests]

            notes_by_request: dict[str, list[dict[str, Any]]] = {}
            if request_ids:
                linked_note_query = (
                    select(Note)
                    .where(
                        Note.request_id.in_(request_ids),
                        Note.deleted_at.is_(None),
                    )
                    .limit(MAX_LINKED_NOTES_PER_REQUEST * len(request_ids))
                )
                linked_note_result = await session.execute(linked_note_query)
                for n in linked_note_result.scalars().all():
                    if n.request_id is None:
                        continue
                    notes_by_request.setdefault(n.request_id, []).append(
                        {
                            "note_id": str(n.id),
                            "summary": n.summary,
                            "classification": n.classification,
                            "status": n.status,
                        }
                    )

            for req in requests:
                available_requests.append(
                    {
                        "request_id": req.request_id,
                        "content": req.content,
                        "status": req.status,
                        "notes": notes_by_request.get(req.request_id, []),
                    }
                )

            note_query = (
                select(Note)
                .where(
                    Note.community_server_id == cs_id,
                    Note.status == "NEEDS_MORE_RATINGS",
                    Note.deleted_at.is_(None),
                )
                .order_by(func.random())
                .limit(MAX_CONTEXT_NOTES)
            )
            note_result = await session.execute(note_query)
            for note in note_result.scalars().all():
                available_notes.append(
                    {
                        "note_id": str(note.id),
                        "summary": note.summary,
                        "classification": note.classification,
                        "status": note.status,
                    }
                )

        return {
            "available_requests": available_requests,
            "available_notes": available_notes,
        }

    return run_sync(_build())


@DBOS.step(retries_allowed=False)
def select_action_step(
    context: dict[str, Any],
    deps_data: dict[str, Any],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    from src.llm_config.model_id import ModelId
    from src.simulation.agent import OpenNotesSimAgent, SimAgentDeps

    async def _select() -> dict[str, Any]:
        model_name_str = context["model_name"]
        model_id = ModelId.from_pydantic_ai(model_name_str)
        agent = OpenNotesSimAgent(model=model_id)

        message_history = _deserialize_messages(messages) if messages else None

        deps = SimAgentDeps(
            db=None,  # type: ignore[arg-type]
            community_server_id=UUID(context["community_server_id"]),
            agent_instance_id=UUID(context["agent_instance_id"]),
            user_profile_id=UUID(context["user_profile_id"]),
            available_requests=deps_data["available_requests"],
            available_notes=deps_data["available_notes"],
            agent_personality=context["personality"],
            model_name=model_id,
        )

        selection, phase1_messages = await agent.select_action(
            deps=deps,
            recent_actions=context.get("recent_actions", []),
            requests=deps_data["available_requests"],
            notes=deps_data["available_notes"],
            message_history=message_history,
        )

        return {
            "action_type": selection.action_type.value,
            "reasoning": selection.reasoning,
            "phase1_messages": _serialize_messages(phase1_messages),
        }

    return run_sync(_select())


@DBOS.step(retries_allowed=False)
def execute_agent_turn_step(
    context: dict[str, Any],
    deps_data: dict[str, Any],
    messages: list[dict[str, Any]],
    action_type: str | None = None,
    phase1_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from pydantic_ai.exceptions import UsageLimitExceeded, UserError

    from src.database import get_session_maker
    from src.llm_config.model_id import ModelId
    from src.simulation.agent import OpenNotesSimAgent, SimAgentDeps

    async def _execute() -> dict[str, Any]:
        settings = get_settings()
        model_params = context.get("model_params") or {}
        request_limit = model_params.get("request_limit", settings.SIMULATION_DEFAULT_REQUEST_LIMIT)
        token_limit = model_params.get(
            "total_tokens_limit", settings.SIMULATION_DEFAULT_TOKEN_LIMIT
        )

        usage_limits = UsageLimits(
            request_limit=request_limit,
            total_tokens_limit=token_limit,
        )

        if phase1_messages is not None:
            message_history = _deserialize_messages(phase1_messages)
        elif messages:
            message_history = _deserialize_messages(messages)
        else:
            message_history = None

        chosen_action: SimActionType | None = None
        if action_type is not None:
            chosen_action = SimActionType(action_type)

        model_name_str = context["model_name"]
        try:
            model_id = ModelId.from_pydantic_ai(model_name_str)
        except ValueError as exc:
            raise ValueError(
                f"Invalid model name '{model_name_str}' for SimAgent "
                f"instance '{context['agent_instance_id']}'. "
                f"Update the SimAgent profile to use a valid "
                f"'provider:model' format. Original error: {exc}"
            ) from exc
        agent = OpenNotesSimAgent(model=model_id)

        async with get_session_maker()() as session:
            deps = SimAgentDeps(
                db=session,
                community_server_id=UUID(context["community_server_id"]),
                agent_instance_id=UUID(context["agent_instance_id"]),
                user_profile_id=UUID(context["user_profile_id"]),
                available_requests=deps_data["available_requests"],
                available_notes=deps_data["available_notes"],
                agent_personality=context["personality"],
                model_name=model_id,
            )

            try:
                action, new_messages = await agent.run_turn(
                    deps=deps,
                    message_history=message_history,
                    usage_limits=usage_limits,
                    chosen_action_type=chosen_action,
                )
            except UserError as exc:
                model_name = context["model_name"]
                raise ValueError(
                    f"Invalid model name '{model_name}' for SimAgent "
                    f"instance '{context['agent_instance_id']}'. "
                    f"Update the SimAgent profile to use a valid "
                    f"'provider:model' format. Original error: {exc}"
                ) from exc
            except UsageLimitExceeded as exc:
                logger.warning(
                    "Agent turn hit usage limit, treating as partial completion",
                    extra={
                        "agent_instance_id": context["agent_instance_id"],
                        "error": str(exc),
                    },
                )
                action = SimAgentAction(
                    action_type=SimActionType.PASS_TURN,
                    reasoning=f"Turn ended early: usage limit exceeded ({exc})",
                )
                return {
                    "action": action.model_dump(mode="json"),
                    "new_messages": phase1_messages if phase1_messages is not None else messages,
                }

            await session.commit()

        return {
            "action": action.model_dump(mode="json"),
            "new_messages": _serialize_messages(new_messages),
        }

    return run_sync(_execute())


@DBOS.step(
    retries_allowed=True,
    max_attempts=3,
    interval_seconds=2.0,
    backoff_rate=2.0,
)
def persist_state_step(
    agent_instance_id: str,
    memory_id: str | None,
    new_messages: list[dict[str, Any]],
    action: dict[str, Any],
    simulation_run_id: str | None = None,
    recent_actions: list[str] | None = None,
) -> dict[str, Any]:
    from src.database import get_session_maker

    async def _persist() -> dict[str, Any]:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        now = pendulum.now("UTC")
        instance_uuid = UUID(agent_instance_id)

        updated_recent_actions = list(recent_actions or [])
        updated_recent_actions.append(action.get("action_type", "unknown"))
        updated_recent_actions = updated_recent_actions[-5:]

        async with get_session_maker()() as session:
            if memory_id is not None:
                await session.execute(
                    update(SimAgentMemory)
                    .where(SimAgentMemory.id == UUID(memory_id))
                    .values(
                        message_history=new_messages,
                        turn_count=SimAgentMemory.turn_count + 1,
                        recent_actions=updated_recent_actions,
                    )
                )
            else:
                stmt = (
                    pg_insert(SimAgentMemory)
                    .values(
                        agent_instance_id=instance_uuid,
                        message_history=new_messages,
                        turn_count=1,
                        recent_actions=updated_recent_actions,
                    )
                    .on_conflict_do_update(
                        index_elements=["agent_instance_id"],
                        set_={
                            "message_history": new_messages,
                            "turn_count": SimAgentMemory.turn_count + 1,
                            "recent_actions": updated_recent_actions,
                        },
                    )
                )
                await session.execute(stmt)

            await session.execute(
                update(SimAgentInstance)
                .where(SimAgentInstance.id == instance_uuid)
                .values(
                    turn_count=SimAgentInstance.turn_count + 1,
                    last_turn_at=now,
                    retry_count=0,
                )
            )

            await session.commit()

        if simulation_run_id:
            try:
                from src.cache.redis_client import get_shared_redis_client
                from src.simulation.constants import PROGRESS_CACHE_KEY_PREFIX

                cache_key = f"{PROGRESS_CACHE_KEY_PREFIX}{simulation_run_id}"
                shared_redis = await get_shared_redis_client()
                await shared_redis.delete(cache_key)
            except Exception:
                logger.warning(
                    "Failed to invalidate progress cache",
                    exc_info=True,
                    extra={"simulation_run_id": simulation_run_id},
                )

        return {
            "agent_instance_id": agent_instance_id,
            "action_type": action.get("action_type", "unknown"),
            "persisted": True,
        }

    return run_sync(_persist())


@DBOS.workflow()
def run_agent_turn(agent_instance_id: str) -> dict[str, Any]:
    gate = TokenGate(pool="default", weight=WorkflowWeight.SIMULATION_TURN)
    gate.acquire()
    try:
        settings = get_settings()
        workflow_id = DBOS.workflow_id
        assert workflow_id is not None

        logger.info(
            "Starting agent turn workflow",
            extra={
                "workflow_id": workflow_id,
                "agent_instance_id": agent_instance_id,
            },
        )

        context = load_agent_context_step(agent_instance_id)

        memory_result = compact_memory_step(
            message_history=context["message_history"],
            turn_count=context["instance_turn_count"],
            strategy=context["memory_compaction_strategy"],
            config=context["memory_compaction_config"],
            compaction_interval=settings.SIMULATION_COMPACTION_INTERVAL,
        )

        deps_data = build_deps_step(
            community_server_id=context["community_server_id"],
        )

        selection = select_action_step(
            context=context,
            deps_data=deps_data,
            messages=memory_result["messages"],
        )
        action_type = selection["action_type"]

        if action_type == SimActionType.PASS_TURN.value:
            pass_action = {
                "action_type": "pass_turn",
                "reasoning": selection["reasoning"],
            }
            persist_result = persist_state_step(
                agent_instance_id=agent_instance_id,
                memory_id=context.get("memory_id"),
                new_messages=selection["phase1_messages"],
                action=pass_action,
                simulation_run_id=context.get("simulation_run_id"),
                recent_actions=context.get("recent_actions", []),
            )

            logger.info(
                "Agent turn workflow completed (pass_turn)",
                extra={
                    "workflow_id": workflow_id,
                    "agent_instance_id": agent_instance_id,
                    "action_type": "pass_turn",
                },
            )

            return {
                "agent_instance_id": agent_instance_id,
                "action": pass_action,
                "persisted": persist_result["persisted"],
                "workflow_id": workflow_id,
            }

        turn_result = execute_agent_turn_step(
            context=context,
            deps_data=deps_data,
            messages=memory_result["messages"],
            action_type=action_type,
            phase1_messages=selection["phase1_messages"],
        )

        persist_result = persist_state_step(
            agent_instance_id=agent_instance_id,
            memory_id=context.get("memory_id"),
            new_messages=turn_result["new_messages"],
            action=turn_result["action"],
            simulation_run_id=context.get("simulation_run_id"),
            recent_actions=context.get("recent_actions", []),
        )

        logger.info(
            "Agent turn workflow completed",
            extra={
                "workflow_id": workflow_id,
                "agent_instance_id": agent_instance_id,
                "action_type": persist_result.get("action_type"),
            },
        )

        return {
            "agent_instance_id": agent_instance_id,
            "action": turn_result["action"],
            "persisted": persist_result["persisted"],
            "workflow_id": workflow_id,
        }
    finally:
        gate.release()


RUN_AGENT_TURN_WORKFLOW_NAME: str = run_agent_turn.__qualname__


async def dispatch_agent_turn(
    agent_instance_id: UUID, turn_number: int, retry_count: int = 0
) -> str:
    import asyncio

    from dbos import EnqueueOptions

    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    wf_id = f"turn-{agent_instance_id}-{turn_number}-retry{retry_count}"
    options: EnqueueOptions = {
        "queue_name": "simulation_turn",
        "workflow_name": RUN_AGENT_TURN_WORKFLOW_NAME,
        "workflow_id": wf_id,
        "deduplication_id": wf_id,
    }
    handle = await asyncio.to_thread(
        client.enqueue,
        options,
        str(agent_instance_id),
    )

    logger.info(
        "Agent turn workflow dispatched",
        extra={
            "agent_instance_id": str(agent_instance_id),
            "turn_number": turn_number,
            "workflow_id": handle.workflow_id,
        },
    )

    return handle.workflow_id
