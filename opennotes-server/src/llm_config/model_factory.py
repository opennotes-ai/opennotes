from __future__ import annotations

from pydantic_ai.models import Model, infer_model
from pydantic_ai.providers.google import GoogleProvider

from src.config import settings
from src.llm_config.local_models import OpenNotesGoogleModel


def infer_model_with_overrides(model_str: str) -> Model:
    if model_str.startswith("google-gla:"):
        raise ValueError(
            "google-gla provider was removed in TASK-1450. "
            "Use google-vertex: prefix instead. "
            "Existing sim_agents.model_name rows are migrated by TASK-1450.09."
        )
    if model_str.startswith("google-vertex:"):
        _, model_name = model_str.split(":", 1)
        provider = GoogleProvider(
            project=settings.VERTEXAI_PROJECT,
            location=settings.VERTEXAI_LOCATION,
        )
        return OpenNotesGoogleModel(model_name=model_name, provider=provider)
    return infer_model(model_str)
