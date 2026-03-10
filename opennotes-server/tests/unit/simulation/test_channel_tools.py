from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.llm_config.model_id import ModelId
from src.simulation.agent import (
    MAX_CHANNEL_MESSAGE_LENGTH,
    SimAgentDeps,
    post_to_channel,
    read_channel,
    sim_agent,
)

_TEST_MODEL_ID = ModelId.from_pydantic_ai("openai:gpt-4o-mini")


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
        available_requests=[],
        available_notes=[],
        agent_personality="test",
        model_name=_TEST_MODEL_ID,
        simulation_run_id=uuid4(),
    )


class TestToolsRegistered:
    def _get_tool_names(self):
        return list(sim_agent._function_toolset.tools.keys())

    def test_post_to_channel_registered(self):
        assert "post_to_channel" in self._get_tool_names()

    def test_read_channel_registered(self):
        assert "read_channel" in self._get_tool_names()


class TestPostToChannel:
    @pytest.mark.asyncio
    async def test_persists_message(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Hello agents")

        sample_deps.db.add.assert_called_once()
        sample_deps.db.flush.assert_awaited_once()
        msg = sample_deps.db.add.call_args[0][0]
        assert msg.message_text == "Hello agents"
        assert msg.simulation_run_id == sample_deps.simulation_run_id
        assert msg.agent_instance_id == sample_deps.agent_instance_id
        assert result == "Posted to channel."

    @pytest.mark.asyncio
    async def test_returns_error_when_no_simulation_run_id(self, mock_db):
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="test",
            model_name=_TEST_MODEL_ID,
            simulation_run_id=None,
        )
        ctx = MagicMock()
        ctx.deps = deps

        result = await post_to_channel(ctx, message="Hello")

        assert "Error" in result
        assert "no simulation_run_id" in result
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_message_exceeding_max_length(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        long_message = "x" * (MAX_CHANNEL_MESSAGE_LENGTH + 1)

        result = await post_to_channel(ctx, message=long_message)

        assert "Error" in result
        assert "too long" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_message_at_max_length(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps
        exact_message = "x" * MAX_CHANNEL_MESSAGE_LENGTH

        result = await post_to_channel(ctx, message=exact_message)

        assert result == "Posted to channel."
        sample_deps.db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_db_error(self, sample_deps):
        from sqlalchemy.exc import SQLAlchemyError

        sample_deps.db.flush = AsyncMock(side_effect=SQLAlchemyError("connection lost"))
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Hello")

        assert "Error" in result
        assert "database error" in result


class TestReadChannel:
    @pytest.mark.asyncio
    async def test_returns_formatted_messages(self, sample_deps):
        agent_id = uuid4()
        mock_msg1 = MagicMock()
        mock_msg1.agent_instance_id = agent_id
        mock_msg1.message_text = "Found something interesting"
        mock_msg1.created_at = MagicMock()

        mock_msg2 = MagicMock()
        mock_msg2.agent_instance_id = agent_id
        mock_msg2.message_text = "Confirming pattern"
        mock_msg2.created_at = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_msg2, mock_msg1]

        sample_deps.db.execute = AsyncMock(return_value=mock_result)
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await read_channel(ctx)

        short_id = str(agent_id)[:8]
        assert f"[Agent {short_id}]" in result
        assert "Found something interesting" in result
        assert "Confirming pattern" in result

    @pytest.mark.asyncio
    async def test_returns_not_available_when_no_simulation_run_id(self, mock_db):
        deps = SimAgentDeps(
            db=mock_db,
            community_server_id=uuid4(),
            agent_instance_id=uuid4(),
            user_profile_id=uuid4(),
            available_requests=[],
            available_notes=[],
            agent_personality="test",
            model_name=_TEST_MODEL_ID,
            simulation_run_id=None,
        )
        ctx = MagicMock()
        ctx.deps = deps

        result = await read_channel(ctx)

        assert result == "Channel not available."
        mock_db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_no_messages_when_empty(self, sample_deps):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        sample_deps.db.execute = AsyncMock(return_value=mock_result)
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await read_channel(ctx)

        assert result == "No channel messages yet."
