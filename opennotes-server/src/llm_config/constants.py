from src.config import settings

ADC_SENTINEL = "ADC"

DEFAULT_MODELS_BY_PROVIDER: dict[str, str] = {
    "anthropic": "anthropic:claude-3-opus-20240229",
    "vertex_ai": "google-vertex:gemini-3.1-pro-preview",
    # The 'gemini' (google-gla) entry was removed in TASK-1450. Gemini models
    # are served exclusively through Vertex AI (google-vertex) now.
    # Note: simulation agents do not use a global default model here; each
    # agent profile inherits its own `sim_agents.model_name`.
}


def get_default_model_for_provider(provider: str) -> str:
    if provider == "openai":
        return settings.DEFAULT_FULL_MODEL.to_pydantic_ai()
    return DEFAULT_MODELS_BY_PROVIDER.get(provider, "unknown")
