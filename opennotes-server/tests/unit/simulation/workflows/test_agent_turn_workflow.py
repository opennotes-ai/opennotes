from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.llm_config.model_id import ModelId


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
    recent_actions: list[str] | None = None,
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
        "recent_actions": recent_actions or [],
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
        mock_profile.personality = "Test personality"
        mock_profile.model_name = "openai:gpt-4o-mini"
        mock_profile.model_params = {"request_limit": 5}
        mock_profile.memory_compaction_strategy = "sliding_window"
        mock_profile.memory_compaction_config = None

        mock_simulation_run = MagicMock()
        mock_simulation_run.community_server_id = cs_id

        mock_instance = MagicMock()
        mock_instance.id = instance_id
        mock_instance.agent_profile_id = profile_id
        mock_instance.simulation_run_id = run_id
        mock_instance.user_profile_id = user_id
        mock_instance.turn_count = 3
        mock_instance.agent_profile = mock_profile
        mock_instance.simulation_run = mock_simulation_run

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
        assert result["community_server_id"] == str(cs_id)

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

        mock_linked_note_result = MagicMock()
        mock_linked_note_result.scalars.return_value.all.return_value = []

        mock_note_result = MagicMock()
        mock_note_result.scalars.return_value.all.return_value = [mock_note]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[mock_req_result, mock_linked_note_result, mock_note_result]
        )

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
        assert result["available_requests"][0]["notes"] == []
        assert len(result["available_notes"]) == 1
        assert result["available_notes"][0]["note_id"] == str(note_id)

    def test_build_deps_includes_linked_notes_on_requests(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import build_deps_step

        cs_id = str(uuid4())
        linked_note_id = uuid4()

        mock_request = MagicMock()
        mock_request.request_id = "req-002"
        mock_request.content = "Vaccines cause autism"
        mock_request.status = "PENDING"

        mock_linked_note = MagicMock()
        mock_linked_note.id = linked_note_id
        mock_linked_note.request_id = "req-002"
        mock_linked_note.summary = "Vaccines do not cause autism"
        mock_linked_note.classification = "NOT_MISLEADING"
        mock_linked_note.status = "NEEDS_MORE_RATINGS"

        mock_req_result = MagicMock()
        mock_req_result.scalars.return_value.all.return_value = [mock_request]

        mock_linked_note_result = MagicMock()
        mock_linked_note_result.scalars.return_value.all.return_value = [mock_linked_note]

        mock_standalone_note_result = MagicMock()
        mock_standalone_note_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[mock_req_result, mock_linked_note_result, mock_standalone_note_result]
        )

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
        req = result["available_requests"][0]
        assert req["request_id"] == "req-002"
        assert len(req["notes"]) == 1
        assert req["notes"][0]["note_id"] == str(linked_note_id)
        assert req["notes"][0]["summary"] == "Vaccines do not cause autism"
        assert req["notes"][0]["classification"] == "NOT_MISLEADING"

    def test_build_deps_linked_notes_query_has_limit(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import build_deps_step

        cs_id = str(uuid4())

        mock_request_1 = MagicMock()
        mock_request_1.request_id = "req-limit-1"
        mock_request_1.content = "test content"
        mock_request_1.status = "PENDING"

        mock_req_result = MagicMock()
        mock_req_result.scalars.return_value.all.return_value = [mock_request_1]

        mock_linked_note_result = MagicMock()
        mock_linked_note_result.scalars.return_value.all.return_value = []

        mock_standalone_note_result = MagicMock()
        mock_standalone_note_result.scalars.return_value.all.return_value = []

        captured_queries: list = []
        call_count = 0
        side_effects = [mock_req_result, mock_linked_note_result, mock_standalone_note_result]

        async def capture_execute(query, *args, **kwargs):
            nonlocal call_count
            captured_queries.append(query)
            result = side_effects[call_count]
            call_count += 1
            return result

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=capture_execute)

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
            build_deps_step.__wrapped__(community_server_id=cs_id)

        assert len(captured_queries) == 3
        linked_notes_query = captured_queries[1]
        compiled = str(linked_notes_query.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT" in compiled.upper()

        from src.simulation.agent import MAX_LINKED_NOTES_PER_REQUEST

        assert f"LIMIT {MAX_LINKED_NOTES_PER_REQUEST}" in compiled


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

    def test_execute_agent_turn_catches_invalid_model_format(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        context["model_name"] = "openai/gpt-5-mini"
        deps_data = {"available_requests": [], "available_notes": []}

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            pytest.raises(ValueError, match="openai/gpt-5-mini"),
        ):
            execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

    def test_execute_agent_turn_error_message_mentions_sim_agent(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        context["model_name"] = "vertex_ai/gemini-2.5-flash"
        deps_data = {"available_requests": [], "available_notes": []}

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            pytest.raises(ValueError, match="Invalid model name"),
        ):
            execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

    def test_execute_agent_turn_constructs_model_id(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        deps_data = {
            "available_requests": [],
            "available_notes": [],
        }

        mock_action = MagicMock()
        mock_action.model_dump.return_value = {
            "action_type": "pass_turn",
            "reasoning": "Nothing to do",
        }

        captured_model: list = []
        captured_deps_model: list = []

        class MockSimAgent:
            def __init__(self, model=None):
                captured_model.append(model)
                self.run_turn = AsyncMock(return_value=(mock_action, []))

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        original_sim_agent_deps = None

        def capture_sim_agent_deps(*args, **kwargs):
            nonlocal original_sim_agent_deps
            from src.simulation.agent import SimAgentDeps

            obj = SimAgentDeps(*args, **kwargs)
            captured_deps_model.append(obj.model_name)
            return obj

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
                MockSimAgent,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._serialize_messages",
                return_value=[],
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._deserialize_messages",
                return_value=[],
            ),
        ):
            execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

        assert len(captured_model) == 1
        assert isinstance(captured_model[0], ModelId)
        assert captured_model[0].provider == "openai"
        assert captured_model[0].model == "gpt-4o-mini"

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

    def test_persist_state_resets_retry_count_to_zero(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import persist_state_step

        agent_instance_id = str(uuid4())
        memory_id = str(uuid4())
        new_messages = [{"kind": "response", "parts": []}]
        action = {"action_type": "write_note", "reasoning": "tested"}

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
            persist_state_step.__wrapped__(
                agent_instance_id=agent_instance_id,
                memory_id=memory_id,
                new_messages=new_messages,
                action=action,
            )

        instance_update_stmt = mock_session.execute.call_args_list[1].args[0]
        compiled = instance_update_stmt.compile()
        assert "retry_count" in str(compiled)
        assert compiled.params["retry_count"] == 0

    def test_persist_state_invalidates_redis_progress_cache(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import persist_state_step

        agent_instance_id = str(uuid4())
        memory_id = str(uuid4())
        simulation_run_id = str(uuid4())
        new_messages = [{"kind": "response", "parts": []}]
        action = {"action_type": "rate_note", "reasoning": "tested"}

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_raw_redis = AsyncMock()
        mock_raw_redis.delete = AsyncMock()
        mock_get_shared = AsyncMock(return_value=mock_raw_redis)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch("src.database.get_session_maker", return_value=lambda: mock_session_ctx),
            patch(
                "src.cache.redis_client.get_shared_redis_client",
                mock_get_shared,
            ),
        ):
            persist_state_step.__wrapped__(
                agent_instance_id=agent_instance_id,
                memory_id=memory_id,
                new_messages=new_messages,
                action=action,
                simulation_run_id=simulation_run_id,
            )

        expected_key = f"sim:progress:{simulation_run_id}"
        mock_get_shared.assert_awaited_once()
        mock_raw_redis.delete.assert_awaited_once_with(expected_key)


class TestSelectActionStep:
    def test_calls_agent_select_action(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import select_action_step

        context = _make_context()
        deps_data = {
            "available_requests": [
                {"request_id": "req-001", "content": "test", "status": "PENDING"}
            ],
            "available_notes": [],
        }

        mock_selection = MagicMock()
        mock_selection.action_type.value = "write_note"
        mock_selection.reasoning = "There is a request to address"

        mock_phase1_messages = [MagicMock()]
        mock_agent_instance = MagicMock()
        mock_agent_instance.select_action = AsyncMock(
            return_value=(mock_selection, mock_phase1_messages)
        )

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
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
            result = select_action_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

        assert result["action_type"] == "write_note"
        assert result["reasoning"] == "There is a request to address"
        assert result["phase1_messages"] == [{"kind": "response"}]
        mock_agent_instance.select_action.assert_awaited_once()

    def test_returns_pass_after_retry(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import select_action_step

        context = _make_context()
        deps_data = {
            "available_requests": [],
            "available_notes": [],
        }

        mock_selection = MagicMock()
        mock_selection.action_type.value = "pass_turn"
        mock_selection.reasoning = "Nothing available"

        mock_agent_instance = MagicMock()
        mock_agent_instance.select_action = AsyncMock(return_value=(mock_selection, []))

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch(
                "src.simulation.agent.OpenNotesSimAgent",
                return_value=mock_agent_instance,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._serialize_messages",
                return_value=[],
            ),
        ):
            result = select_action_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

        assert result["action_type"] == "pass_turn"
        assert result["reasoning"] == "Nothing available"

    def test_passes_recent_actions_to_agent(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import select_action_step

        context = _make_context(recent_actions=["write_note", "rate_note"])
        deps_data = {
            "available_requests": [],
            "available_notes": [],
        }

        mock_selection = MagicMock()
        mock_selection.action_type.value = "rate_note"
        mock_selection.reasoning = "Diversifying"

        captured_kwargs: dict = {}

        async def capture_select(**kwargs):
            captured_kwargs.update(kwargs)
            return (mock_selection, [])

        mock_agent_instance = MagicMock()
        mock_agent_instance.select_action = AsyncMock(side_effect=capture_select)

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.run_sync",
                side_effect=lambda coro: __import__("asyncio")
                .get_event_loop()
                .run_until_complete(coro),
            ),
            patch(
                "src.simulation.agent.OpenNotesSimAgent",
                return_value=mock_agent_instance,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow._serialize_messages",
                return_value=[],
            ),
        ):
            select_action_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

        assert captured_kwargs["recent_actions"] == ["write_note", "rate_note"]


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
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                return_value={
                    "action_type": "write_note",
                    "reasoning": "Found a request",
                    "phase1_messages": [{"kind": "response"}],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                return_value={
                    "action": {"action_type": "write_note", "reasoning": "Wrote note"},
                    "new_messages": [{"kind": "response"}],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={
                    "agent_instance_id": agent_instance_id,
                    "action_type": "write_note",
                    "persisted": True,
                },
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test-123"

            result = run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert result["agent_instance_id"] == agent_instance_id
        assert result["action"]["action_type"] == "write_note"
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

        def track_select(*args, **kwargs):
            call_order.append("select")
            return {
                "action_type": "write_note",
                "reasoning": "Found work",
                "phase1_messages": [],
            }

        def track_execute(*args, **kwargs):
            call_order.append("execute")
            return {
                "action": {"action_type": "write_note", "reasoning": "wrote note"},
                "new_messages": [],
            }

        def track_persist(*args, **kwargs):
            call_order.append("persist")
            return {
                "agent_instance_id": agent_instance_id,
                "action_type": "write_note",
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
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                side_effect=track_select,
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

        assert call_order == ["load", "compact", "build", "select", "execute", "persist"]

    def test_run_agent_turn_passes_compacted_messages_to_select(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)
        compacted = [{"kind": "request", "parts": [{"part_kind": "text", "content": "compacted"}]}]

        captured_select_args: dict = {}

        def capture_select(**kwargs):
            captured_select_args.update(kwargs)
            return {
                "action_type": "write_note",
                "reasoning": "test",
                "phase1_messages": [],
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
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                side_effect=capture_select,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                return_value={
                    "action": {"action_type": "write_note", "reasoning": "wrote"},
                    "new_messages": [],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={
                    "agent_instance_id": agent_instance_id,
                    "action_type": "write_note",
                    "persisted": True,
                },
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert captured_select_args["messages"] == compacted

    def test_run_agent_turn_skips_phase2_on_pass_turn(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)
        phase1_msgs = [{"kind": "response", "parts": [{"part_kind": "text", "content": "pass"}]}]

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
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                return_value={
                    "action_type": "pass_turn",
                    "reasoning": "Nothing to do",
                    "phase1_messages": phase1_msgs,
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
            ) as mock_execute,
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={
                    "agent_instance_id": agent_instance_id,
                    "action_type": "pass_turn",
                    "persisted": True,
                },
            ) as mock_persist,
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        mock_execute.assert_not_called()
        assert result["action"]["action_type"] == "pass_turn"
        assert result["action"]["reasoning"] == "Nothing to do"
        assert result["persisted"] is True
        persist_kwargs = mock_persist.call_args.kwargs
        assert persist_kwargs["new_messages"] == phase1_msgs
        assert persist_kwargs["action"]["action_type"] == "pass_turn"


class TestDispatchAgentTurn:
    @pytest.mark.asyncio
    async def test_dispatch_agent_turn_enqueues_via_dbos_client(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import dispatch_agent_turn

        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.workflow_id = "turn-abc-5-retry0"
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

        assert workflow_id == "turn-abc-5-retry0"
        mock_client.enqueue.assert_called_once()

        enqueue_args = mock_client.enqueue.call_args
        options = enqueue_args.args[0]
        assert options["queue_name"] == "simulation_turn"
        assert options["workflow_name"] == "run_agent_turn"
        assert options["workflow_id"] == f"turn-{agent_instance_id}-{turn_number}-retry0"
        assert options["deduplication_id"] == f"turn-{agent_instance_id}-{turn_number}-retry0"

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

    @pytest.mark.asyncio
    async def test_dispatch_agent_turn_retry_count_changes_dedup_id(self) -> None:
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
            await dispatch_agent_turn(agent_id, 1, retry_count=0)
            await dispatch_agent_turn(agent_id, 1, retry_count=2)

        call1_options = mock_client.enqueue.call_args_list[0].args[0]
        call2_options = mock_client.enqueue.call_args_list[1].args[0]
        assert call1_options["workflow_id"] == f"turn-{agent_id}-1-retry0"
        assert call2_options["workflow_id"] == f"turn-{agent_id}-1-retry2"
        assert call1_options["deduplication_id"] != call2_options["deduplication_id"]


class TestRecentActions:
    def test_load_agent_context_returns_recent_actions_from_memory(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import load_agent_context_step

        instance_id = uuid4()
        memory_id = uuid4()

        mock_profile = MagicMock()
        mock_profile.personality = "Test"
        mock_profile.model_name = "openai:gpt-4o-mini"
        mock_profile.model_params = None
        mock_profile.memory_compaction_strategy = "sliding_window"
        mock_profile.memory_compaction_config = None

        mock_simulation_run = MagicMock()
        mock_simulation_run.community_server_id = uuid4()

        mock_instance = MagicMock()
        mock_instance.id = instance_id
        mock_instance.agent_profile_id = uuid4()
        mock_instance.simulation_run_id = uuid4()
        mock_instance.user_profile_id = uuid4()
        mock_instance.turn_count = 3
        mock_instance.agent_profile = mock_profile
        mock_instance.simulation_run = mock_simulation_run

        mock_memory = MagicMock()
        mock_memory.id = memory_id
        mock_memory.message_history = []
        mock_memory.turn_count = 3
        mock_memory.recent_actions = ["write_note", "rate_note", "pass_turn"]

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

        assert result["recent_actions"] == ["write_note", "rate_note", "pass_turn"]
        assert result["community_server_id"] == str(mock_simulation_run.community_server_id)

    def test_load_agent_context_returns_empty_recent_actions_when_no_memory(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import load_agent_context_step

        instance_id = uuid4()

        mock_profile = MagicMock()
        mock_profile.personality = "Test"
        mock_profile.model_name = "openai:gpt-4o-mini"
        mock_profile.model_params = None
        mock_profile.memory_compaction_strategy = "sliding_window"
        mock_profile.memory_compaction_config = None

        mock_simulation_run = MagicMock()
        mock_simulation_run.community_server_id = uuid4()

        mock_instance = MagicMock()
        mock_instance.id = instance_id
        mock_instance.agent_profile_id = uuid4()
        mock_instance.simulation_run_id = uuid4()
        mock_instance.user_profile_id = uuid4()
        mock_instance.turn_count = 0
        mock_instance.agent_profile = mock_profile
        mock_instance.simulation_run = mock_simulation_run

        mock_session = AsyncMock()
        instance_result = MagicMock()
        instance_result.scalar_one_or_none.return_value = mock_instance
        memory_result = MagicMock()
        memory_result.scalar_one_or_none.return_value = None
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

        assert result["recent_actions"] == []

    def test_persist_state_appends_action_type_to_recent_actions(self) -> None:
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
            persist_state_step.__wrapped__(
                agent_instance_id=agent_instance_id,
                memory_id=memory_id,
                new_messages=new_messages,
                action=action,
                recent_actions=["pass_turn", "rate_note"],
            )

        memory_update_stmt = mock_session.execute.call_args_list[0].args[0]
        compiled = memory_update_stmt.compile()
        assert "recent_actions" in str(compiled)
        assert compiled.params["recent_actions"] == ["pass_turn", "rate_note", "write_note"]

    def test_persist_state_trims_recent_actions_to_last_5(self) -> None:
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
            persist_state_step.__wrapped__(
                agent_instance_id=agent_instance_id,
                memory_id=memory_id,
                new_messages=new_messages,
                action=action,
                recent_actions=["a1", "a2", "a3", "a4", "a5"],
            )

        memory_update_stmt = mock_session.execute.call_args_list[0].args[0]
        compiled = memory_update_stmt.compile()
        assert compiled.params["recent_actions"] == ["a2", "a3", "a4", "a5", "write_note"]

    def test_persist_state_upsert_includes_recent_actions(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import persist_state_step

        agent_instance_id = str(uuid4())
        new_messages = [{"kind": "response", "parts": []}]
        action = {"action_type": "rate_note", "reasoning": "first turn"}

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
            persist_state_step.__wrapped__(
                agent_instance_id=agent_instance_id,
                memory_id=None,
                new_messages=new_messages,
                action=action,
                recent_actions=[],
            )

        upsert_stmt = mock_session.execute.call_args_list[0].args[0]
        compiled = upsert_stmt.compile()
        assert "recent_actions" in str(compiled)
        assert compiled.params["recent_actions"] == ["rate_note"]

    def test_persist_state_defaults_recent_actions_to_empty(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import persist_state_step

        agent_instance_id = str(uuid4())
        memory_id = str(uuid4())
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
            persist_state_step.__wrapped__(
                agent_instance_id=agent_instance_id,
                memory_id=memory_id,
                new_messages=new_messages,
                action=action,
            )

        memory_update_stmt = mock_session.execute.call_args_list[0].args[0]
        compiled = memory_update_stmt.compile()
        assert compiled.params["recent_actions"] == ["pass_turn"]

    def test_run_agent_turn_passes_recent_actions_to_persist(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(
            agent_instance_id=agent_instance_id,
            recent_actions=["write_note", "rate_note"],
        )

        captured_persist_kwargs: dict = {}

        def capture_persist(**kwargs):
            captured_persist_kwargs.update(kwargs)
            return {
                "agent_instance_id": agent_instance_id,
                "action_type": "write_note",
                "persisted": True,
            }

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
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                return_value={
                    "action_type": "write_note",
                    "reasoning": "Found work",
                    "phase1_messages": [],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                return_value={
                    "action": {"action_type": "write_note", "reasoning": "wrote note"},
                    "new_messages": [],
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                side_effect=capture_persist,
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert captured_persist_kwargs["recent_actions"] == ["write_note", "rate_note"]


class TestTwoPhaseFlow:
    def test_run_agent_turn_with_phase1_write_note(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)
        phase1_msgs = [{"kind": "response", "parts": [{"part_kind": "text", "content": "phase1"}]}]

        captured_execute_kwargs: dict = {}

        def capture_execute(**kwargs):
            captured_execute_kwargs.update(kwargs)
            return {
                "action": {"action_type": "write_note", "reasoning": "wrote note"},
                "new_messages": [{"kind": "response"}],
            }

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
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                return_value={
                    "action_type": "write_note",
                    "reasoning": "There is a request",
                    "phase1_messages": phase1_msgs,
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                side_effect=capture_execute,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={
                    "agent_instance_id": agent_instance_id,
                    "action_type": "write_note",
                    "persisted": True,
                },
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert result["action"]["action_type"] == "write_note"
        assert captured_execute_kwargs["action_type"] == "write_note"
        assert captured_execute_kwargs["phase1_messages"] == phase1_msgs

    def test_run_agent_turn_skips_phase2_on_pass(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)
        phase1_msgs = [{"kind": "response", "parts": [{"part_kind": "text", "content": "pass"}]}]

        execute_called = False

        def track_execute(**kwargs):
            nonlocal execute_called
            execute_called = True
            return {
                "action": {"action_type": "write_note", "reasoning": "should not happen"},
                "new_messages": [],
            }

        captured_persist_kwargs: dict = {}

        def capture_persist(**kwargs):
            captured_persist_kwargs.update(kwargs)
            return {
                "agent_instance_id": agent_instance_id,
                "action_type": "pass_turn",
                "persisted": True,
            }

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
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                return_value={
                    "action_type": "pass_turn",
                    "reasoning": "Nothing to do",
                    "phase1_messages": phase1_msgs,
                },
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                side_effect=track_execute,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                side_effect=capture_persist,
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            result = run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert execute_called is False
        assert result["action"]["action_type"] == "pass_turn"
        assert result["action"]["reasoning"] == "Nothing to do"
        assert result["persisted"] is True
        assert captured_persist_kwargs["new_messages"] == phase1_msgs
        assert captured_persist_kwargs["action"]["action_type"] == "pass_turn"

    def test_run_agent_turn_pass_turn_step_order(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)
        call_order: list[str] = []

        def track(name, return_val):
            def fn(*args, **kwargs):
                call_order.append(name)
                return return_val

            return fn

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
                side_effect=track("load", context),
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.compact_memory_step",
                side_effect=track("compact", {"messages": [], "was_compacted": False}),
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.build_deps_step",
                side_effect=track("build", {"available_requests": [], "available_notes": []}),
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                side_effect=track(
                    "select",
                    {
                        "action_type": "pass_turn",
                        "reasoning": "idle",
                        "phase1_messages": [],
                    },
                ),
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.execute_agent_turn_step",
                side_effect=track(
                    "execute",
                    {
                        "action": {"action_type": "write_note", "reasoning": "x"},
                        "new_messages": [],
                    },
                ),
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                side_effect=track(
                    "persist",
                    {
                        "agent_instance_id": agent_instance_id,
                        "action_type": "pass_turn",
                        "persisted": True,
                    },
                ),
            ),
            patch("src.simulation.workflows.agent_turn_workflow.TokenGate"),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "wf-test"
            run_agent_turn.__wrapped__(agent_instance_id=agent_instance_id)

        assert call_order == ["load", "compact", "build", "select", "persist"]
        assert "execute" not in call_order

    def test_execute_agent_turn_step_with_action_type(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        deps_data = {
            "available_requests": [
                {"request_id": "req-001", "content": "test", "status": "PENDING"}
            ],
            "available_notes": [],
        }

        mock_action = MagicMock()
        mock_action.model_dump.return_value = {
            "action_type": "write_note",
            "reasoning": "Wrote a note",
        }

        captured_run_turn_kwargs: dict = {}

        async def capture_run_turn(**kwargs):
            captured_run_turn_kwargs.update(kwargs)
            return (mock_action, [])

        mock_agent_instance = MagicMock()
        mock_agent_instance.run_turn = AsyncMock(side_effect=capture_run_turn)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        phase1_msgs = [{"kind": "response", "parts": []}]

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
            patch(
                "src.simulation.workflows.agent_turn_workflow._deserialize_messages",
                return_value=[],
            ),
        ):
            result = execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
                action_type="write_note",
                phase1_messages=phase1_msgs,
            )

        assert result["action"]["action_type"] == "write_note"
        from src.simulation.schemas import SimActionType

        call_kwargs = mock_agent_instance.run_turn.call_args.kwargs
        assert call_kwargs["chosen_action_type"] == SimActionType.WRITE_NOTE

    def test_execute_agent_turn_step_without_action_type_preserves_original_behavior(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        deps_data = {
            "available_requests": [],
            "available_notes": [],
        }

        mock_action = MagicMock()
        mock_action.model_dump.return_value = {
            "action_type": "pass_turn",
            "reasoning": "Nothing to do",
        }

        captured_run_turn_kwargs: dict = {}

        async def capture_run_turn(**kwargs):
            captured_run_turn_kwargs.update(kwargs)
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
        assert call_kwargs["chosen_action_type"] is None

    def test_execute_agent_turn_step_uses_phase1_messages_as_history(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        deps_data = {"available_requests": [], "available_notes": []}

        mock_action = MagicMock()
        mock_action.model_dump.return_value = {
            "action_type": "write_note",
            "reasoning": "test",
        }

        captured_history: list = []

        async def capture_run_turn(**kwargs):
            captured_history.append(kwargs.get("message_history"))
            return (mock_action, [])

        mock_agent_instance = MagicMock()
        mock_agent_instance.run_turn = AsyncMock(side_effect=capture_run_turn)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        phase1_sentinel = [
            {"kind": "response", "parts": [{"part_kind": "text", "content": "phase1"}]}
        ]
        memory_sentinel = [
            {"kind": "request", "parts": [{"part_kind": "text", "content": "memory"}]}
        ]

        deserialized_phase1 = object()
        deserialized_memory = object()

        call_count = 0

        def mock_deserialize(data):
            nonlocal call_count
            if data == phase1_sentinel:
                return deserialized_phase1
            if data == memory_sentinel:
                return deserialized_memory
            call_count += 1
            return []

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
            patch(
                "src.simulation.workflows.agent_turn_workflow._deserialize_messages",
                side_effect=mock_deserialize,
            ),
        ):
            execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=memory_sentinel,
                action_type="write_note",
                phase1_messages=phase1_sentinel,
            )

        assert captured_history[0] is deserialized_phase1


class TestUsageLimitExceeded:
    def test_usage_limit_exceeded_returns_pass_turn(self) -> None:
        from pydantic_ai.exceptions import UsageLimitExceeded

        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        deps_data = {"available_requests": [], "available_notes": []}
        messages: list = []

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_agent = MagicMock()
        mock_agent.run_turn = AsyncMock(
            side_effect=UsageLimitExceeded("Exceeded total_tokens_limit of 4000")
        )

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
                return_value=mock_agent,
            ),
        ):
            result = execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=messages,
            )

        assert result["action"]["action_type"] == "pass_turn"
        assert "usage limit exceeded" in result["action"]["reasoning"].lower()
        assert result["new_messages"] == messages

    def test_usage_limit_preserves_phase1_messages(self) -> None:
        from pydantic_ai.exceptions import UsageLimitExceeded

        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        deps_data = {"available_requests": [], "available_notes": []}
        old_messages: list = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "old"}]}
        ]
        phase1_msgs: list = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "phase1"}]}
        ]

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_agent = MagicMock()
        mock_agent.run_turn = AsyncMock(
            side_effect=UsageLimitExceeded("Exceeded total_tokens_limit of 4000")
        )

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
                return_value=mock_agent,
            ),
        ):
            result = execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=old_messages,
                phase1_messages=phase1_msgs,
            )

        assert result["action"]["action_type"] == "pass_turn"
        assert result["new_messages"] == phase1_msgs
        assert result["new_messages"] != old_messages

    def test_usage_limit_partial_result_is_persisted(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import persist_state_step

        agent_instance_id = str(uuid4())
        memory_id = str(uuid4())
        action = {"action_type": "pass_turn", "reasoning": "Turn ended early: usage limit exceeded"}

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
                new_messages=[],
                action=action,
                recent_actions=["write_note"],
            )

        assert result["persisted"] is True
        assert result["action_type"] == "pass_turn"


