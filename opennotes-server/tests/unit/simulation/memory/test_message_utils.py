import logging
from typing import Any

from src.simulation.memory.message_utils import (
    extract_text,
    group_tool_pairs,
    is_system_message,
    is_tool_call_message,
    is_tool_return_message,
    validate_tool_pairs,
)


def _make_user_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": content}]}


def _make_system_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "system-prompt", "content": content}]}


def _make_response_message(content: str) -> dict[str, Any]:
    return {"kind": "response", "parts": [{"part_kind": "text", "content": content}]}


class TestExtractTextDict:
    def test_extracts_user_prompt(self):
        msg = _make_user_message("hello world")
        assert extract_text(msg) == "hello world"

    def test_extracts_system_prompt(self):
        msg = _make_system_message("you are a helper")
        assert extract_text(msg) == "you are a helper"

    def test_extracts_response_text(self):
        msg = _make_response_message("response content")
        assert extract_text(msg) == "response content"

    def test_joins_multiple_parts(self):
        msg: dict[str, Any] = {
            "kind": "request",
            "parts": [
                {"part_kind": "user-prompt", "content": "part one"},
                {"part_kind": "user-prompt", "content": "part two"},
            ],
        }
        assert extract_text(msg) == "part one part two"

    def test_skips_empty_content(self):
        msg: dict[str, Any] = {
            "kind": "request",
            "parts": [
                {"part_kind": "user-prompt", "content": ""},
                {"part_kind": "user-prompt", "content": "valid"},
            ],
        }
        assert extract_text(msg) == "valid"

    def test_empty_parts(self):
        msg: dict[str, Any] = {"kind": "request", "parts": []}
        assert extract_text(msg) == ""

    def test_no_parts_key(self):
        msg: dict[str, Any] = {"kind": "request"}
        assert extract_text(msg) == ""

    def test_fallback_for_unknown_type(self):
        result = extract_text("raw string")
        assert result == "raw string"


