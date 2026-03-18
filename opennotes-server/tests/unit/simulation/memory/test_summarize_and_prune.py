from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.simulation.memory.summarize_and_prune import SummarizeAndPruneCompactor


def _make_user_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": content}]}


def _make_response_message(content: str) -> dict[str, Any]:
    return {"kind": "response", "parts": [{"part_kind": "text", "content": content}]}


def _make_tool_call_response(
    tool_name: str = "test_tool", args: str = "{}", tool_call_id: str = "call-1"
) -> dict[str, Any]:
    return {
        "kind": "response",
        "parts": [
            {
                "part_kind": "tool-call",
                "tool_name": tool_name,
                "args": args,
                "tool_call_id": tool_call_id,
            }
        ],
    }


def _make_tool_return_request(
    tool_name: str = "test_tool", content: str = "result", tool_call_id: str = "call-1"
) -> dict[str, Any]:
    return {
        "kind": "request",
        "parts": [
            {
                "part_kind": "tool-return",
                "tool_name": tool_name,
                "content": content,
                "tool_call_id": tool_call_id,
            }
        ],
    }


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
    async def test_summary_uses_system_prompt_part_kind(self):
        mock_summarizer = AsyncMock(return_value="Condensed history")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(15)]

        result = await compactor.compact(messages, {"keep_recent": 5})

        summary_msg = result.messages[0]
        assert summary_msg["kind"] == "request"
        assert summary_msg["parts"][0]["part_kind"] == "system-prompt"
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

    @pytest.mark.asyncio
    async def test_summary_not_user_prompt(self):
        mock_summarizer = AsyncMock(return_value="Summary")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [_make_user_message(f"msg-{i}") for i in range(15)]

        result = await compactor.compact(messages, {"keep_recent": 5})

        summary_msg = result.messages[0]
        assert summary_msg["parts"][0]["part_kind"] != "user-prompt"


class TestSummarizeAndPruneToolPairs:
    @pytest.mark.asyncio
    async def test_tool_pair_straddling_boundary_kept_in_recent(self):
        mock_summarizer = AsyncMock(return_value="Summary of old")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)

        messages: list[dict[str, Any]] = []
        for i in range(9):
            messages.append(_make_user_message(f"msg-{i}"))
        messages.append(_make_tool_call_response("lookup", "{}", "call-9"))
        messages.append(_make_tool_return_request("lookup", "result-10", "call-9"))
        for i in range(11, 15):
            messages.append(_make_user_message(f"msg-{i}"))

        assert len(messages) == 15

        result = await compactor.compact(messages, {"keep_recent": 5})

        recent = result.messages[1:]
        assert messages[9] in recent, "tool_call at index 9 must be in recent"
        assert messages[10] in recent, "tool_return at index 10 must be in recent"
        assert result.metadata["messages_summarized"] == 9

    @pytest.mark.asyncio
    async def test_tool_pair_entirely_in_old_section_summarized(self):
        mock_summarizer = AsyncMock(return_value="Summary with tool context")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)

        messages: list[dict[str, Any]] = []
        messages.append(_make_user_message("msg-0"))
        messages.append(_make_user_message("msg-1"))
        messages.append(_make_tool_call_response("search", "{}", "call-2"))
        messages.append(_make_tool_return_request("search", "found-it", "call-2"))
        for i in range(4, 15):
            messages.append(_make_user_message(f"msg-{i}"))

        assert len(messages) == 15

        result = await compactor.compact(messages, {"keep_recent": 5})

        mock_summarizer.assert_called_once()
        call_arg = mock_summarizer.call_args[0][0]
        assert "found-it" in call_arg
        assert result.metadata["messages_summarized"] == 10
        assert result.messages[1:] == messages[-5:]

    @pytest.mark.asyncio
    async def test_multiple_tool_returns_straddling_boundary(self):
        mock_summarizer = AsyncMock(return_value="Summary")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)

        messages: list[dict[str, Any]] = []
        for i in range(8):
            messages.append(_make_user_message(f"msg-{i}"))
        messages.append(_make_tool_call_response("multi", "{}", "call-8"))
        messages.append(_make_tool_return_request("multi", "ret-9", "call-8"))
        messages.append(_make_tool_return_request("multi", "ret-10", "call-8"))
        for i in range(11, 15):
            messages.append(_make_user_message(f"msg-{i}"))

        assert len(messages) == 15

        result = await compactor.compact(messages, {"keep_recent": 5})

        recent = result.messages[1:]
        assert messages[8] in recent, "tool_call at index 8 must be in recent"
        assert messages[9] in recent, "tool_return at index 9 must be in recent"
        assert messages[10] in recent, "tool_return at index 10 must be in recent"
        assert result.metadata["messages_summarized"] == 8


class TestSummarizeAndPrunePydanticAiTypes:
    @pytest.mark.asyncio
    async def test_extracts_text_from_pydantic_ai_messages(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        mock_summarizer = AsyncMock(return_value="Summary")
        compactor = SummarizeAndPruneCompactor(summarizer=mock_summarizer)
        messages = [ModelRequest(parts=[UserPromptPart(content=f"msg-{i}")]) for i in range(15)]

        result = await compactor.compact(messages, {"keep_recent": 5})

        mock_summarizer.assert_called_once()
        call_arg = mock_summarizer.call_args[0][0]
        assert "msg-0" in call_arg
        assert "msg-9" in call_arg
        assert result.compacted_count == 6
