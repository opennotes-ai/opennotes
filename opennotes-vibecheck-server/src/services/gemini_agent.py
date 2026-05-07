"""Shared pydantic-ai Agent factory for vibecheck analyses.

All LLM calls (except OpenAI moderation in src/analyses/safety) go through pydantic-ai
Agents bound to Vertex AI Gemini. Mirrors opennotes-server's pattern:
- `google-vertex:` prefix on the model string
- `GoogleProvider(project=..., location=...)` using Application Default Credentials
- Caller passes `output_type=PydanticSchema` for structured outputs
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any, Final, Literal, TypedDict, TypeVar, cast, overload

import logfire
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider

from src.config import Settings

T = TypeVar("T", bound=BaseModel)
GeminiTier = Literal["fast", "synthesis"]

MAX_VERTEX_429_ATTEMPTS: Final[int] = 3
OUTPUT_VALIDATION_RETRIES: Final[int] = 3


@lru_cache(maxsize=4)
def _build_google_vertex_model(model_name: str, project: str, location: str) -> GoogleModel:
    provider = GoogleProvider(project=project, location=location)
    return GoogleModel(model_name=model_name, provider=provider)


def google_vertex_model_name(setting_value: str, *, setting_name: str) -> str:
    prefix, _, name = setting_value.partition(":")
    if prefix != "google-vertex" or not name:
        raise ValueError(f"{setting_name} must start with 'google-vertex:', got: {setting_value!r}")
    return name


def _model_from_settings(settings: Settings, tier: GeminiTier) -> GoogleModel:
    if tier == "fast":
        setting_name = "VERTEXAI_FAST_MODEL"
        setting_value = settings.VERTEXAI_FAST_MODEL
    elif tier == "synthesis":
        setting_name = "VERTEXAI_MODEL"
        setting_value = settings.VERTEXAI_MODEL
    else:
        raise ValueError(f"unknown Gemini tier: {tier!r}")

    name = google_vertex_model_name(setting_value, setting_name=setting_name)
    return _build_google_vertex_model(
        name,
        settings.VERTEXAI_PROJECT,
        settings.VERTEXAI_LOCATION,
    )


@overload
def build_agent(
    settings: Settings,
    *,
    output_type: type[T],
    system_prompt: str | None = None,
    name: str | None = None,
    tier: GeminiTier = "fast",
    builtin_tools: Sequence[Any] = (),
    logprobs: bool = False,
    top_logprobs: int | None = None,
) -> Agent[None, T]: ...


@overload
def build_agent(
    settings: Settings,
    *,
    output_type: None = None,
    system_prompt: str | None = None,
    name: str | None = None,
    tier: GeminiTier = "fast",
    builtin_tools: Sequence[Any] = (),
    logprobs: bool = False,
    top_logprobs: int | None = None,
) -> Agent[None, str]: ...


def build_agent(
    settings: Settings,
    *,
    output_type: type[T] | None = None,
    system_prompt: str | None = None,
    name: str | None = None,
    tier: GeminiTier = "fast",
    builtin_tools: Sequence[Any] = (),
    logprobs: bool = False,
    top_logprobs: int | None = None,
) -> Agent[None, T] | Agent[None, str]:
    """Construct a pydantic-ai Agent bound to Vertex Gemini.

    Usage:
        agent = build_agent(settings, output_type=MySchema, system_prompt="...", name="vibecheck.foo")
        result = await agent.run("prompt text")
        parsed: MySchema = result.output

    `name` is forwarded to pydantic-ai and surfaces as a span attribute in
    Logfire traces, so each call site appears as a distinct Agent in
    observability tooling instead of an anonymous "agent run" span.
    """
    model = _model_from_settings(settings, tier)
    kwargs: dict[str, Any] = {"output_retries": OUTPUT_VALIDATION_RETRIES}
    if system_prompt is not None:
        kwargs["system_prompt"] = system_prompt
    if output_type is not None:
        kwargs["output_type"] = output_type
    if builtin_tools:
        kwargs["builtin_tools"] = builtin_tools
    if name is not None:
        kwargs["name"] = name
    if logprobs:
        model_settings: GoogleModelSettings = {"google_logprobs": True}
        if top_logprobs is not None:
            model_settings["google_top_logprobs"] = top_logprobs
        kwargs["model_settings"] = model_settings
    return Agent(model, **kwargs)


class GoogleLogprobs(TypedDict, total=False):
    """Best-effort view of Google model response metadata."""

    logprobs: Mapping[str, Any]
    avg_logprobs: float | None


def extract_google_logprobs(
    result: Any,
) -> GoogleLogprobs | None:
    """Extract best-effort logprob data from a pydantic-ai AgentRunResult.

    Returns ``None`` when provider details are absent or malformed.
    """
    response = getattr(result, "response", None)
    provider_details = getattr(response, "provider_details", None) if response is not None else None

    if not isinstance(provider_details, Mapping):
        return None

    raw_logprobs = provider_details.get("logprobs")
    if not isinstance(raw_logprobs, Mapping):
        return None

    payload: GoogleLogprobs = {"logprobs": raw_logprobs}
    avg_logprobs = provider_details.get("avg_logprobs")
    if avg_logprobs is not None:
        avg_logprobs = cast(float, avg_logprobs)
        payload["avg_logprobs"] = avg_logprobs
    return payload


async def run_vertex_agent_with_retry(
    agent: Agent[Any, T],
    /,
    *args: Any,
    **kwargs: Any,
) -> AgentRunResult[T]:
    attempts_used = 0
    while True:
        try:
            return await agent.run(*args, **kwargs)
        except ModelHTTPError as exc:
            if exc.status_code != 429:
                raise
            attempts_used += 1
            if attempts_used >= MAX_VERTEX_429_ATTEMPTS:
                logfire.warning(
                    "vertex_429_exhausted",
                    model_name=exc.model_name,
                    status_code=exc.status_code,
                    attempts=MAX_VERTEX_429_ATTEMPTS,
                )
                raise
            delay = (1.0 * 2 ** (attempts_used - 1)) * random.uniform(0.5, 1.5)
            logfire.info(
                "vertex_429_retry",
                model_name=exc.model_name,
                status_code=exc.status_code,
                attempt_number=attempts_used,
                backoff_delay_s=delay,
            )
            await asyncio.sleep(delay)
