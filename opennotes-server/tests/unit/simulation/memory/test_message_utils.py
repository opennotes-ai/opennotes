from typing import Any

from src.simulation.memory.message_utils import _extract_text, _is_system_message


def _make_user_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": content}]}


def _make_system_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "system-prompt", "content": content}]}


def _make_response_message(content: str) -> dict[str, Any]:
    return {"kind": "response", "parts": [{"part_kind": "text", "content": content}]}


class TestExtractTextDict:
    def test_extracts_user_prompt(self):
        msg = _make_user_message("hello world")
        assert _extract_text(msg) == "hello world"

    def test_extracts_system_prompt(self):
        msg = _make_system_message("you are a helper")
        assert _extract_text(msg) == "you are a helper"

    def test_extracts_response_text(self):
        msg = _make_response_message("response content")
        assert _extract_text(msg) == "response content"

    def test_joins_multiple_parts(self):
        msg: dict[str, Any] = {
            "kind": "request",
            "parts": [
                {"part_kind": "user-prompt", "content": "part one"},
                {"part_kind": "user-prompt", "content": "part two"},
            ],
        }
        assert _extract_text(msg) == "part one part two"

    def test_skips_empty_content(self):
        msg: dict[str, Any] = {
            "kind": "request",
            "parts": [
                {"part_kind": "user-prompt", "content": ""},
                {"part_kind": "user-prompt", "content": "valid"},
            ],
        }
        assert _extract_text(msg) == "valid"

    def test_empty_parts(self):
        msg: dict[str, Any] = {"kind": "request", "parts": []}
        assert _extract_text(msg) == ""

    def test_no_parts_key(self):
        msg: dict[str, Any] = {"kind": "request"}
        assert _extract_text(msg) == ""

    def test_fallback_for_unknown_type(self):
        result = _extract_text("raw string")
        assert result == "raw string"


class TestExtractTextPydanticAi:
    def test_extracts_from_model_request(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        msg = ModelRequest(parts=[UserPromptPart(content="hello")])
        assert _extract_text(msg) == "hello"

    def test_extracts_from_model_response(self):
        from pydantic_ai.messages import ModelResponse, TextPart

        msg = ModelResponse(parts=[TextPart(content="response")])
        assert _extract_text(msg) == "response"

    def test_extracts_from_system_prompt_part(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart

        msg = ModelRequest(parts=[SystemPromptPart(content="system")])
        assert _extract_text(msg) == "system"

    def test_joins_multiple_pydantic_parts(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

        msg = ModelRequest(
            parts=[
                SystemPromptPart(content="system"),
                UserPromptPart(content="user"),
            ]
        )
        assert _extract_text(msg) == "system user"

    def test_skips_parts_without_string_content(self):
        from pydantic_ai.messages import ModelRequest, ToolCallPart, UserPromptPart

        msg = ModelRequest(
            parts=[
                UserPromptPart(content="hello"),
                ToolCallPart(tool_name="test", args="{}"),
            ]
        )
        assert _extract_text(msg) == "hello"


class TestIsSystemMessageDict:
    def test_system_message_detected(self):
        msg = _make_system_message("system")
        assert _is_system_message(msg) is True

    def test_user_message_not_system(self):
        msg = _make_user_message("user")
        assert _is_system_message(msg) is False

    def test_response_not_system(self):
        msg = _make_response_message("response")
        assert _is_system_message(msg) is False

    def test_empty_parts_not_system(self):
        msg: dict[str, Any] = {"kind": "request", "parts": []}
        assert _is_system_message(msg) is False

    def test_unknown_type_not_system(self):
        assert _is_system_message("raw string") is False


class TestIsSystemMessagePydanticAi:
    def test_system_prompt_detected(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart

        msg = ModelRequest(parts=[SystemPromptPart(content="system")])
        assert _is_system_message(msg) is True

    def test_user_prompt_not_system(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        msg = ModelRequest(parts=[UserPromptPart(content="user")])
        assert _is_system_message(msg) is False

    def test_response_not_system(self):
        from pydantic_ai.messages import ModelResponse, TextPart

        msg = ModelResponse(parts=[TextPart(content="response")])
        assert _is_system_message(msg) is False

    def test_mixed_parts_with_system(self):
        from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

        msg = ModelRequest(
            parts=[
                SystemPromptPart(content="system"),
                UserPromptPart(content="user"),
            ]
        )
        assert _is_system_message(msg) is True
