from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.llm_config.model_id import ModelId
from src.simulation.agent import (
    OpenNotesSimAgent,
    SimAgentDeps,
    action_selector,
    build_queue_summary,
)
from src.simulation.schemas import ActionSelectionResult, SimActionType


def make_sequence_model(results: list[ActionSelectionResult]):
    call_count = 0

    def handler(messages: list, info: AgentInfo) -> ModelResponse:
        nonlocal call_count
        result = results[min(call_count, len(results) - 1)]
        call_count += 1
        return ModelResponse(parts=[TextPart(content=result.model_dump_json())])

    return FunctionModel(handler), lambda: call_count


def make_sequence_model_with_capture(results: list[ActionSelectionResult]):
    calls: list[list] = []

    def handler(messages: list, info: AgentInfo) -> ModelResponse:
        calls.append(messages)
        result = results[min(len(calls) - 1, len(results) - 1)]
        return ModelResponse(parts=[TextPart(content=result.model_dump_json())])

    return FunctionModel(handler), calls


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_deps(mock_db):
    return SimAgentDeps(
        db=mock_db,
        community_server_id=uuid4(),
        agent_instance_id=uuid4(),
        user_profile_id=uuid4(),
        available_requests=[
            {
                "id": str(uuid4()),
                "request_id": "prov-test",
                "content": "Test content",
                "status": "PENDING",
                "notes": [],
            },
        ],
        available_notes=[
            {
                "note_id": str(uuid4()),
                "summary": "Test note",
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
            },
        ],
        agent_personality="Skeptical fact-checker",
        model_name=ModelId.from_pydantic_ai("openai:gpt-4o-mini"),
    )


