from __future__ import annotations

from enum import StrEnum


class ModelFlavor(StrEnum):
    PYDANTIC_AI = "pydantic_ai"
    LEGACY_SLASH = "legacy_slash"


LEGACY_SLASH_TO_PYDANTIC_AI: dict[str, str] = {
    "vertex_ai": "google-vertex",
}

PYDANTIC_AI_TO_LEGACY_SLASH: dict[str, str] = {v: k for k, v in LEGACY_SLASH_TO_PYDANTIC_AI.items()}


def adapt_provider(provider: str, from_flavor: ModelFlavor, to_flavor: ModelFlavor) -> str:
    if from_flavor == to_flavor:
        return provider
    if from_flavor == ModelFlavor.LEGACY_SLASH and to_flavor == ModelFlavor.PYDANTIC_AI:
        return LEGACY_SLASH_TO_PYDANTIC_AI.get(provider, provider)
    if from_flavor == ModelFlavor.PYDANTIC_AI and to_flavor == ModelFlavor.LEGACY_SLASH:
        return PYDANTIC_AI_TO_LEGACY_SLASH.get(provider, provider)
    return provider