class TestExtractTextPydanticAi:
    def test_extracts_from_model_request(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        msg = ModelRequest(parts=[UserPromptPart(content="hello")])
        assert extract_text(msg) == "hello"

    def test_extracts_from_model_response(self):
        from pydantic_ai.messages import ModelResponse, TextPart

        msg = ModelResponse(parts=[TextPart(content="response")])
        assert extract_text(msg) == "response"

    def test_extracts_from_system_prompt_part(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart

        msg = ModelRequest(parts=[SystemPromptPart(content="system")])
        assert extract_text(msg) == "system"

    def test_joins_multiple_pydantic_parts(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

        msg = ModelRequest(
            parts=[
                SystemPromptPart(content="system"),
                UserPromptPart(content="user"),
            ]
        )
        assert extract_text(msg) == "system user"

    def test_skips_parts_without_string_content(self):
        from pydantic_ai.messages import ModelRequest, ToolCallPart, UserPromptPart

        msg = ModelRequest(
            parts=[
                UserPromptPart(content="hello"),
                ToolCallPart(tool_name="test", args="{}"),
            ]
        )
        assert extract_text(msg) == "hello"


class TestIsSystemMessageDict:
    def test_system_message_detected(self):
        msg = _make_system_message("system")
        assert is_system_message(msg) is True

    def test_user_message_not_system(self):
        msg = _make_user_message("user")
        assert is_system_message(msg) is False

    def test_response_not_system(self):
        msg = _make_response_message("response")
        assert is_system_message(msg) is False

    def test_empty_parts_not_system(self):
        msg: dict[str, Any] = {"kind": "request", "parts": []}
        assert is_system_message(msg) is False

    def test_unknown_type_not_system(self):
        assert is_system_message("raw string") is False


class TestIsSystemMessagePydanticAi:
    def test_system_prompt_detected(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart

        msg = ModelRequest(parts=[SystemPromptPart(content="system")])
        assert is_system_message(msg) is True

    def test_user_prompt_not_system(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        msg = ModelRequest(parts=[UserPromptPart(content="user")])
        assert is_system_message(msg) is False

    def test_response_not_system(self):
        from pydantic_ai.messages import ModelResponse, TextPart

        msg = ModelResponse(parts=[TextPart(content="response")])
        assert is_system_message(msg) is False

    def test_mixed_parts_with_system(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

        msg = ModelRequest(
            parts=[
                SystemPromptPart(content="system"),
                UserPromptPart(content="user"),
            ]
        )
        assert is_system_message(msg) is True


def _make_tool_call_response(tool_name: str = "test_tool", args: str = "{}") -> dict[str, Any]:
    return {
        "kind": "response",
        "parts": [
            {
                "part_kind": "tool-call",
                "tool_name": tool_name,
                "args": args,
                "tool_call_id": "call-1",
            }
        ],
    }


def _make_tool_return_request(
    tool_name: str = "test_tool", content: str = "result"
) -> dict[str, Any]:
    return {
        "kind": "request",
        "parts": [
            {
                "part_kind": "tool-return",
                "tool_name": tool_name,
                "content": content,
                "tool_call_id": "call-1",
            }
        ],
    }


class TestIsToolCallMessageDict:
    def test_detects_tool_call(self):
        msg = _make_tool_call_response()
        assert is_tool_call_message(msg) is True

    def test_user_message_not_tool_call(self):
        msg = _make_user_message("hello")
        assert is_tool_call_message(msg) is False

    def test_system_message_not_tool_call(self):
        msg = _make_system_message("system")
        assert is_tool_call_message(msg) is False

    def test_response_text_not_tool_call(self):
        msg = _make_response_message("text response")
        assert is_tool_call_message(msg) is False

    def test_tool_return_not_tool_call(self):
        msg = _make_tool_return_request()
        assert is_tool_call_message(msg) is False

    def test_empty_parts_not_tool_call(self):
        msg: dict[str, Any] = {"kind": "response", "parts": []}
        assert is_tool_call_message(msg) is False

    def test_mixed_parts_with_tool_call(self):
        msg: dict[str, Any] = {
            "kind": "response",
            "parts": [
                {"part_kind": "text", "content": "thinking..."},
                {
                    "part_kind": "tool-call",
                    "tool_name": "search",
                    "args": "{}",
                    "tool_call_id": "call-2",
                },
            ],
        }
        assert is_tool_call_message(msg) is True


class TestIsToolCallMessagePydanticAi:
    def test_detects_tool_call_part(self):
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        msg = ModelResponse(parts=[ToolCallPart(tool_name="test_tool", args="{}")])
        assert is_tool_call_message(msg) is True

    def test_text_response_not_tool_call(self):
        from pydantic_ai.messages import ModelResponse, TextPart

        msg = ModelResponse(parts=[TextPart(content="hello")])
        assert is_tool_call_message(msg) is False

    def test_model_request_not_tool_call(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        msg = ModelRequest(parts=[UserPromptPart(content="hello")])
        assert is_tool_call_message(msg) is False

    def test_mixed_parts_with_tool_call(self):
        from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

        msg = ModelResponse(
            parts=[
                TextPart(content="let me search"),
                ToolCallPart(tool_name="search", args="{}"),
            ]
        )
        assert is_tool_call_message(msg) is True


class TestIsToolReturnMessageDict:
    def test_detects_tool_return(self):
        msg = _make_tool_return_request()
        assert is_tool_return_message(msg) is True

    def test_user_message_not_tool_return(self):
        msg = _make_user_message("hello")
        assert is_tool_return_message(msg) is False

    def test_system_message_not_tool_return(self):
        msg = _make_system_message("system")
        assert is_tool_return_message(msg) is False

    def test_tool_call_not_tool_return(self):
        msg = _make_tool_call_response()
        assert is_tool_return_message(msg) is False

    def test_empty_parts_not_tool_return(self):
        msg: dict[str, Any] = {"kind": "request", "parts": []}
        assert is_tool_return_message(msg) is False

    def test_mixed_parts_with_tool_return(self):
        msg: dict[str, Any] = {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "search",
                    "content": "found it",
                    "tool_call_id": "call-1",
                },
                {"part_kind": "user-prompt", "content": "thanks"},
            ],
        }
        assert is_tool_return_message(msg) is True


class TestIsToolReturnMessagePydanticAi:
    def test_detects_tool_return_part(self):
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        msg = ModelRequest(parts=[ToolReturnPart(tool_name="test_tool", content="result")])
        assert is_tool_return_message(msg) is True

    def test_user_prompt_not_tool_return(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        msg = ModelRequest(parts=[UserPromptPart(content="hello")])
        assert is_tool_return_message(msg) is False

    def test_response_not_tool_return(self):
        from pydantic_ai.messages import ModelResponse, TextPart

        msg = ModelResponse(parts=[TextPart(content="response")])
        assert is_tool_return_message(msg) is False

    def test_mixed_parts_with_tool_return(self):
        from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

        msg = ModelRequest(
            parts=[
                ToolReturnPart(tool_name="search", content="result"),
                UserPromptPart(content="thanks"),
            ]
        )
        assert is_tool_return_message(msg) is True


class TestGroupToolPairs:
    def test_empty_list(self):
        assert group_tool_pairs([]) == []

    def test_no_tool_calls(self):
        msgs = [_make_user_message("hi"), _make_response_message("hello")]
        result = group_tool_pairs(msgs)
        assert result == [[msgs[0]], [msgs[1]]]

    def test_single_tool_pair(self):
        user = _make_user_message("search for X")
        tool_call = _make_tool_call_response()
        tool_return = _make_tool_return_request()
        reply = _make_response_message("found it")

        result = group_tool_pairs([user, tool_call, tool_return, reply])
        assert result == [[user], [tool_call, tool_return], [reply]]

    def test_multiple_tool_returns_after_one_call(self):
        tool_call = _make_tool_call_response()
        ret1 = _make_tool_return_request("tool_a", "result_a")
        ret2 = _make_tool_return_request("tool_b", "result_b")

        result = group_tool_pairs([tool_call, ret1, ret2])
        assert result == [[tool_call, ret1, ret2]]

    def test_multiple_tool_pairs(self):
        user = _make_user_message("do stuff")
        call1 = _make_tool_call_response("tool_a")
        ret1 = _make_tool_return_request("tool_a", "result_a")
        call2 = _make_tool_call_response("tool_b")
        ret2 = _make_tool_return_request("tool_b", "result_b")
        reply = _make_response_message("done")

        result = group_tool_pairs([user, call1, ret1, call2, ret2, reply])
        assert result == [[user], [call1, ret1], [call2, ret2], [reply]]

    def test_tool_call_at_end_without_return(self):
        user = _make_user_message("hi")
        call = _make_tool_call_response()

        result = group_tool_pairs([user, call])
        assert result == [[user], [call]]

    def test_pydantic_ai_types(self):
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            TextPart,
            ToolCallPart,
            ToolReturnPart,
            UserPromptPart,
        )

        user = ModelRequest(parts=[UserPromptPart(content="search")])
        call = ModelResponse(parts=[ToolCallPart(tool_name="search", args="{}")])
        ret = ModelRequest(parts=[ToolReturnPart(tool_name="search", content="found")])
        reply = ModelResponse(parts=[TextPart(content="here it is")])

        result = group_tool_pairs([user, call, ret, reply])
        assert result == [[user], [call, ret], [reply]]


class TestValidateToolPairs:
    def test_valid_sequence(self):
        msgs = [
            _make_user_message("hi"),
            _make_tool_call_response(),
            _make_tool_return_request(),
            _make_response_message("done"),
        ]
        assert validate_tool_pairs(msgs) is True

    def test_empty_list_valid(self):
        assert validate_tool_pairs([]) is True

    def test_no_tool_messages_valid(self):
        msgs = [_make_user_message("hi"), _make_response_message("hello")]
        assert validate_tool_pairs(msgs) is True

    def test_orphaned_tool_return(self, caplog: Any):
        msgs = [
            _make_user_message("hi"),
            _make_tool_return_request(),
        ]
        with caplog.at_level(logging.WARNING):
            result = validate_tool_pairs(msgs)
        assert result is False
        assert "orphaned" in caplog.text.lower() or "tool" in caplog.text.lower()

    def test_tool_call_without_return_valid(self):
        msgs = [_make_tool_call_response()]
        assert validate_tool_pairs(msgs) is True

    def test_multiple_valid_pairs(self):
        msgs = [
            _make_tool_call_response("a"),
            _make_tool_return_request("a"),
            _make_tool_call_response("b"),
            _make_tool_return_request("b"),
        ]
        assert validate_tool_pairs(msgs) is True

    def test_pydantic_ai_orphaned_tool_return(self, caplog: Any):
        from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

        msgs = [
            ModelRequest(parts=[UserPromptPart(content="hi")]),
            ModelRequest(parts=[ToolReturnPart(tool_name="test", content="result")]),
        ]
        with caplog.at_level(logging.WARNING):
            result = validate_tool_pairs(msgs)
        assert result is False

    def test_pydantic_ai_valid_pair(self):
        from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

        msgs = [
            ModelResponse(parts=[ToolCallPart(tool_name="test", args="{}")]),
            ModelRequest(parts=[ToolReturnPart(tool_name="test", content="result")]),
        ]
        assert validate_tool_pairs(msgs) is True