class TestSelectAction:
    @pytest.mark.asyncio
    async def test_non_pass_skips_retry(self, sample_deps):
        """When Phase 1 returns write_note, no retry needed."""
        agent = OpenNotesSimAgent()
        write_result = ActionSelectionResult(
            action_type=SimActionType.WRITE_NOTE, reasoning="want to write"
        )

        model, get_count = make_sequence_model([write_result])
        with action_selector.override(model=model):
            result, _messages = await agent.select_action(
                deps=sample_deps,
                recent_actions=["write_note"],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.WRITE_NOTE
            assert get_count() == 1

    @pytest.mark.asyncio
    async def test_pass_triggers_retry_with_verbose(self, sample_deps):
        """When Phase 1 returns pass, retry with verbose summary."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing to do"
        )
        write_result = ActionSelectionResult(
            action_type=SimActionType.WRITE_NOTE, reasoning="reconsidered"
        )

        model, get_count = make_sequence_model([pass_result, write_result])
        with action_selector.override(model=model):
            result, _messages = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.WRITE_NOTE
            assert get_count() == 2

    @pytest.mark.asyncio
    async def test_triple_pass_returns_pass(self, sample_deps):
        """When all retries return pass (with notes available), final result is pass."""
        agent = OpenNotesSimAgent()
        pass_result1 = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing to do"
        )
        pass_result2 = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="still nothing"
        )
        pass_result3 = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="really nothing"
        )

        model, get_count = make_sequence_model([pass_result1, pass_result2, pass_result3])
        with action_selector.override(model=model):
            result, _messages = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.PASS_TURN
            assert get_count() == 3

    @pytest.mark.asyncio
    async def test_retry_uses_verbose_queue_summary(self, sample_deps):
        """The retry calls build_queue_summary with verbose=True."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        write_result = ActionSelectionResult(action_type=SimActionType.WRITE_NOTE, reasoning="ok")

        model, _get_count = make_sequence_model([pass_result, write_result])
        with (
            action_selector.override(model=model),
            patch(
                "src.simulation.agent.build_queue_summary",
                wraps=build_queue_summary,
            ) as mock_summary,
        ):
            _result, _ = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            calls = mock_summary.call_args_list
            assert len(calls) == 2
            assert calls[0].kwargs.get("verbose", False) is False
            assert calls[1].kwargs.get("verbose") is True

    @pytest.mark.asyncio
    async def test_rate_note_skips_retry(self, sample_deps):
        """When Phase 1 returns rate_note, no retry needed."""
        agent = OpenNotesSimAgent()
        rate_result = ActionSelectionResult(
            action_type=SimActionType.RATE_NOTE, reasoning="want to rate"
        )

        model, get_count = make_sequence_model([rate_result])
        with action_selector.override(model=model):
            result, _ = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.RATE_NOTE
            assert get_count() == 1

    @pytest.mark.asyncio
    async def test_retry_passes_defensive_copy_of_message_history(self, sample_deps):
        """The retry uses a defensive copy of the original message_history,
        not result.all_messages()."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        write_result = ActionSelectionResult(action_type=SimActionType.WRITE_NOTE, reasoning="ok")

        model, captured_calls = make_sequence_model_with_capture([pass_result, write_result])
        with action_selector.override(model=model):
            await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
                message_history=None,
            )
            assert len(captured_calls) == 2

    @pytest.mark.asyncio
    async def test_soft_guard_third_retry_when_notes_available(self, sample_deps):
        """Third retry fires when pass persists after verbose retry and notes > 0."""
        agent = OpenNotesSimAgent()
        pass_result1 = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        pass_result2 = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="still nothing"
        )
        rate_result = ActionSelectionResult(
            action_type=SimActionType.RATE_NOTE, reasoning="ok fine"
        )

        model, get_count = make_sequence_model([pass_result1, pass_result2, rate_result])
        with action_selector.override(model=model):
            result, _ = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.RATE_NOTE
            assert get_count() == 3

    @pytest.mark.asyncio
    async def test_no_soft_guard_when_nothing_available_legacy(self, sample_deps):
        """No retries when both notes and requests are empty (legitimate pass)."""
        agent = OpenNotesSimAgent()
        pass_result1 = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )

        model, get_count = make_sequence_model([pass_result1])
        with action_selector.override(model=model):
            result, _ = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=[],
                notes=[],
            )
            assert result.action_type == SimActionType.PASS_TURN
            assert get_count() == 1

    @pytest.mark.asyncio
    async def test_soft_guard_fires_for_requests_only(self, sample_deps):
        """Third retry fires when pass persists and requests > 0 but notes == 0."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        write_result = ActionSelectionResult(
            action_type=SimActionType.WRITE_NOTE, reasoning="ok fine"
        )

        model, captured_calls = make_sequence_model_with_capture(
            [pass_result, pass_result, write_result]
        )
        with action_selector.override(model=model):
            result, _ = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=[],
            )
            assert result.action_type == SimActionType.WRITE_NOTE
            assert len(captured_calls) == 3
            third_messages = captured_calls[2]
            last_user_content = ""
            for msg in reversed(third_messages):
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if hasattr(part, "content") and isinstance(part.content, str):
                            last_user_content = part.content
                            break
                    if last_user_content:
                        break
            assert "request" in last_user_content.lower()

    @pytest.mark.asyncio
    async def test_no_soft_guard_when_nothing_available(self, sample_deps):
        """No retries when both notes and requests are empty."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )

        model, get_count = make_sequence_model([pass_result])
        with action_selector.override(model=model):
            result, _ = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=[],
                notes=[],
            )
            assert result.action_type == SimActionType.PASS_TURN
            assert get_count() == 1

    @pytest.mark.asyncio
    async def test_soft_guard_prompt_mentions_notes(self, sample_deps):
        """Third retry prompt mentions available notes."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        rate_result = ActionSelectionResult(action_type=SimActionType.RATE_NOTE, reasoning="ok")

        model, captured_calls = make_sequence_model_with_capture(
            [pass_result, pass_result, rate_result]
        )
        with action_selector.override(model=model):
            await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert len(captured_calls) == 3
            third_messages = captured_calls[2]
            last_user_content = ""
            for msg in reversed(third_messages):
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if hasattr(part, "content") and isinstance(part.content, str):
                            last_user_content = part.content
                            break
                    if last_user_content:
                        break
            assert "note" in last_user_content.lower()

    @pytest.mark.asyncio
    async def test_empty_work_skips_all_retries(self, sample_deps):
        """When requests and notes are both empty, no retries fire."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing to do"
        )

        model, get_count = make_sequence_model([pass_result])
        with action_selector.override(model=model):
            _result, _messages = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=[],
                notes=[],
            )
            assert get_count() == 1

    @pytest.mark.asyncio
    async def test_empty_work_returns_pass_turn_immediately(self, sample_deps):
        """When requests and notes are both empty, PASS_TURN is returned immediately."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing to do"
        )

        model, _get_count = make_sequence_model([pass_result])
        with action_selector.override(model=model):
            result, _messages = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=[],
                notes=[],
            )
            assert result.action_type == SimActionType.PASS_TURN
