from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.llm_config.model_id import ModelId
from src.simulation.agent import OpenNotesSimAgent, SimAgentDeps
from src.simulation.schemas import ActionSelectionResult, SimActionType


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


def _make_run_result(data, messages=None):
    result = MagicMock()
    result.output = data
    result.all_messages.return_value = messages or []
    return result


class TestMessageHistorySafety:
    @pytest.mark.asyncio
    async def test_message_history_not_corrupted_when_run_mutates_list(self, sample_deps):
        """Verify that even if agent.run() mutates the message_history list
        in-place, select_action's original list stays intact.

        This simulates what could happen if a future pydantic-ai version
        stopped copying message_history internally during retries.
        """
        agent = OpenNotesSimAgent()
        original_history: list = [MagicMock(spec_set=["role"])]
        original_len = len(original_history)

        call_count = 0
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        write_result = ActionSelectionResult(action_type=SimActionType.WRITE_NOTE, reasoning="ok")

        async def mutating_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            history = kwargs.get("message_history")
            if history is not None:
                history.append(MagicMock(spec_set=["role"]))
            if call_count == 1:
                return _make_run_result(pass_result)
            return _make_run_result(write_result)

        with patch.object(
            agent._action_selector,
            "run",
            side_effect=mutating_side_effect,
        ):
            await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
                message_history=original_history,
            )

        assert len(original_history) == original_len, (
            f"message_history was mutated in-place: expected {original_len} items, "
            f"got {len(original_history)}"
        )

    @pytest.mark.asyncio
    async def test_each_run_call_receives_independent_copy(self, sample_deps):
        """Each call to _action_selector.run() should get its own list copy,
        so mutations in one call don't leak to the next."""
        agent = OpenNotesSimAgent()
        original_history: list = [MagicMock(spec_set=["role"])]

        captured_histories: list[list] = []
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        final_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="still nothing"
        )

        async def capturing_side_effect(*args, **kwargs):
            history = kwargs.get("message_history")
            captured_histories.append(history)
            if len(captured_histories) < 3:
                return _make_run_result(pass_result)
            return _make_run_result(final_result)

        with patch.object(
            agent._action_selector,
            "run",
            side_effect=capturing_side_effect,
        ):
            await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
                message_history=original_history,
            )

        assert len(captured_histories) == 3
        for i, h in enumerate(captured_histories):
            assert h is not original_history, (
                f"Call {i} received the original list object instead of a copy"
            )
        for i in range(len(captured_histories)):
            for j in range(i + 1, len(captured_histories)):
                assert captured_histories[i] is not captured_histories[j], (
                    f"Calls {i} and {j} received the same list object"
                )

    @pytest.mark.asyncio
    async def test_none_message_history_stays_none(self, sample_deps):
        """When message_history is None, it should be passed as None (not [])."""
        agent = OpenNotesSimAgent()
        write_result = ActionSelectionResult(action_type=SimActionType.WRITE_NOTE, reasoning="go")

        with patch.object(
            agent._action_selector,
            "run",
            new_callable=AsyncMock,
            return_value=_make_run_result(write_result),
        ) as mock_run:
            await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
                message_history=None,
            )
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["message_history"] is None
