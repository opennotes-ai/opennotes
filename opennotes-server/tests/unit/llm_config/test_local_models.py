from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai.exceptions import UserError
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.native_tools import (
    CodeExecutionTool,
    FileSearchTool,
    ImageGenerationTool,
    WebFetchTool,
    WebSearchTool,
)
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.tools import ToolDefinition

from src.llm_config.local_models import OpenNotesGoogleModel


@pytest.fixture(autouse=True)
def _stub_google_adc(monkeypatch: pytest.MonkeyPatch) -> None:
    import google.auth

    fake_creds = MagicMock()
    monkeypatch.setattr(google.auth, "default", lambda *_, **__: (fake_creds, "test-project"))


@pytest.fixture
def google_model() -> GoogleModel:
    return GoogleModel(
        "gemini-3-flash",
        provider=GoogleProvider(project="test-project", location="global"),
    )


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


def test_opennotes_google_model_is_upstream_google_model() -> None:
    assert OpenNotesGoogleModel is GoogleModel


def test_google_model_combines_function_and_native_tools(
    google_model: GoogleModel, function_tool: ToolDefinition
) -> None:
    params = ModelRequestParameters(
        function_tools=[function_tool],
        native_tools=[WebSearchTool()],
    )

    tools, tool_config, image_config = google_model._get_tool_config(params, {})

    assert image_config is None
    assert tools is not None
    assert any("function_declarations" in tool for tool in tools)
    assert any("google_search" in tool for tool in tools)
    assert tool_config is not None
    assert tool_config["include_server_side_tool_invocations"] is True

    function_tool_names = [
        decl.get("name") for tool in tools for decl in tool.get("function_declarations") or []
    ]
    assert function_tool_names == ["lookup_note"]


def test_google_model_function_tools_only(
    google_model: GoogleModel, function_tool: ToolDefinition
) -> None:
    params = ModelRequestParameters(
        function_tools=[function_tool],
        native_tools=[],
    )

    tools, tool_config, image_config = google_model._get_tool_config(params, {})

    assert image_config is None
    assert tools is not None
    assert tool_config is not None
    assert "include_server_side_tool_invocations" not in tool_config
    function_tool_names = [
        decl.get("name") for tool in tools for decl in tool.get("function_declarations") or []
    ]
    assert function_tool_names == ["lookup_note"]


def test_google_model_native_tools_only(google_model: GoogleModel) -> None:
    params = ModelRequestParameters(
        function_tools=[],
        native_tools=[WebSearchTool()],
    )

    tools, tool_config, image_config = google_model._get_tool_config(params, {})

    assert image_config is None
    assert tools == [{"google_search": {}}]
    assert tool_config is not None
    assert tool_config["include_server_side_tool_invocations"] is True


@pytest.mark.parametrize(
    ("tool", "expected_key"),
    [
        (WebFetchTool(), "url_context"),
        (CodeExecutionTool(), "code_execution"),
        (FileSearchTool(file_store_ids=["store-1", "store-2"]), "file_search"),
    ],
)
def test_google_model_maps_native_tools(
    google_model: GoogleModel, tool: object, expected_key: str
) -> None:
    params = ModelRequestParameters(function_tools=[], native_tools=[tool])  # type: ignore[list-item]

    tools, image_config = google_model._get_native_tools(params)

    assert image_config is None
    assert tools is not None
    assert expected_key in tools[0]
    if expected_key == "file_search":
        assert tools[0]["file_search"]["file_search_store_names"] == ["store-1", "store-2"]


def test_google_model_raises_for_image_generation_tool_on_non_image_model(
    google_model: GoogleModel,
) -> None:
    params = ModelRequestParameters(function_tools=[], native_tools=[ImageGenerationTool()])

    with pytest.raises(UserError, match="ImageGenerationTool"):
        google_model._get_native_tools(params)


def test_google_model_raises_for_unknown_native_tool_kind(google_model: GoogleModel) -> None:
    class UnknownTool:
        pass

    params = ModelRequestParameters(function_tools=[], native_tools=[UnknownTool()])  # type: ignore[list-item]

    with pytest.raises(UserError, match="is not supported by `GoogleModel`"):
        google_model._get_native_tools(params)
