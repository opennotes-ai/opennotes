from __future__ import annotations

import dataclasses
from functools import lru_cache

from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from src.config import settings


@lru_cache(maxsize=32)
def _build_google_vertex_model(model_name: str, project: str, location: str) -> GoogleModel:
    provider = GoogleProvider(project=project, location=location)
    return GoogleModel(model_name=model_name, provider=provider)


def build_url_scan_vertex_model(model_str: str) -> Model:
    if not model_str.startswith("google-vertex:"):
        raise ValueError(
            f"build_url_scan_vertex_model requires a google-vertex: model string, got: {model_str!r}"
        )
    _, model_name = model_str.split(":", 1)
    if not settings.VERTEXAI_PROJECT:
        raise ValueError(
            "VERTEXAI_PROJECT is not configured. "
            "Set VERTEXAI_PROJECT or GOOGLE_CLOUD_PROJECT before using google-vertex models."
        )
    provider = GoogleProvider(
        project=settings.VERTEXAI_PROJECT, location=settings.VERTEXAI_LOCATION
    )
    base_model = GoogleModel(model_name=model_name, provider=provider)
    patched_profile = dataclasses.replace(
        base_model.profile,
        google_supports_server_side_tool_invocations=False,
    )
    return GoogleModel(model_name=model_name, provider=provider, profile=patched_profile)


def infer_model_with_overrides(model_str: str) -> Model | str:
    if model_str.startswith("google-gla:"):
        raise ValueError(
            "google-gla provider was removed in TASK-1450. "
            "Use google-vertex: prefix instead. "
            "Existing sim_agents.model_name rows are migrated by TASK-1450.09."
        )
    if model_str.startswith("google-vertex:"):
        _, model_name = model_str.split(":", 1)
        if not settings.VERTEXAI_PROJECT:
            raise ValueError(
                "VERTEXAI_PROJECT is not configured. "
                "Set VERTEXAI_PROJECT or GOOGLE_CLOUD_PROJECT before using google-vertex models."
            )
        return _build_google_vertex_model(
            model_name, settings.VERTEXAI_PROJECT, settings.VERTEXAI_LOCATION
        )
    return model_str
