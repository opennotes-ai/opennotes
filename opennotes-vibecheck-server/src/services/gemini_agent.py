"""Shared pydantic-ai Agent factory for vibecheck analyses.

All LLM calls (except OpenAI moderation in src/analyses/safety) go through pydantic-ai
Agents bound to Vertex AI Gemini 3.1 Pro Preview. Mirrors opennotes-server's pattern:
- `google-vertex:` prefix on the model string
- `GoogleProvider(project=..., location=...)` using Application Default Credentials
- Caller passes `output_type=PydanticSchema` for structured outputs
"""
from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from src.config import Settings

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=4)
def _build_google_vertex_model(
    model_name: str, project: str, location: str
) -> GoogleModel:
    provider = GoogleProvider(project=project, location=location)
    return GoogleModel(model_name=model_name, provider=provider)


def _model_from_settings(settings: Settings) -> GoogleModel:
    prefix, _, name = settings.VERTEXAI_MODEL.partition(":")
    if prefix != "google-vertex" or not name:
        raise ValueError(
            f"VERTEXAI_MODEL must start with 'google-vertex:', got: {settings.VERTEXAI_MODEL!r}"
        )
    return _build_google_vertex_model(name, settings.VERTEXAI_PROJECT, settings.VERTEXAI_LOCATION)


def build_agent(
    settings: Settings,
    *,
    output_type: type[T] | None = None,
    system_prompt: str | None = None,
) -> Agent:
    """Construct a pydantic-ai Agent bound to Vertex Gemini.

    Usage:
        agent = build_agent(settings, output_type=MySchema, system_prompt="...")
        result = await agent.run("prompt text")
        parsed: MySchema = result.output
    """
    model = _model_from_settings(settings)
    kwargs: dict = {}
    if system_prompt is not None:
        kwargs["system_prompt"] = system_prompt
    if output_type is not None:
        kwargs["output_type"] = output_type
    return Agent(model, **kwargs)
