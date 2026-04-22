from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    VERTEXAI_PROJECT: str = "open-notes-core"
    VERTEXAI_LOCATION: str = "global"
    VERTEXAI_MODEL: str = "google-vertex:gemini-3.1-pro-preview"
    VERTEXAI_EMBEDDING_MODEL: str = "google-vertex:gemini-embedding-001"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    FIRECRAWL_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    VIBECHECK_SUPABASE_URL: str = ""
    VIBECHECK_SUPABASE_DB_PASSWORD: str = ""
    VIBECHECK_SUPABASE_ANON_KEY: str = ""

    RATE_LIMIT_PER_IP_PER_HOUR: int = 10
    CACHE_TTL_HOURS: int = 72

    # TASK-1473.14 — GET /api/analyze/{job_id} poll rate limit.
    # Two separate buckets (slowapi applies both via stacked decorators):
    #   RATE_LIMIT_POLL_BURST is a per-second cap so a runaway client
    #   cannot flood the DB in a single tight loop.
    #   RATE_LIMIT_POLL_SUSTAINED is a per-minute cap that bounds
    #   cumulative load while still allowing the progressive-fill UI
    #   to poll at ~500ms cadence for the full job lifetime.
    # Both buckets are keyed on (ip, job_id) so distinct jobs don't
    # share a budget.
    RATE_LIMIT_POLL_BURST: int = 10
    RATE_LIMIT_POLL_SUSTAINED: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()

# --- Vertex AI settings (Gemini 3.1 Pro Preview is the primary LLM;
#     OpenAI is only used for moderation).
#     Settings names mirror opennotes-server convention.
