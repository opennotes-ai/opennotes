from src.config import settings

ADC_SENTINEL = "ADC"

DEFAULT_MODELS_BY_PROVIDER: dict[str, str] = {
    "anthropic": "anthropic:claude-3-opus-20240229",
    "vertex_ai": "google-vertex:gemini-2.5-pro",
    "gemini": "google-gla:gemini-2.5-pro",
}


def get_default_model_for_provider(provider: str) -> str:
    if provider == "openai":
        return settings.DEFAULT_FULL_MODEL.to_pydantic_ai()
    return DEFAULT_MODELS_BY_PROVIDER.get(provider, "unknown")