class TestConfigurableDefaults:
    def test_settings_has_simulation_default_request_limit(self) -> None:
        from src.config import get_settings

        settings = get_settings()
        assert settings.SIMULATION_DEFAULT_REQUEST_LIMIT == 3

    def test_settings_has_simulation_default_token_limit(self) -> None:
        from src.config import get_settings

        settings = get_settings()
        assert settings.SIMULATION_DEFAULT_TOKEN_LIMIT == 4000

    def test_settings_has_simulation_compaction_interval(self) -> None:
        from src.config import get_settings

        settings = get_settings()
        assert settings.SIMULATION_COMPACTION_INTERVAL == 2

    def test_execute_agent_turn_uses_settings_defaults_when_no_model_params(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        context["model_params"] = {}
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

        mock_settings = MagicMock()
        mock_settings.SIMULATION_DEFAULT_REQUEST_LIMIT = 10
        mock_settings.SIMULATION_DEFAULT_TOKEN_LIMIT = 9000

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
            patch(
                "src.simulation.workflows.agent_turn_workflow.get_settings",
                return_value=mock_settings,
            ),
        ):
            execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

        call_kwargs = mock_agent_instance.run_turn.call_args.kwargs
        limits = call_kwargs["usage_limits"]
        assert limits.request_limit == 10
        assert limits.total_tokens_limit == 9000

    def test_per_agent_model_params_override_settings_defaults(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import execute_agent_turn_step

        context = _make_context()
        context["model_params"] = {"request_limit": 7, "total_tokens_limit": 5000}
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

        mock_settings = MagicMock()
        mock_settings.SIMULATION_DEFAULT_REQUEST_LIMIT = 10
        mock_settings.SIMULATION_DEFAULT_TOKEN_LIMIT = 9000

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
            patch(
                "src.simulation.workflows.agent_turn_workflow.get_settings",
                return_value=mock_settings,
            ),
        ):
            execute_agent_turn_step.__wrapped__(
                context=context,
                deps_data=deps_data,
                messages=[],
            )

        call_kwargs = mock_agent_instance.run_turn.call_args.kwargs
        limits = call_kwargs["usage_limits"]
        assert limits.request_limit == 7
        assert limits.total_tokens_limit == 5000

    def test_run_agent_turn_uses_settings_compaction_interval(self) -> None:
        from src.simulation.workflows.agent_turn_workflow import run_agent_turn

        agent_instance_id = str(uuid4())
        context = _make_context(agent_instance_id=agent_instance_id)

        mock_settings = MagicMock()
        mock_settings.SIMULATION_COMPACTION_INTERVAL = 5

        mock_gate = MagicMock()

        mock_selection = {
            "action_type": "pass_turn",
            "reasoning": "test",
            "phase1_messages": [],
        }

        with (
            patch(
                "src.simulation.workflows.agent_turn_workflow.TokenGate",
                return_value=mock_gate,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.load_agent_context_step",
                return_value=context,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.compact_memory_step",
                return_value={"messages": [], "was_compacted": False},
            ) as mock_compact,
            patch(
                "src.simulation.workflows.agent_turn_workflow.build_deps_step",
                return_value={"available_requests": [], "available_notes": []},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.select_action_step",
                return_value=mock_selection,
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.persist_state_step",
                return_value={"persisted": True, "action_type": "pass_turn"},
            ),
            patch(
                "src.simulation.workflows.agent_turn_workflow.get_settings",
                return_value=mock_settings,
            ),
            patch("src.simulation.workflows.agent_turn_workflow.DBOS") as mock_dbos,
        ):
            mock_dbos.workflow_id = "test-wf-id"
            run_agent_turn.__wrapped__(agent_instance_id)

        mock_compact.assert_called_once()
        call_kwargs = mock_compact.call_args.kwargs
        assert call_kwargs["compaction_interval"] == 5
