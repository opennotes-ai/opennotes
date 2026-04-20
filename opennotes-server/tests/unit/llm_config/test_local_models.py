from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from pydantic_ai.builtin_tools import WebSearchTool
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition

if TYPE_CHECKING:
    from src.llm_config.local_models import OpenNotesGoogleModel


@pytest.fixture
def function_tool() -> ToolDefinition:
    return ToolDefinition(
        name="lookup_note",
        parameters_json_schema={
            "type": "object",
            "properties": {"note_id": {"type": "string"}},
            "required": ["note_id"],
        },
        description="Look up a Community Notes entry by id.",
    )


def _call_get_tools(params: ModelRequestParameters):
    from src.llm_config.local_models import OpenNotesGoogleModel

    fake_self = cast("OpenNotesGoogleModel", object())
    return OpenNotesGoogleModel._get_tools(fake_self, params)


def test_get_tools_combines_function_and_builtin_tools(function_tool: ToolDefinition) -> None:
    params = ModelRequestParameters(
        function_tools=[function_tool],
        builtin_tools=[WebSearchTool()],
    )

    tools, image_config = _call_get_tools(params)

    assert image_config is None
    assert tools is not None
    assert any("function_declarations" in tool for tool in tools)
    assert any("google_search" in tool for tool in tools)

    function_tool_names = [
        decl.get("name") for tool in tools for decl in tool.get("function_declarations") or []
    ]
    assert "lookup_note" in function_tool_names


def test_get_tools_function_tools_only(function_tool: ToolDefinition) -> None:
    params = ModelRequestParameters(
        function_tools=[function_tool],
        builtin_tools=[],
    )

    tools, image_config = _call_get_tools(params)

    assert image_config is None
    assert tools is not None
    assert all("google_search" not in tool for tool in tools)
    function_tool_names = [
        decl.get("name") for tool in tools for decl in tool.get("function_declarations") or []
    ]
    assert function_tool_names == ["lookup_note"]


def test_get_tools_builtin_tools_only() -> None:
    params = ModelRequestParameters(
        function_tools=[],
        builtin_tools=[WebSearchTool()],
    )

    tools, image_config = _call_get_tools(params)

    assert image_config is None
    assert tools is not None
    assert any("google_search" in tool for tool in tools)
    assert all(not tool.get("function_declarations") for tool in tools)
