from __future__ import annotations

from enum import StrEnum


class ModelFlavor(StrEnum):
    LITELLM = "litellm"
    PYDANTIC_AI = "pydantic_ai"


LITELLM_TO_PYDANTIC_AI: dict[str, str] = {
    "vertex_ai": "google-vertex",
    "gemini": "google-gla",
}

PYDANTIC_AI_TO_LITELLM: dict[str, str] = {v: k for k, v in LITELLM_TO_PYDANTIC_AI.items()}


def adapt_provider(provider: str, from_flavor: ModelFlavor, to_flavor: ModelFlavor) -> str:
    if from_flavor == to_flavor:
        return provider
    if from_flavor == ModelFlavor.LITELLM and to_flavor == ModelFlavor.PYDANTIC_AI:
        return LITELLM_TO_PYDANTIC_AI.get(provider, provider)
    if from_flavor == ModelFlavor.PYDANTIC_AI and to_flavor == ModelFlavor.LITELLM:
        return PYDANTIC_AI_TO_LITELLM.get(provider, provider)
    return provider
