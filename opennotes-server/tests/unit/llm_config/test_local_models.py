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


def _tool_kinds(tools: list[dict[str, object]] | None) -> set[str]:
    if not tools:
        return set()
    return {key for tool in tools for key in tool if key != "function_declarations"}


def _function_declaration_names(tools: list[dict[str, object]] | None) -> list[str]:
    if not tools:
        return []

    names: list[str] = []
    for tool in tools:
        for declaration in tool.get("function_declarations") or []:
            name = declaration.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def test_opennotes_google_model_is_upstream_google_model() -> None:
    assert OpenNotesGoogleModel is GoogleModel


def test_google_model_tool_config_sentinel_allows_function_and_native_tools_together(
    google_model: GoogleModel, function_tool: ToolDefinition
) -> None:
    params = ModelRequestParameters(
        function_tools=[function_tool],
        native_tools=[WebSearchTool()],
    )

    # Compatibility sentinel for pydantic-ai 1.96: there is no public offline API
    # that exposes GoogleModel's tool serialization, so we probe the narrow private
    # helper and assert only the OpenNotes-supported behavior.
    tools, tool_config, image_config = google_model._get_tool_config(params, {})

    assert image_config is None
    assert tools is not None
    assert _function_declaration_names(tools) == ["lookup_note"]
    assert _tool_kinds(tools) == {"google_search"}
    assert tool_config is not None
    assert tool_config["include_server_side_tool_invocations"] is True


def test_google_model_tool_config_sentinel_keeps_function_only_requests_stable(
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
    assert _function_declaration_names(tools) == ["lookup_note"]
    assert _tool_kinds(tools) == set()


def test_google_model_tool_config_sentinel_keeps_native_only_requests_stable(
    google_model: GoogleModel,
) -> None:
    params = ModelRequestParameters(
        function_tools=[],
        native_tools=[WebSearchTool()],
    )

    tools, tool_config, image_config = google_model._get_tool_config(params, {})

    assert image_config is None
    assert tools is not None
    assert _function_declaration_names(tools) == []
    assert _tool_kinds(tools) == {"google_search"}
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
