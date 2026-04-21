from __future__ import annotations

from google.genai.types import (
    FileSearchDict,
    GoogleSearchDict,
    ImageConfigDict,
    ToolCodeExecutionDict,
    ToolDict,
    UrlContextDict,
)
from pydantic_ai.builtin_tools import (
    CodeExecutionTool,
    FileSearchTool,
    ImageGenerationTool,
    WebFetchTool,
    WebSearchTool,
)
from pydantic_ai.exceptions import UserError
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.google import GoogleModel, _function_declaration_from_tool


class OpenNotesGoogleModel(GoogleModel):
    def _get_tools(
        self, model_request_parameters: ModelRequestParameters
    ) -> tuple[list[ToolDict] | None, ImageConfigDict | None]:
        # Override: upstream forbids combining function_tools with builtin_tools
        # (pydantic_ai/models/google.py:491-493). Gemini 3 supports the combo;
        # see TASK-1450 for context and SKU recommendation.
        tools: list[ToolDict] = [
            ToolDict(function_declarations=[_function_declaration_from_tool(t)])
            for t in model_request_parameters.tool_defs.values()
        ]

        image_config: ImageConfigDict | None = None

        if model_request_parameters.builtin_tools:
            for tool in model_request_parameters.builtin_tools:
                if isinstance(tool, WebSearchTool):
                    tools.append(ToolDict(google_search=GoogleSearchDict()))
                elif isinstance(tool, WebFetchTool):
                    tools.append(ToolDict(url_context=UrlContextDict()))
                elif isinstance(tool, CodeExecutionTool):
                    tools.append(ToolDict(code_execution=ToolCodeExecutionDict()))
                elif isinstance(tool, FileSearchTool):
                    file_search_config = FileSearchDict(
                        file_search_store_names=list(tool.file_store_ids)
                    )
                    tools.append(ToolDict(file_search=file_search_config))
                elif isinstance(tool, ImageGenerationTool):
                    if not self.profile.supports_image_output:
                        raise UserError(
                            "`ImageGenerationTool` is not supported by this model. Use a model with 'image' in the name instead."
                        )
                    image_config = self._build_image_config(tool)
                else:
                    raise UserError(
                        f"`{tool.__class__.__name__}` is not supported by `GoogleModel`. If it should be, please file an issue."
                    )
        return tools or None, image_config
