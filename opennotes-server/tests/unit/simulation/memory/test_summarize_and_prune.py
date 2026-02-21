from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.simulation.memory.summarize_and_prune import SummarizeAndPruneCompactor


def _make_user_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": content}]}


def _make_response_message(content: str) -> dict[str, Any]:
    return {"kind": "response", "parts": [{"part_kind": "text", "content": content}]}


class TestSummarizeAndPruneCompactor:
    @pytest.mark.asyncio
    async def test_summarizes_old_messages(self):
        mock_summarizer = AsyncMock(return_value="Summary of old messages")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(20)]

        result = await compactor.compact(messages, {"keep_recent": 5})

        assert result.compacted_count == 6
        assert result.original_count == 20
        assert len(result.messages) == 6
        assert result.messages[0]["parts"][0]["content"] == "Summary of old messages"
        assert result.messages[1:] == messages[-5:]

    @pytest.mark.asyncio
    async def test_no_op_when_under_threshold(self):
        mock_summarizer = AsyncMock(return_value="Should not be called")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(3)]

        result = await compactor.compact(messages, {"keep_recent": 10})

        assert result.compacted_count == 3
        assert result.original_count == 3
        assert len(result.messages) == 3
        mock_summarizer.assert_not_called()

    @pytest.mark.asyncio
    async def test_summary_content_format(self):
        mock_summarizer = AsyncMock(return_value="Condensed history")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(15)]

        result = await compactor.compact(messages, {"keep_recent": 5})

        summary_msg = result.messages[0]
        assert summary_msg["kind"] == "request"
        assert summary_msg["parts"][0]["part_kind"] == "user-prompt"
        assert summary_msg["parts"][0]["content"] == "Condensed history"

    @pytest.mark.asyncio
    async def test_calls_summarizer_with_old_messages(self):
        mock_summarizer = AsyncMock(return_value="Summary")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(10)]

        await compactor.compact(messages, {"keep_recent": 3})

        mock_summarizer.assert_called_once()
        call_arg = mock_summarizer.call_args[0][0]
        assert "msg-0" in call_arg
        assert "msg-6" in call_arg
        assert "msg-7" not in call_arg

    @pytest.mark.asyncio
    async def test_default_keep_recent(self):
        mock_summarizer = AsyncMock(return_value="Summary")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(5)]

        result = await compactor.compact(messages, {})

        assert result.compacted_count == 5
        assert result.metadata["keep_recent"] == 10
        mock_summarizer.assert_not_called()

    @pytest.mark.asyncio
    async def test_metadata_includes_summarized_flag(self):
        mock_summarizer = AsyncMock(return_value="Summary")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(20)]

        result = await compactor.compact(messages, {"keep_recent": 5})

        assert result.strategy == "summarize_and_prune"
        assert result.metadata["summarized"] is True
        assert result.metadata["messages_summarized"] == 15

    @pytest.mark.asyncio
    async def test_metadata_not_summarized_when_under_threshold(self):
        mock_summarizer = AsyncMock(return_value="Summary")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(3)]

        result = await compactor.compact(messages, {"keep_recent": 10})

        assert result.metadata["summarized"] is False

    @pytest.mark.asyncio
    async def test_mixed_message_types(self):
        mock_summarizer = AsyncMock(return_value="Summary")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = []
        for i in range(10):
            if i % 2 == 0:
                messages.append(_make_user_message(f"user-{i}"))
            else:
                messages.append(_make_response_message(f"response-{i}"))

        result = await compactor.compact(messages, {"keep_recent": 3})

        assert result.compacted_count == 4
        assert result.messages[1:] == messages[-3:]
