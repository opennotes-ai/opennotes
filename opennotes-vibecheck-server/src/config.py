from functools import lru_cache

from pydantic import field_validator
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
    # Service-role key bypasses RLS. The cache tables
    # (vibecheck_scrapes / _analyses / _jobs / _job_utterances /
    # _web_risk_lookups) are locked down to service_role only — writes and
    # reads from the orchestrator + lifespan cache MUST use this key or
    # they hit `permission denied for table ...` under RLS. Anon key is
    # still exposed for public-facing read paths.
    VIBECHECK_SUPABASE_SERVICE_ROLE_KEY: str = ""

    VIBECHECK_DATABASE_HOST: str = ""
    VIBECHECK_DATABASE_PORT: int = 0

    # GCS bucket holding scrape screenshots (TASK-1480 GCS migration,
    # 2026-04-23). Replaces the prior Supabase Storage bucket — simpler
    # IAM, no anon-vs-service-role split, and avoids the missing-Supabase-
    # bucket failure mode we hit in prod. When unset (dev/test), the
    # cache falls back to an in-memory store and rows persist with a null
    # screenshot_storage_key. Provisioned in infra (gcs_screenshots.tf).
    VIBECHECK_GCS_SCREENSHOT_BUCKET: str = ""

    RATE_LIMIT_PER_IP_PER_HOUR: int = 10
    CACHE_TTL_HOURS: int = 72
    MAX_IMAGES_MODERATED: int = 30
    MAX_VIDEOS_MODERATED: int = 5
    WEB_RISK_CACHE_TTL_HOURS: int = 6

    # --- Cloud Tasks + internal worker endpoint (TASK-1473.12) ---
    # Defaults map the dev/test shape: empty strings so enqueue_job short-
    # circuits and raises a clear RuntimeError in envs that did not wire
    # the queue. Production values are set in .env.yaml; see
    # docs/vibecheck-server-deploy.md for the expected shape (queue name,
    # location, enqueuer service account, public server URL).
    VIBECHECK_TASKS_PROJECT: str = ""
    VIBECHECK_TASKS_LOCATION: str = ""
    VIBECHECK_TASKS_QUEUE: str = ""
    # OIDC-verified caller identity (Cloud Tasks signs tokens as this SA).
    VIBECHECK_TASKS_ENQUEUER_SA: str = ""
    # Also the OIDC audience — the full external URL Cloud Tasks is configured
    # to invoke (e.g. https://vibecheck.opennotes.ai). The server verifies the
    # token audience matches this value exactly.
    VIBECHECK_SERVER_URL: str = ""

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

    # TASK-1473.35: when set + the public POST carries
    # `X-Vibecheck-Test-Fail-Slug: <slug>`, the orchestrator forces a
    # synthetic failure for the named slot so the e2e section-retry
    # Playwright spec can drive a real round-trip retry. Default False
    # so the header is always ignored in production envs.
    VIBECHECK_ALLOW_TEST_FAIL_HEADER: bool = False

    # TASK-1485.03: "Recently vibe checked" gallery sizing + cache TTL.
    # The endpoint over-fetches and post-filters in Python (90% rule,
    # privacy filters, dedup), then truncates to LIMIT. Default 5 keeps
    # the home-page gallery compact while leaving headroom to dial up via
    # env var without a deploy.
    VIBECHECK_RECENT_ANALYSES_LIMIT: int = 5
    # Cache TTL must be < 900s (signed screenshot URLs are valid for 15min;
    # cached signed URLs cannot outlive their signature). Field validator
    # asserts < 900 — picking the cache-stores-signed-urls path keeps
    # per-request CPU minimal at the cost of this constraint.
    VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS: int = 60

    @field_validator("VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS")
    @classmethod
    def _recent_cache_ttl_under_signed_url_validity(cls, value: int) -> int:
        if value < 0:
            raise ValueError(
                "VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS must be >= 0"
            )
        if value >= 900:
            raise ValueError(
                "VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS must be < 900 "
                "(signed screenshot URLs expire at 15 minutes)"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

# --- Vertex AI settings (Gemini 3.1 Pro Preview is the primary LLM;
#     OpenAI is only used for moderation).
#     Settings names mirror opennotes-server convention.
