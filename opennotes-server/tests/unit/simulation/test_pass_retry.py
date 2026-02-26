from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.llm_config.model_id import ModelId
from src.simulation.agent import OpenNotesSimAgent, SimAgentDeps, build_queue_summary
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
                "request_id": str(uuid4()),
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
    result.data = data
    result.all_messages.return_value = messages or []
    return result


class TestSelectAction:
    @pytest.mark.asyncio
    async def test_non_pass_skips_retry(self, sample_deps):
        """When Phase 1 returns write_note, no retry needed."""
        agent = OpenNotesSimAgent()
        write_result = ActionSelectionResult(
            action_type=SimActionType.WRITE_NOTE, reasoning="want to write"
        )

        with patch.object(
            agent._action_selector,
            "run",
            new_callable=AsyncMock,
            return_value=_make_run_result(write_result),
        ) as mock_run:
            result, _messages = await agent.select_action(
                deps=sample_deps,
                recent_actions=["write_note"],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.WRITE_NOTE
            assert mock_run.call_count == 1

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

        with patch.object(
            agent._action_selector,
            "run",
            new_callable=AsyncMock,
            side_effect=[
                _make_run_result(pass_result, [{"role": "user", "content": "phase1"}]),
                _make_run_result(write_result, [{"role": "user", "content": "retry"}]),
            ],
        ) as mock_run:
            result, _messages = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.WRITE_NOTE
            assert mock_run.call_count == 2

    @pytest.mark.asyncio
    async def test_double_pass_returns_pass(self, sample_deps):
        """When Phase 1 returns pass both times, final result is pass."""
        agent = OpenNotesSimAgent()
        pass_result1 = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing to do"
        )
        pass_result2 = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="still nothing"
        )

        with patch.object(
            agent._action_selector,
            "run",
            new_callable=AsyncMock,
            side_effect=[
                _make_run_result(pass_result1),
                _make_run_result(pass_result2),
            ],
        ) as mock_run:
            result, _messages = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.PASS_TURN
            assert mock_run.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_uses_verbose_queue_summary(self, sample_deps):
        """The retry calls build_queue_summary with verbose=True."""
        agent = OpenNotesSimAgent()
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        write_result = ActionSelectionResult(action_type=SimActionType.WRITE_NOTE, reasoning="ok")

        with (
            patch.object(
                agent._action_selector,
                "run",
                new_callable=AsyncMock,
                side_effect=[
                    _make_run_result(pass_result),
                    _make_run_result(write_result),
                ],
            ),
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

        with patch.object(
            agent._action_selector,
            "run",
            new_callable=AsyncMock,
            return_value=_make_run_result(rate_result),
        ) as mock_run:
            result, _ = await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            assert result.action_type == SimActionType.RATE_NOTE
            assert mock_run.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_passes_message_history(self, sample_deps):
        """The retry passes the first run's messages as message_history."""
        agent = OpenNotesSimAgent()
        first_messages = [MagicMock(spec_set=["role"])]
        pass_result = ActionSelectionResult(
            action_type=SimActionType.PASS_TURN, reasoning="nothing"
        )
        write_result = ActionSelectionResult(action_type=SimActionType.WRITE_NOTE, reasoning="ok")

        with patch.object(
            agent._action_selector,
            "run",
            new_callable=AsyncMock,
            side_effect=[
                _make_run_result(pass_result, first_messages),
                _make_run_result(write_result),
            ],
        ) as mock_run:
            await agent.select_action(
                deps=sample_deps,
                recent_actions=[],
                requests=sample_deps.available_requests,
                notes=sample_deps.available_notes,
            )
            retry_call = mock_run.call_args_list[1]
            assert retry_call.kwargs.get("message_history") is first_messages
