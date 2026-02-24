from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestWorkflowNameConstants:
    def test_workflow_name_matches_qualname(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import (
            RUN_AGENT_TURN_WORKFLOW_NAME,
            run_agent_turn,
        )

        assert run_agent_turn.__qualname__ == RUN_AGENT_TURN_WORKFLOW_NAME

    def test_workflow_name_is_nonempty_string(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import RUN_AGENT_TURN_WORKFLOW_NAME

        assert isinstance(RUN_AGENT_TURN_WORKFLOW_NAME, str)
        assert len(RUN_AGENT_TURN_WORKFLOW_NAME) > 0

    def test_workflow_name_is_bare_function_name(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import RUN_AGENT_TURN_WORKFLOW_NAME

        assert RUN_AGENT_TURN_WORKFLOW_NAME == "run_agent_turn"


def _make_context(
    *,
    agent_instance_id: str | None = None,
    community_server_id: str | None = None,
    memory_id: str | None = None,
    instance_turn_count: int = 0,
    memory_turn_count: int = 0,
    message_history: list | None = None,
) -> dict:
    return {
        "agent_instance_id": agent_instance_id or str(uuid4()),
        "agent_profile_id": str(uuid4()),
        "simulation_run_id": str(uuid4()),
        "community_server_id": community_server_id or str(uuid4()),
        "user_profile_id": str(uuid4()),
        "personality": "You are a skeptical fact-checker.",
        "model_name": "openai:gpt-4o-mini",
        "model_params": {"request_limit": 3, "total_tokens_limit": 4000},
        "memory_compaction_strategy": "sliding_window",
        "memory_compaction_config": None,
        "message_history": message_history or [],
        "memory_id": memory_id or str(uuid4()),
        "memory_turn_count": memory_turn_count,
        "instance_turn_count": instance_turn_count,
    }


class TestLoadAgentContextStep:
    def test_load_agent_context_returns_profile_and_memory(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import load_agent_context_step

        instance_id = uuid4()
        profile_id = uuid4()
        run_id = uuid4()
        user_id = uuid4()
        memory_id = uuid4()
        cs_id = uuid4()

        mock_profile = MagicMock()
        mock_profile.community_server_id = cs_id
        mock_profile.personality = "Test personality"
        mock_profile.model_name = "openai:gpt-4o-mini"
        mock_profile.model_params = {"request_limit": 5}
        mock_profile.memory_compaction_strategy = "sliding_window"
        mock_profile.memory_compaction_config = None

        mock_instance = MagicMock()
        mock_instance.id = instance_id
        mock_instance.agent_profile_id = profile_id
        mock_instance.simulation_run_id = run_id
        mock_instance.user_profile_id = user_id
        mock_instance.turn_count = 3
        mock_instance.agent_profile = mock_profile

        mock_memory = MagicMock()
        mock_memory.id = memory_id
        mock_memory.message_history = [{"role": "user", "content": "hello"}]
        mock_memory.turn_count = 3

        mock_session = AsyncMock()

        instance_result = MagicMock()
        instance_result.scalar_one_or_none.return_value = mock_instance

        memory_result = MagicMock()
        memory_result.scalar_one_or_none.return_value = mock_memory

        mock_session.execute = AsyncMock(side_effect=[instance_result, memory_result])

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
        ):
            result = load_agent_context_step.__wrapped__(str(instance_id))

        assert result["agent_instance_id"] == str(instance_id)
        assert result["personality"] == "Test personality"
        assert result["model_name"] == "openai:gpt-4o-mini"
        assert result["memory_id"] == str(memory_id)
        assert result["message_history"] == [{"role": "user", "content": "hello"}]
        assert result["instance_turn_count"] == 3

    def test_load_agent_context_missing_instance_raises(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import load_agent_context_step

        mock_session = AsyncMock()
        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=empty_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
            pytest.raises(ValueError, match="SimAgentInstance not found"),
        ):
            load_agent_context_step.__wrapped__(str(uuid4()))


class TestCompactMemoryStep:
    def test_compact_memory_skips_when_not_due(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import compact_memory_step

        messages = [{"kind": "request", "parts": []}]
        result = compact_memory_step.__wrapped__(
            message_history=messages,
            turn_count=3,
            strategy="sliding_window",
            config=None,
            compaction_interval=5,
        )

        assert result["messages"] == messages
        assert result["was_compacted"] is False

    def test_compact_memory_skips_when_turn_zero(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import compact_memory_step

        messages = [{"kind": "request", "parts": []}]
        result = compact_memory_step.__wrapped__(
            message_history=messages,
            turn_count=0,
            strategy="sliding_window",
            config=None,
            compaction_interval=5,
        )

        assert result["messages"] == messages
        assert result["was_compacted"] is False

    def test_compact_memory_runs_compactor_when_due(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import compact_memory_step

        original_messages = [
            {"kind": "request", "parts": [{"part_kind": "text", "content": f"msg-{i}"}]}
            for i in range(10)
        ]
        compacted_messages = original_messages[-3:]

        mock_compaction_result = MagicMock()
        mock_compaction_result.messages = compacted_messages

        mock_compactor = AsyncMock()
        mock_compactor.compact = AsyncMock(return_value=mock_compaction_result)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._deserialize_messages",
                return_value=original_messages,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._serialize_messages",
                return_value=compacted_messages,
            ),
            patch(
                "src.simulation.memory.compactor_factory.CompactorFactory.create",
                return_value=mock_compactor,
            ),
        ):
            result = compact_memory_step.__wrapped__(
                message_history=original_messages,
                turn_count=10,
                strategy="sliding_window",
                config=None,
                compaction_interval=5,
            )

        assert result["was_compacted"] is True
        assert result["messages"] == compacted_messages
        mock_compactor.compact.assert_awaited_once()

    def test_compact_memory_handles_compactor_error(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import compact_memory_step

        original_messages = [{"kind": "request", "parts": []}]

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._deserialize_messages",
                side_effect=RuntimeError("deserialization failed"),
            ),
        ):
            result = compact_memory_step.__wrapped__(
                message_history=original_messages,
                turn_count=5,
                strategy="sliding_window",
                config=None,
                compaction_interval=5,
            )

        assert result["was_compacted"] is False
        assert result["messages"] == original_messages

    def test_compact_memory_skips_empty_history(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import compact_memory_step

        result = compact_memory_step.__wrapped__(
            message_history=[],
            turn_count=5,
            strategy="sliding_window",
            config=None,
            compaction_interval=5,
        )

        assert result["messages"] == []
        assert result["was_compacted"] is False


class TestBuildDepsStep:
    def test_build_deps_returns_requests_and_notes(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import build_deps_step

        cs_id = str(uuid4())
        note_id = uuid4()

        mock_request = MagicMock()
        mock_request.request_id = "req-001"
        mock_request.content = "Earth is flat"
        mock_request.status = "PENDING"

        mock_note = MagicMock()
        mock_note.id = note_id
        mock_note.summary = "Earth is an oblate spheroid"
        mock_note.classification = "NOT_MISLEADING"
        mock_note.status = "NEEDS_MORE_RATINGS"

        mock_req_result = MagicMock()
        mock_req_result.scalars.return_value.all.return_value = [mock_request]

        mock_note_result = MagicMock()
        mock_note_result.scalars.return_value.all.return_value = [mock_note]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_req_result, mock_note_result])

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
        ):
            result = build_deps_step.__wrapped__(community_server_id=cs_id)

        assert len(result["available_requests"]) == 1
        assert result["available_requests"][0]["request_id"] == "req-001"
        assert len(result["available_notes"]) == 1
        assert result["available_notes"][0]["note_id"] == str(note_id)

    def test_build_deps_returns_empty_when_no_community(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import build_deps_step

        with patch(
            "src.simulation.workflows.agent_turn_workflow.run_sync",
            side_effect=lambda coro: __import__("asyncio")
            .get_event_loop()
            .run_until_complete(coro),
        ):
            result = build_deps_step.__wrapped__(community_server_id=None)

        assert result["available_requests"] == []
        assert result["available_notes"] == []


class TestExecuteAgentTurnStep:
    def test_execute_agent_turn_returns_action_and_messages(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        deps_data = {
            "available_requests": [
                {"request_id": "req-001", "content": "test", "status": "PENDING"}
            ],
            "available_notes": [],
        }
        messages: list[dict] = []

        mock_action = MagicMock()
        mock_action.model_dump.return_value = {
            "action_type": "pass_turn",
            "reasoning": "Nothing to do",
        }

        mock_new_messages = [MagicMock()]
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_turn = AsyncMock(return_value=(mock_action, mock_new_messages))

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
            patch(
                "src.simulation.agent.OpenNotesSimAgent",
                return_value=mock_agent_instance,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._serialize_messages",
                return_value=[{"kind": "response"}],
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._deserialize_messages",
                return_value=[],
            ),
        ):
            result = execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=messages,
            )

        assert result["action"]["action_type"] == "pass_turn"
        assert "new_messages" in result
        mock_agent_instance.run_turn.assert_awaited_once()

    def test_execute_agent_turn_respects_usage_limits(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        context["model_params"] = {"request_limit": 5, "total_tokens_limit": 8000}

        deps_data = {"available_requests": [], "available_notes": []}

        mock_action = MagicMock()
        mock_action.model_dump.return_value = {"action_type": "pass_turn", "reasoning": "idle"}

        captured_kwargs: dict = {}

        async def capture_run_turn(**kwargs):
            captured_kwargs.update(kwargs)
            return (mock_action, [])

        mock_agent_instance = MagicMock()
        mock_agent_instance.run_turn = AsyncMock(side_effect=capture_run_turn)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
            patch(
                "src.simulation.agent.OpenNotesSimAgent",
                return_value=mock_agent_instance,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._serialize_messages",
                return_value=[],
            ),
        ):
            execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

        call_kwargs = mock_agent_instance.run_turn.call_args.kwargs
        limits = call_kwargs["usage_limits"]
        assert limits.request_limit == 5
        assert limits.total_tokens_limit == 8000


class TestPersistStateStep:
    def test_persist_state_updates_memory_and_counters(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import persist_state_step

        agent_instance_id = str(uuid4())
        memory_id = str(uuid4())
        new_messages = [{"kind": "response", "parts": []}]
        action = {"action_type": "write_note", "reasoning": "test"}

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
        ):
            result = persist_state_step.__wrapped__(
                agent_instance_id=agent_instance_id,
                memory_id=memory_id,
                new_messages=new_messages,
                action=action,
            )

        assert result["persisted"] is True
        assert result["action_type"] == "write_note"
        assert result["agent_instance_id"] == agent_instance_id
        assert mock_session.execute.await_count == 2
        mock_session.commit.assert_awaited_once()

    def test_persist_state_creates_memory_with_upsert(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import persist_state_step

        agent_instance_id = str(uuid4())
        new_messages = [{"kind": "response", "parts": []}]
        action = {"action_type": "pass_turn", "reasoning": "idle"}

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
        ):
            result = persist_state_step.__wrapped__(
                agent_instance_id=agent_instance_id,
                memory_id=None,
                new_messages=new_messages,
                action=action,
            )

        assert result["persisted"] is True
        assert mock_session.execute.await_count == 2
        mock_session.commit.assert_awaited_once()


class TestRunAgentTurnWorkflow:
    def test_run_agent_turn_happy_path(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
                return_value=context,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.compact_memory_step",
                return_value={"messages": [], "was_compacted": False},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.build_deps_step",
                return_value={"available_requests": [], "available_notes": []},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                return_value={
                    "action": {"action_type": "pass_turn", "reasoning": "Nothing to do"},
                    "new_messages": [{"kind": "response"}],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={
                    "agent_instance_id": agent_instance_id,
                    "action_type": "pass_turn",
                    "persisted": True,
                },
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test-123"

            result = run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert result["agent_instance_id"] == agent_instance_id
        assert result["action"]["action_type"] == "pass_turn"
        assert result["persisted"] is True
        assert result["workflow_id"] == "wf-test-123"

    def test_run_agent_turn_calls_steps_in_order(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)
        call_order: list[str] = []

        def track_load(*args, **kwargs):
            call_order.append("load")
            return context

        def track_compact(*args, **kwargs):
            call_order.append("compact")
            return {"messages": [], "was_compacted": False}

        def track_build(*args, **kwargs):
            call_order.append("build")
            return {"available_requests": [], "available_notes": []}

        def track_execute(*args, **kwargs):
            call_order.append("execute")
            return {
                "action": {"action_type": "pass_turn", "reasoning": "idle"},
                "new_messages": [],
            }

        def track_persist(*args, **kwargs):
            call_order.append("persist")
            return {
                "agent_instance_id": agent_instance_id,
                "action_type": "pass_turn",
                "persisted": True,
            }

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
                side_effect=track_load,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.compact_memory_step",
                side_effect=track_compact,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.build_deps_step",
                side_effect=track_build,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                side_effect=track_execute,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                side_effect=track_persist,
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert call_order == ["load", "compact", "build", "execute", "persist"]

    def test_run_agent_turn_passes_compacted_messages_to_execute(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)
        compacted = [{"kind": "request", "parts": [{"part_kind": "text", "content": "compacted"}]}]

        captured_execute_args: dict = {}

        def capture_execute(**kwargs):
            captured_execute_args.update(kwargs)
            return {
                "action": {"action_type": "pass_turn", "reasoning": "idle"},
                "new_messages": [],
            }

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
                return_value=context,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.compact_memory_step",
                return_value={"messages": compacted, "was_compacted": True},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.build_deps_step",
                return_value={"available_requests": [], "available_notes": []},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                side_effect=capture_execute,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={
                    "agent_instance_id": agent_instance_id,
                    "action_type": "pass_turn",
                    "persisted": True,
                },
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert captured_execute_args["messages"] == compacted


class TestDispatchAgentTurn:
    @pytest.mark.asyncio
    async def test_dispatch_agent_turn_enqueues_via_dbos_client(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import dispatch_agent_turn

        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "turn-abc-5"
        mock_client.enqueue.return_value = mock_handle

        agent_instance_id = uuid4()
        turn_number = 5

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            workflow_id = await dispatch_agent_turn(agent_instance_id, turn_number)

        assert workflow_id == "turn-abc-5"
        mock_client.enqueue.assert_called_once()

        enqueue_args = mock_client.enqueue.call_args
        options = enqueue_args.args[0]
        assert options["queue_name"] == "simulation_turn"
        assert options["workflow_name"] == "run_agent_turn"
        assert options["workflow_id"] == f"turn-{agent_instance_id}-{turn_number}"
        assert options["deduplication_id"] == f"turn-{agent_instance_id}-{turn_number}"

        assert enqueue_args.args[1] == str(agent_instance_id)

    @pytest.mark.asyncio
    async def test_dispatch_agent_turn_idempotent_id(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import dispatch_agent_turn

        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "test-wf"
        mock_client.enqueue.return_value = mock_handle

        agent_id = uuid4()

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            await dispatch_agent_turn(agent_id, 7)
            await dispatch_agent_turn(agent_id, 7)

        call1_options = mock_client.enqueue.call_args_list[0].args[0]
        call2_options = mock_client.enqueue.call_args_list[1].args[0]
        assert call1_options["workflow_id"] == call2_options["workflow_id"]
        assert call1_options["deduplication_id"] == call2_options["deduplication_id"]
