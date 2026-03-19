from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.llm_config.model_id import ModelId
from src.simulation.agent import (
    CHANNEL_RATE_LIMIT_MAX,
    CHANNEL_SIMILARITY_THRESHOLD,
    MAX_CHANNEL_MESSAGE_LENGTH,
    SimAgentDeps,
    post_to_channel,
    read_channel,
    sim_agent,
)

_TEST_MODEL_ID = ModelId.from_pydantic_ai("openai:gpt-4o-mini")


def _make_dedup_execute(rate_count=0, recent_texts=None):
    if recent_texts is None:
        recent_texts = []

    rate_result = MagicMock()
    rate_result.scalar_one.return_value = rate_count

    sim_result = MagicMock()
    sim_result.scalars.return_value.all.return_value = recent_texts

    return AsyncMock(side_effect=[rate_result, sim_result])


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = _make_dedup_execute()
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

    @pytest.mark.asyncio
    async def test_rejects_empty_message(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="")

        assert "Error" in result
        assert "empty" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_whitespace_only_message(self, sample_deps):
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="   \n\t  ")

        assert "Error" in result
        assert "empty" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_rolls_back_session_on_db_error(self, sample_deps):
        from sqlalchemy.exc import SQLAlchemyError

        sample_deps.db.flush = AsyncMock(side_effect=SQLAlchemyError("connection lost"))
        sample_deps.db.rollback = AsyncMock()
        ctx = MagicMock()
        ctx.deps = sample_deps

        await post_to_channel(ctx, message="Hello")

        sample_deps.db.rollback.assert_awaited_once()


class TestPostToChannelDedup:
    @pytest.mark.asyncio
    async def test_rejects_exact_duplicate_message(self, sample_deps):
        sample_deps.db.execute = _make_dedup_execute(rate_count=0, recent_texts=["Hello agents"])
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Hello agents")

        assert "too similar" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_near_duplicate_message(self, sample_deps):
        original = "This claim about vaccines is misleading because it misquotes the study."
        near_dup = "This claim about vaccines is misleading because it misquotes the study!"
        from difflib import SequenceMatcher

        assert SequenceMatcher(None, near_dup, original).ratio() > CHANNEL_SIMILARITY_THRESHOLD

        sample_deps.db.execute = _make_dedup_execute(rate_count=0, recent_texts=[original])
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message=near_dup)

        assert "too similar" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_distinct_message(self, sample_deps):
        sample_deps.db.execute = _make_dedup_execute(
            rate_count=0,
            recent_texts=["The weather today is quite pleasant and warm."],
        )
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(
            ctx, message="I found evidence that this claim is false based on the CDC data."
        )

        assert result == "Posted to channel."
        sample_deps.db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_message_when_no_recent_history(self, sample_deps):
        sample_deps.db.execute = _make_dedup_execute(rate_count=0, recent_texts=[])
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="First message ever!")

        assert result == "Posted to channel."
        sample_deps.db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_checks_similarity_against_multiple_recent_messages(self, sample_deps):
        recent = [
            "Completely different topic about birds.",
            "Another unrelated discussion about music.",
            "Hello agents, let me share my findings.",
        ]
        sample_deps.db.execute = _make_dedup_execute(rate_count=0, recent_texts=recent)
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Hello agents, let me share my findings.")

        assert "too similar" in result
        sample_deps.db.add.assert_not_called()


class TestPostToChannelRateLimit:
    @pytest.mark.asyncio
    async def test_rejects_when_rate_limit_exceeded(self, sample_deps):
        sample_deps.db.execute = _make_dedup_execute(
            rate_count=CHANNEL_RATE_LIMIT_MAX + 1, recent_texts=[]
        )
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Yet another message")

        assert "Rate limit" in result
        assert "please wait" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_at_rate_limit_boundary(self, sample_deps):
        sample_deps.db.execute = _make_dedup_execute(
            rate_count=CHANNEL_RATE_LIMIT_MAX, recent_texts=[]
        )
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Message at limit boundary")

        assert "Rate limit" in result
        assert "please wait" in result
        sample_deps.db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_below_rate_limit_boundary(self, sample_deps):
        sample_deps.db.execute = _make_dedup_execute(
            rate_count=CHANNEL_RATE_LIMIT_MAX - 1, recent_texts=[]
        )
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Message below limit")

        assert result == "Posted to channel."
        sample_deps.db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_after_cooldown(self, sample_deps):
        sample_deps.db.execute = _make_dedup_execute(rate_count=0, recent_texts=[])
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Back after cooldown")

        assert result == "Posted to channel."
        sample_deps.db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_checked_before_similarity(self, sample_deps):
        sample_deps.db.execute = _make_dedup_execute(
            rate_count=CHANNEL_RATE_LIMIT_MAX + 1, recent_texts=["Same message"]
        )
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await post_to_channel(ctx, message="Same message")

        assert "Rate limit" in result
        assert sample_deps.db.execute.await_count == 1


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
        interesting_pos = result.index("Found something interesting")
        confirming_pos = result.index("Confirming pattern")
        assert interesting_pos < confirming_pos

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

    @pytest.mark.asyncio
    async def test_handles_db_error(self, sample_deps):
        from sqlalchemy.exc import SQLAlchemyError

        sample_deps.db.execute = AsyncMock(side_effect=SQLAlchemyError("connection lost"))
        sample_deps.db.rollback = AsyncMock()
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await read_channel(ctx)

        assert "Error" in result
        assert "database error" in result
        sample_deps.db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_no_messages_when_empty(self, sample_deps):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        sample_deps.db.execute = AsyncMock(return_value=mock_result)
        ctx = MagicMock()
        ctx.deps = sample_deps

        result = await read_channel(ctx)

        assert result == "No channel messages yet."
