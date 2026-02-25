from __future__ import annotations

from pydantic import BaseModel

from src.llm_config.adapter import ModelFlavor, adapt_provider


class ModelId(BaseModel, frozen=True):
    provider: str
    model: str
    flavor: ModelFlavor

    @classmethod
    def from_litellm(cls, s: str) -> ModelId:
        if "/" not in s:
            msg = f"LiteLLM model string requires explicit provider prefix (provider/model), got: {s!r}"
            raise ValueError(msg)
        provider, _, model = s.partition("/")
        if not provider or not model:
            msg = f"Both provider and model must be non-empty, got: {s!r}"
            raise ValueError(msg)
        return cls(provider=provider, model=model, flavor=ModelFlavor.LITELLM)

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
    def litellm_provider(self) -> str:
        return adapt_provider(self.provider, self.flavor, ModelFlavor.LITELLM)

    def to_litellm(self) -> str:
        return f"{self.litellm_provider}/{self.model}"

    def to_pydantic_ai(self) -> str:
        provider = adapt_provider(self.provider, self.flavor, ModelFlavor.PYDANTIC_AI)
        return f"{provider}:{self.model}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModelId):
            return NotImplemented
        return self.provider == other.provider and self.model == other.model

    def __hash__(self) -> int:
        return hash((self.provider, self.model))

    def __str__(self) -> str:
        if self.flavor == ModelFlavor.LITELLM:
            return self.to_litellm()
        return self.to_pydantic_ai()
