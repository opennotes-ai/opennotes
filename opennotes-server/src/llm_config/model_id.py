from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from src.llm_config.adapter import ModelFlavor, adapt_provider

if TYPE_CHECKING:
    from pydantic_ai.models import Model


class ModelId(BaseModel, frozen=True):
    provider: str
    model: str
    flavor: ModelFlavor

    @classmethod
    def from_slash_format(cls, s: str) -> ModelId:
        if "/" not in s:
            msg = f"Slash-format model string requires explicit provider prefix (provider/model), got: {s!r}"
            raise ValueError(msg)
        provider, _, model = s.partition("/")
        if not provider or not model:
            msg = f"Both provider and model must be non-empty, got: {s!r}"
            raise ValueError(msg)
        return cls(provider=provider, model=model, flavor=ModelFlavor.LEGACY_SLASH)

    @classmethod
    def from_pydantic_ai(cls, s: str) -> ModelId:
        if ":" not in s:
            msg = f"pydantic-ai model string requires explicit provider prefix (provider:model), got: {s!r}"
            raise ValueError(msg)
        provider, _, model = s.partition(":")
        if not provider or not model:
            msg = f"Both provider and model must be non-empty, got: {s!r}"
            raise ValueError(msg)
        return cls(provider=provider, model=model, flavor=ModelFlavor.PYDANTIC_AI)

    @property
    def canonical_provider(self) -> str:
        return adapt_provider(self.provider, self.flavor, ModelFlavor.LEGACY_SLASH)

    def to_slash_format(self) -> str:
        return f"{self.canonical_provider}/{self.model}"

    def to_pydantic_ai(self) -> str:
        provider = adapt_provider(self.provider, self.flavor, ModelFlavor.PYDANTIC_AI)
        return f"{provider}:{self.model}"

    def to_pydantic_ai_model(self) -> Model | str:
        from src.llm_config.model_factory import infer_model_with_overrides  # noqa: PLC0415

        return infer_model_with_overrides(self.to_pydantic_ai())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModelId):
            return NotImplemented
        return self.provider == other.provider and self.model == other.model

    def __hash__(self) -> int:
        return hash((self.provider, self.model))

    def __str__(self) -> str:
        return self.to_pydantic_ai()
