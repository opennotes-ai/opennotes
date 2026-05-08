from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    VERTEXAI_PROJECT: str = "open-notes-core"
    VERTEXAI_LOCATION: str = "global"
    VERTEXAI_FAST_MODEL: str = "google-vertex:gemini-3-flash-preview"
    VERTEXAI_MODEL: str = "google-vertex:gemini-3.1-pro-preview"
    VERTEXAI_EMBEDDING_MODEL: str = "google-vertex:gemini-embedding-001"
    # Conservative per-process cap while production Cloud Run max_instances=1.
    VERTEX_MAX_CONCURRENCY: int = 4

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

    # TASK-1498: bucket for direct browser-to-GCS PDF uploads. The
    # POST /api/upload-pdf route fails fast (500) if unset so callers
    # never get a partially configured URL.
    VIBECHECK_PDF_UPLOAD_BUCKET: str = ""

    # TASK-1483.09: per-real-user rate limiting now lives at the web tier
    # (vibecheck-web reads the GCLB-set X-Forwarded-For and enforces a
    # per-IP bucket before calling /api/analyze). This backend limiter is
    # therefore keyed on the SolidStart server IP — useless as per-user
    # enforcement, but retained as a coarse defense-in-depth safety valve
    # against the FastAPI service being hit directly. Default 5000 so the
    # blunt per-instance bucket does not throttle legit multi-user traffic
    # that already passed the web-tier limiter — at 80 concurrent requests
    # per Cloud Run instance and a few seconds per request, normal traffic
    # would run at ~3000-4000/hr per instance under load.
    # The web tier is the source of truth; raise this knob (or remove the
    # decorator) before tightening backend enforcement, never the reverse.
    RATE_LIMIT_PER_IP_PER_HOUR: int = 5000
    CACHE_TTL_HOURS: int = 72
    MAX_IMAGES_MODERATED: int = 30
    MAX_VIDEOS_MODERATED: int = 5
    WEB_RISK_CACHE_TTL_HOURS: int = 6
    # TASK-1483.24: Vision API SafeSearch results are stable per-URL within
    # the cache window. Cache aggressively (7 days) to bound per-job cost;
    # override via env to bump down if a flagged image needs re-evaluation.
    VISION_IMAGE_CACHE_TTL_HOURS: int = 168
    # TASK-1483.24: Frame findings for a given video URL are stable; mirror
    # the image cache TTL. Lower if videos at a stable URL get re-edited.
    VISION_VIDEO_CACHE_TTL_HOURS: int = 168
    EVIDENCE_MAX_EXTERNAL_RETRIEVALS: int = 5
    PREMISES_MAX_CLAIMS_PER_BATCH: int = 30

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
    VIBECHECK_SCRAPE_API_TOKEN: str = ""
    VIBECHECK_WEB_URL: str = ""

    # TASK-1473.35: when set + the public POST carries
    # `X-Vibecheck-Test-Fail-Slug: <slug>`, the orchestrator forces a
    # synthetic failure for the named slot so the e2e section-retry
    # Playwright spec can drive a real round-trip retry. Default False
    # so the header is always ignored in production envs.
    VIBECHECK_ALLOW_TEST_FAIL_HEADER: bool = False

    # TASK-1485.03: "Recently vibe checked" gallery sizing + cache TTL.
    # The endpoint over-fetches and post-filters in Python (90% rule,
    # privacy filters, dedup), then truncates to LIMIT. Default 6 matches
    # the 3-column gallery layout (2 rows x 3) while leaving headroom to
    # dial up via env var without a deploy.
    VIBECHECK_RECENT_ANALYSES_LIMIT: int = 6
    # Cache TTL must be < 900s (signed screenshot URLs are valid for 15min;
    # cached signed URLs cannot outlive their signature). Field validator
    # asserts < 900 — picking the cache-stores-signed-urls path keeps
    # per-request CPU minimal at the cost of this constraint.
    VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS: int = 60

    # TASK-1474.23.03.24: Cloud Run sets containerConcurrency=80 for
    # vibecheck-server. The startup lifespan sizes asyncio's default
    # ThreadPoolExecutor against this value so `asyncio.to_thread` calls in
    # the extractor (TASK-1474.23.04) don't saturate the default ~5-6 worker
    # pool. Override via VIBECHECK_CONTAINER_CONCURRENCY when the Cloud Run
    # revision uses a different concurrency setting.
    VIBECHECK_CONTAINER_CONCURRENCY: int = 80

    # TASK-1508.10: opinion highlights floor/scale coefficients for the
    # sidebar. Both are configurable to tune sensitivity of influence
    # filtering in production without code changes.
    VIBECHECK_OPINIONS_HIGHLIGHTS_AUTHOR_DIVISOR: float = 2.0
    VIBECHECK_OPINIONS_HIGHLIGHTS_OCCURRENCE_MULTIPLIER: float = 1.5
    # TASK-1508.09: cap opinion clusters sent to the trends/oppositions
    # analyzer. Keep tunable so production can trade result breadth against
    # LLM cost without a code deploy.
    VIBECHECK_TRENDS_OPPOSITIONS_MAX_CLUSTERS: int = 50

    # TASK-1588.17 AC#6: Set-Cookie's Secure attribute. Browsers silently drop
    # `Secure` cookies on `http://localhost`, so a hard-coded True breaks the
    # whole uid-bound rate limiting + feedback flow in dev. Default False so a
    # plain `http://localhost:5173` dev session can persist the cookie; set to
    # True in staging/prod env config (we ship over HTTPS there).
    VIBECHECK_COOKIE_SECURE: bool = False

    @field_validator("VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS")
    @classmethod
    def _recent_cache_ttl_under_signed_url_validity(cls, value: int) -> int:
        if value < 0:
            raise ValueError("VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS must be >= 0")
        if value >= 900:
            raise ValueError(
                "VIBECHECK_RECENT_ANALYSES_CACHE_TTL_SECONDS must be < 900 "
                "(signed screenshot URLs expire at 15 minutes)"
            )
        return value

    @field_validator("VERTEX_MAX_CONCURRENCY")
    @classmethod
    def _vertex_max_concurrency_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("VERTEX_MAX_CONCURRENCY must be > 0")
        return value

    @field_validator(
        "VIBECHECK_OPINIONS_HIGHLIGHTS_AUTHOR_DIVISOR",
        "VIBECHECK_OPINIONS_HIGHLIGHTS_OCCURRENCE_MULTIPLIER",
    )
    @classmethod
    def _opinion_highlights_scaling_factors_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("opinion highlights scaling factors must be > 0")
        return value

    @field_validator("VIBECHECK_TRENDS_OPPOSITIONS_MAX_CLUSTERS")
    @classmethod
    def _trends_oppositions_max_clusters_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("trends/oppositions max clusters must be >= 0")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --- Vertex AI settings (Gemini 3.1 Pro Preview is the primary LLM;
#     OpenAI is only used for moderation).
#     Settings names mirror opennotes-server convention.
