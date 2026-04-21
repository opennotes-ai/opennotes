from __future__ import annotations

from functools import lru_cache

from pydantic_ai.models import Model
from pydantic_ai.providers.google import GoogleProvider

from src.config import settings
from src.llm_config.local_models import OpenNotesGoogleModel


@lru_cache(maxsize=32)
def _build_google_vertex_model(
    model_name: str, project: str, location: str
) -> OpenNotesGoogleModel:
    provider = GoogleProvider(project=project, location=location)
    return OpenNotesGoogleModel(model_name=model_name, provider=provider)


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
