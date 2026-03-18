from typing import Any

import pytest

from src.simulation.memory.sliding_window import SlidingWindowCompactor


def _make_user_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": content}]}


def _make_system_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "system-prompt", "content": content}]}


def _make_response_message(content: str) -> dict[str, Any]:
    return {"kind": "response", "parts": [{"part_kind": "text", "content": content}]}


class TestSlidingWindowKeepsLastN:
    @pytest.mark.asyncio
    async def test_keeps_last_n_messages(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_user_message(f"msg-{i}") for i in range(20)]

        result = await compactor.compact(messages, {"window_size": 10})

        assert result.compacted_count == 10
        assert result.original_count == 20
        assert len(result.messages) == 10
        assert result.messages == messages[-10:]

    @pytest.mark.asyncio
    async def test_preserves_system_message(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_system_message("You are a helper")]
        messages.extend(_make_user_message(f"msg-{i}") for i in range(19))

        result = await compactor.compact(messages, {"window_size": 10})

        assert len(result.messages) == 10
        assert result.messages[0]["parts"][0]["part_kind"] == "system-prompt"
        assert result.messages[0]["parts"][0]["content"] == "You are a helper"

    @pytest.mark.asyncio
    async def test_no_op_when_under_window(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_user_message(f"msg-{i}") for i in range(5)]

        result = await compactor.compact(messages, {"window_size": 10})

        assert result.compacted_count == 5
        assert result.original_count == 5
        assert len(result.messages) == 5

    @pytest.mark.asyncio
    async def test_default_window_size(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_user_message(f"msg-{i}") for i in range(30)]

        result = await compactor.compact(messages, {})

        assert result.compacted_count == 20
        assert result.metadata["window_size"] == 20

    @pytest.mark.asyncio
    async def test_returns_compaction_result_metadata(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_user_message(f"msg-{i}") for i in range(20)]

        result = await compactor.compact(messages, {"window_size": 10})

        assert result.strategy == "sliding_window"
        assert result.original_count == 20
        assert result.compacted_count == 10
        assert result.metadata["window_size"] == 10

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        compactor = SlidingWindowCompactor()

        result = await compactor.compact([], {"window_size": 10})

        assert result.compacted_count == 0
        assert result.original_count == 0
        assert result.messages == []

    @pytest.mark.asyncio
    async def test_system_message_preserved_with_exact_window(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_system_message("system")]
        messages.extend(_make_user_message(f"msg-{i}") for i in range(14))

        result = await compactor.compact(messages, {"window_size": 10})

        assert len(result.messages) == 10
        assert result.messages[0]["parts"][0]["part_kind"] == "system-prompt"
        for msg in result.messages[1:]:
            assert msg["parts"][0]["part_kind"] != "system-prompt"

    @pytest.mark.asyncio
    async def test_window_size_1_with_system_message(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_system_message("system")]
        messages.extend(_make_user_message(f"msg-{i}") for i in range(10))

        result = await compactor.compact(messages, {"window_size": 1})

        assert len(result.messages) == 1
        assert result.messages[0]["parts"][0]["part_kind"] == "system-prompt"
        assert result.compacted_count == 1

    @pytest.mark.asyncio
    async def test_window_size_1_without_system_message(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_user_message(f"msg-{i}") for i in range(10)]

        result = await compactor.compact(messages, {"window_size": 1})

        assert len(result.messages) == 1
        assert result.messages[0]["parts"][0]["content"] == "msg-9"
        assert result.compacted_count == 1

    @pytest.mark.asyncio
    async def test_window_size_2_with_system_message(self):
        compactor = SlidingWindowCompactor()
        messages = [_make_system_message("system")]
        messages.extend(_make_user_message(f"msg-{i}") for i in range(10))

        result = await compactor.compact(messages, {"window_size": 2})

        assert len(result.messages) == 2
        assert result.messages[0]["parts"][0]["part_kind"] == "system-prompt"
        assert result.messages[1]["parts"][0]["content"] == "msg-9"


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


class TestSlidingWindowToolPairs:
    @pytest.mark.asyncio
    async def test_tool_pair_at_boundary_preserved(self):
        compactor = SlidingWindowCompactor()
        messages: list[dict[str, Any]] = []
        for i in range(8):
            messages.append(_make_user_message(f"msg-{i}"))
        messages.append(_make_tool_call_response())
        messages.append(_make_tool_return_request())
        for i in range(10, 15):
            messages.append(_make_user_message(f"msg-{i}"))
        assert len(messages) == 15

        result = await compactor.compact(messages, {"window_size": 6})

        assert result.messages[0]["parts"][0]["part_kind"] == "tool-call"
        assert result.messages[1]["parts"][0]["part_kind"] == "tool-return"
        assert len(result.messages) == 7

    @pytest.mark.asyncio
    async def test_tool_pair_outside_window_dropped_as_unit(self):
        compactor = SlidingWindowCompactor()
        messages: list[dict[str, Any]] = []
        messages.append(_make_user_message("msg-0"))
        messages.append(_make_user_message("msg-1"))
        messages.append(_make_tool_call_response())
        messages.append(_make_tool_return_request())
        for i in range(4, 20):
            messages.append(_make_user_message(f"msg-{i}"))
        assert len(messages) == 20

        result = await compactor.compact(messages, {"window_size": 5})

        assert len(result.messages) == 5
        for msg in result.messages:
            for part in msg["parts"]:
                assert part["part_kind"] not in ("tool-call", "tool-return")

    @pytest.mark.asyncio
    async def test_multiple_tool_returns_kept_with_call(self):
        compactor = SlidingWindowCompactor()
        messages: list[dict[str, Any]] = []
        for i in range(6):
            messages.append(_make_user_message(f"msg-{i}"))
        messages.append(_make_tool_call_response())
        messages.append(_make_tool_return_request(tool_name="tool_a", tool_call_id="call-a"))
        messages.append(_make_tool_return_request(tool_name="tool_b", tool_call_id="call-b"))
        messages.append(_make_tool_return_request(tool_name="tool_c", tool_call_id="call-c"))
        for i in range(10, 13):
            messages.append(_make_user_message(f"msg-{i}"))
        assert len(messages) == 13

        result = await compactor.compact(messages, {"window_size": 5})

        tool_parts = [
            part["part_kind"]
            for msg in result.messages
            for part in msg["parts"]
            if part["part_kind"] in ("tool-call", "tool-return")
        ]
        assert "tool-call" in tool_parts
        assert tool_parts.count("tool-return") == 3
        assert len(result.messages) == 7

    @pytest.mark.asyncio
    async def test_tool_pair_with_system_message(self):
        compactor = SlidingWindowCompactor()
        messages: list[dict[str, Any]] = [_make_system_message("system")]
        for i in range(7):
            messages.append(_make_user_message(f"msg-{i}"))
        messages.append(_make_tool_call_response())
        messages.append(_make_tool_return_request())
        for i in range(9, 14):
            messages.append(_make_user_message(f"msg-{i}"))
        assert len(messages) == 15

        result = await compactor.compact(messages, {"window_size": 7})

        assert result.messages[0]["parts"][0]["part_kind"] == "system-prompt"
        tool_parts = [
            part["part_kind"]
            for msg in result.messages
            for part in msg["parts"]
            if part["part_kind"] in ("tool-call", "tool-return")
        ]
        assert "tool-call" in tool_parts
        assert "tool-return" in tool_parts


class TestSlidingWindowPydanticAiTypes:
    @pytest.mark.asyncio
    async def test_handles_pydantic_ai_model_request(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

        compactor = SlidingWindowCompactor()
        messages = [ModelRequest(parts=[SystemPromptPart(content="system")])]
        messages.extend(ModelRequest(parts=[UserPromptPart(content=f"msg-{i}")]) for i in range(10))

        result = await compactor.compact(messages, {"window_size": 5})

        assert len(result.messages) == 5
        assert isinstance(result.messages[0], ModelRequest)
        assert isinstance(result.messages[0].parts[0], SystemPromptPart)

    @pytest.mark.asyncio
    async def test_window_size_1_with_pydantic_ai_system(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

        compactor = SlidingWindowCompactor()
        messages = [ModelRequest(parts=[SystemPromptPart(content="system")])]
        messages.extend(ModelRequest(parts=[UserPromptPart(content=f"msg-{i}")]) for i in range(5))

        result = await compactor.compact(messages, {"window_size": 1})

        assert len(result.messages) == 1
        assert isinstance(result.messages[0].parts[0], SystemPromptPart)
