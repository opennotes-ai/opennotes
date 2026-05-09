"""Orchestrator for the async job pipeline (TASK-1473.12).

Called from the internal worker endpoint
(`POST /_internal/jobs/{job_id}/run`) once the OIDC dependency has accepted
the caller. The orchestrator is the single place that owns the pipeline
lifecycle:

    1. CAS-claim the job row by rotating `attempt_id` from pending->extracting.
       Stale redeliveries (whose `expected_attempt_id` no longer matches the
       row) are dropped silently — Cloud Tasks will not retry a 200 response.
    2. Spawn a heartbeat task that bumps `vibecheck_jobs.heartbeat_at` every
       `HEARTBEAT_INTERVAL_SEC` seconds while the pipeline runs. The sweeper
       watches heartbeat_at to reclaim orphaned jobs (.18 ticket).
    3. Scrape via Firecrawl (or hit the cache), revalidate the final URL via
       the SSRF guard (catching redirects into private space), extract
       utterances, then fan out to the ten per-section analysis slots via
       `asyncio.gather`.
    4. Finalize: `maybe_finalize_job` UPSERTs the `vibecheck_analyses` cache
       and flips the job status.

Error handling ladder (CTU + Cloud Tasks retry contract):

    TransientError        -> reset attempt_id + status=pending, return 503
                             (Cloud Tasks re-enqueues within retry config)
    TerminalError         -> status=failed + error_code/error_message, 200
                             (Cloud Tasks does NOT retry)
    any other Exception   -> log with exc_info, treat as transient (reset + 503)

Scrape ladder (TASK-1488.05): `_scrape_step` runs a two-tier fetch:

    Tier 1 — /scrape with single-attempt budget (`max_attempts=1`).
             Refusal envelopes (FirecrawlBlocked) and INTERSTITIAL bundles
             escalate to Tier 2; AUTH_WALL and LEGITIMATELY_EMPTY classifications
             short-circuit to TerminalError(EXTRACTION_FAILED) — no escalation.
    Tier 2 — /interact with default retry budget. A non-OK Tier 2 result
             raises TerminalError(UNSUPPORTED_SITE) carrying both tier reasons,
             flipping ErrorCode.UNSUPPORTED_SITE from a dead enum into a live
             signal that the page is unrenderable for our pipeline.

The ladder emits a single `vibecheck.scrape_step` Logfire span carrying
`tier_attempted`, `tier_success`, `escalation_reason`, and
`final_classification` so a partial trace pinpoints whether the fetch
died on Tier 1, escalated and recovered, or burned through both tiers.

`run_job` is the synchronous entrypoint the route handler awaits. The
route itself never sees exceptions — `run_job` returns a `RunResult` with
the HTTP status to emit. The heartbeat task is cancelled in every exit
path via try/finally so no background coroutine outlives the request.

Module-level constants (HEARTBEAT_INTERVAL_SEC) and factory hooks
(_build_scrape_cache, _build_firecrawl_client, _run_all_sections,
_run_pipeline) are the monkeypatch seams unit tests use; production code
paths call them directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Final, Literal, NoReturn
from urllib.parse import urlparse
from uuid import UUID, uuid4

import asyncpg
import httpx
import logfire

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.claims.dedupe_slot import run_claims_dedup
from src.analyses.claims.evidence_slot import run_claims_evidence
from src.analyses.claims.facts_agent import run_facts_claims_known_misinfo
from src.analyses.claims.premises_slot import run_claims_premises
from src.analyses.opinions._highlights_schemas import OpinionsHighlightsReport
from src.analyses.opinions._schemas import SentimentStatsReport, SubjectiveClaim
from src.analyses.opinions._trends_schemas import TrendsOppositionsReport
from src.analyses.opinions.highlights_slot import run_highlights
from src.analyses.opinions.sentiment_slot import run_sentiment
from src.analyses.opinions.subjective_slot import run_subjective
from src.analyses.opinions.trends_oppositions_slot import (
    FIRST_RUN_DEPENDENCY_PAYLOAD,
    TrendsDependenciesNotReadyError,
    run_trends_oppositions,
)
from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.safety.image_moderation_worker import run_image_moderation
from src.analyses.safety.moderation_slot import run_safety_moderation
from src.analyses.safety.recommendation_agent import (
    SafetyRecommendationInputs,
    run_safety_recommendation,
)
from src.analyses.safety.video_intelligence_worker import run_video_intelligence
from src.analyses.safety.video_moderation_worker import run_video_moderation
from src.analyses.safety.web_risk_worker import run_web_risk
from src.analyses.schemas import (
    ErrorCode,
    PageKind,
    SectionSlot,
    SectionSlug,
    SectionState,
)
from src.analyses.synthesis.headline_summary_agent import (
    HeadlineSummaryInputs,
    run_headline_summary,
)
from src.analyses.synthesis.weather_report_agent import (
    WeatherInputs,
    evaluate_weather,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport
from src.analyses.tone.flashpoint_slot import run_flashpoint
from src.analyses.tone.scd_slot import run_scd
from src.cache.scrape_cache import (
    CachedScrape,
    ScrapeTier,
    SupabaseScrapeCache,
)
from src.config import Settings
from src.coral import (
    CoralFetchError,
    CoralSignal,
    CoralUnsupportedError,
    detect_coral,
    fetch_coral_comments,
    merge_coral_into_scrape,
)
from src.firecrawl_client import (
    FirecrawlBlocked,
    FirecrawlClient,
    FirecrawlError,
    ScrapeMetadata,
    ScrapeResult,
)
from src.jobs.enqueue import enqueue_section_retry, enqueue_video_moderation_poll
from src.jobs.finalize import maybe_finalize_job
from src.jobs.pdf_extract import PDFExtractionError, pdf_extract_step
from src.jobs.scrape_quality import ScrapeQuality, classify_scrape
from src.jobs.section_defaults import empty_section_data as _empty_section_data
from src.jobs.slots import mark_slot_done, mark_slot_failed, write_slot
from src.jobs.utterance_writes import (
    UtterancePersistenceSuperseded,
    persist_utterances,
)
from src.monitoring import bind_contextvars, clear_contextvars, get_logger
from src.monitoring_metrics import (
    ACTIVE_JOBS,
    CLOUD_TASKS_REDELIVERIES,
    JOB_DURATION,
    SECTION_DURATION,
    SECTION_FAILURES,
    classify_error,
)
from src.platforms import PlatformSignal
from src.utils.url_security import (
    InvalidURL,
    revalidate_redirect_target,
    validate_public_http_url,
)
from src.utterances.errors import (
    TransientExtractionError,
    UtteranceExtractionError,
    ZeroUtterancesError,
)
from src.utterances.extractor import extract_utterances
from src.utterances.schema import UtterancesPayload
from src.viafoura import (
    ViafouraFetchError,
    ViafouraSignal,
    ViafouraUnsupportedError,
    build_viafoura_actions,
    detect_viafoura,
    fetch_viafoura_comments,
    merge_viafoura_into_scrape,
)

logger = get_logger(__name__)


HEARTBEAT_INTERVAL_SEC: float = 5.0
"""Heartbeat bump cadence. Tests override to a shorter interval."""


EXTRACT_TRANSIENT_MAX_ATTEMPTS: Final[int] = 3
"""Matches the max_attempts for the vibecheck-jobs Cloud Tasks queue
(google_cloud_tasks_queue.vibecheck_jobs in cloud_tasks.tf). On the 3rd
transient extraction failure, flip the row to TerminalError(UPSTREAM_ERROR).
Tight local retries in run_vertex_agent_with_retry absorb fast Vertex 429
bursts before they surface as TransientExtractionError, so each Cloud Tasks
delivery may now consume one job-level transient attempt for a genuine
upstream flake. This cap is intentionally equal to Cloud Tasks max_attempts:
the backstop fires on the same final delivery that Cloud Tasks would also
stop, preventing wasted deliveries that the prior cap of 2 caused.
"""

_SECTION_RETRY_DEPENDENCY_BACKOFF_SECONDS: Final[int] = 30
_TRENDS_DEPENDENCY_WAIT_ITERATION_KEY: Final[str] = "dependency_wait_iteration"


_CORAL_PARTIAL_MARKERS: tuple[str, ...] = (
    "coral_talk_stream",
    'data-gtm-class="open-community"',
    'data-gtm-class=\'open-community\'',
    'comments-show-comments-button',
    "coral-talk-stream",
    "data-embed-coral",
    "coral_thread",
    "coral-thread",
    "coral-display-comments",
    "coral_display_comments",
)
_LA_TIMES_HOSTS: Final[tuple[str, ...]] = ("latimes.com", "www.latimes.com")
_LA_TIMES_CORAL_ORIGIN: Final[str] = "https://latimes.coral.coralproject.net"
_CORAL_TIER2_ACTION_SELECTORS: Final[tuple[str, ...]] = (
    'button[data-testid="comments-show-comments-button"]',
    'button[data-testid="comments-button"]',
    'button[data-qa="comments-btn"]',
    'button[aria-label*="comments" i]',
    'button[data-gtm-class="open-community"]',
    "#coral_talk_stream button",
    "#coral_thread button",
    "#coral-thread button",
    "#coral-display-comments",
    "#coral_display_comments",
    "[data-embed-coral] button",
    "ps-comments#coral_talk_stream button",
    "ps-comments#coral_talk_stream",
)

_CORAL_DETECTION_FETCH_TIMEOUT_SECONDS: float = 1.5


class TransientError(Exception):
    """Retryable error — the handler resets the job row and returns 503."""


class TerminalError(Exception):
    """Non-retryable error with a classified `error_code`.

    The handler writes `status=failed`, `error_code`, and
    `error_message` to the job row and returns 200 so Cloud Tasks does
    not retry. Callers pass the stable `ErrorCode` enum.

    Two payload fields, by intent:
    - `error_detail`: free-form prose summary intended for log surfacing
      and the (TEXT) `vibecheck_jobs.error_message` column. Stable for
      operators reading logs; NOT a stable test surface. **Never
      rendered to end users** — the FE renders curated per-code copy
      via `JobFailureCard` (TASK-1488.19) so internal vendor strings
      don't leak through this column into customer-facing UI.
    - `detail`: optional structured fields. Currently a test-only
      payload — not persisted (no JSONB column on `vibecheck_jobs`) and
      not surfaced as Logfire span attributes by the `run_job` catch
      site. Tests should assert on specific `detail[k]` keys instead of
      substrings of `error_detail` so a reword of the prose summary
      does not break tests with identical behavior. Defaults to `{}` so
      existing two-arg raise sites keep working unchanged; new raises
      populate it as their tests need to de-brittle
      (TASK-1474.23.03.13).
    """

    def __init__(
        self,
        error_code: ErrorCode,
        error_detail: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_detail)
        self.error_code = error_code
        self.error_detail = error_detail
        self.detail: dict[str, Any] = detail or {}


class HandlerSuperseded(Exception):  # noqa: N818 — matches spec terminology; not raised as an "Error"
    """Raised when a mid-pipeline CAS guard detects the attempt rotated
    out from under us. The handler returns 200 and lets the newer worker
    own the job."""


@dataclass
class RunResult:
    """What the route handler emits after orchestration completes."""

    status_code: int
    """200 for success / terminal / superseded, 503 for transient."""


# ---------------------------------------------------------------------------
# Claim + reset helpers (CAS on `attempt_id`).
# ---------------------------------------------------------------------------

_CLAIM_SQL = """
UPDATE vibecheck_jobs
SET status = 'extracting',
    attempt_id = $2,
    heartbeat_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
  AND status = 'pending'
RETURNING attempt_id, url, COALESCE(source_type, 'url') AS source_type, test_fail_slug
"""

_RESET_SQL = """
UPDATE vibecheck_jobs
SET status = 'pending',
    attempt_id = $2,
    heartbeat_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
"""

_MARK_FAILED_SQL = """
UPDATE vibecheck_jobs
SET status = 'failed',
    error_code = $2,
    error_message = $3,
    error_host = COALESCE($5, error_host),
    finished_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $4
"""

_SET_ANALYZING_SQL = """
UPDATE vibecheck_jobs
SET status = 'analyzing',
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $2
"""

_HEARTBEAT_SQL = """
UPDATE vibecheck_jobs
SET heartbeat_at = now()
WHERE job_id = $1
  AND attempt_id = $2
"""

_LOAD_SAFETY_SECTIONS_SQL = """
SELECT sections
FROM vibecheck_jobs
WHERE job_id = $1
  AND attempt_id = $2
"""

_LOAD_BROWSER_HTML_SCRAPE_SQL = """
SELECT
    url,
    final_url,
    page_title,
    markdown,
    html,
    screenshot_storage_key
FROM vibecheck_scrapes
WHERE tier = 'browser_html'
  AND job_id = $1
  AND expires_at > now()
  AND evicted_at IS NULL
"""


async def _load_browser_html_scrape(
    pool: Any, job_id: UUID
) -> CachedScrape | None:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                _LOAD_BROWSER_HTML_SCRAPE_SQL,
                job_id,
            )
    except Exception as exc:
        raise TerminalError(
            ErrorCode.INTERNAL,
            f"failed to load browser_html scrape for job={job_id}: {exc}",
        ) from exc

    if row is None:
        return None

    return CachedScrape(
        markdown=row["markdown"] or "",
        html=row["html"],
        raw_html=None,
        screenshot=None,
        links=None,
        metadata=ScrapeMetadata(
            title=row["page_title"],
            source_url=row["final_url"] or row["url"],
        ),
        warning=None,
        storage_key=row["screenshot_storage_key"],
    )

_WRITE_SAFETY_RECOMMENDATION_SQL = """
UPDATE vibecheck_jobs
SET safety_recommendation = $2::jsonb,
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
"""

# TASK-1508.04.03: load all section data plus the freshly-written safety
# recommendation and job-level page metadata so the headline summarizer can
# synthesize from the structured outputs without re-reading raw utterances.
_LOAD_HEADLINE_INPUTS_SQL = """
SELECT
    j.sections,
    j.safety_recommendation,
    j.page_title AS page_title,
    j.page_kind AS page_kind
FROM vibecheck_jobs j
WHERE j.job_id = $1
  AND j.attempt_id = $2
"""

_WRITE_HEADLINE_SUMMARY_SQL = """
UPDATE vibecheck_jobs
SET headline_summary = $2::jsonb,
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
"""

_WRITE_WEATHER_REPORT_SQL = """
UPDATE vibecheck_jobs
SET weather_report = $2::jsonb,
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
"""

# TASK-1474.23.02: post-Gemini stage breadcrumb. CAS on attempt_id so a
# stale worker can't overwrite the marker after a fresh attempt rotated.
_SET_LAST_STAGE_SQL = """
UPDATE vibecheck_jobs
SET last_stage = $2,
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $3
"""

# TASK-1474.23.03.04: in-row backstop counter for transient extraction
# errors. CAS on attempt_id so a stale worker cannot double-increment the
# counter after a fresh attempt has rotated. RETURNING the new value lets
# the caller decide whether to escalate to TerminalError(UPSTREAM_ERROR).
_INCREMENT_EXTRACT_TRANSIENT_SQL = """
UPDATE vibecheck_jobs
SET extract_transient_attempts = extract_transient_attempts + 1,
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $2
RETURNING extract_transient_attempts
"""

# Stage names recorded in `vibecheck_jobs.last_stage` and as Logfire span
# attributes. These are also the names of the Logfire spans wrapped around
# each step in `_run_pipeline` after `extract_utterances` returns.
_STAGE_PERSIST_UTTERANCES = "persist_utterances"
_STAGE_SET_ANALYZING = "set_analyzing"
_STAGE_RUN_SECTIONS = "run_sections"
_STAGE_SAFETY_RECOMMENDATION = "safety_recommendation"
_STAGE_HEADLINE_SUMMARY = "headline_summary"
_STAGE_WEATHER_REPORT = "weather_report"
_STAGE_FINALIZE = "finalize"


async def _claim_job(
    pool: Any,
    job_id: UUID,
    expected_attempt_id: UUID,
) -> tuple[UUID, str, str, str | None] | None:
    """Atomically rotate attempt_id and set status=extracting.

    Returns (new_attempt_id, url, source_type, test_fail_slug) on success,
    None when the CAS fails (stale expected_attempt_id or status already moved).
    `test_fail_slug` is the e2e Playwright hook (TASK-1473.35);
    always-None in production where the env flag defaults off. Cloud
    Tasks redeliveries of a superseded enqueue fall into the None
    branch; the caller returns 200 no-op.
    """
    new_attempt = uuid4()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            _CLAIM_SQL, job_id, new_attempt, expected_attempt_id
        )
    if row is None:
        return None
    source_type = row["source_type"]
    if source_type not in {"url", "pdf", "browser_html"}:
        source_type = "url"
    return row["attempt_id"], row["url"], source_type, row["test_fail_slug"]


async def _reset_for_retry(
    pool: Any,
    job_id: UUID,
    *,
    task_attempt: UUID,
    expected_attempt_id: UUID,
) -> None:
    """Revert status to pending and restore the caller's envelope attempt_id.

    Cloud Tasks will retry with the *same* body payload (same
    expected_attempt_id), so the reset puts that value back in the row —
    the next delivery can re-claim cleanly.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            _RESET_SQL, job_id, expected_attempt_id, task_attempt
        )


async def _mark_failed(
    pool: Any,
    job_id: UUID,
    *,
    task_attempt: UUID,
    error_code: ErrorCode,
    error_message: str,
    error_host: str | None = None,
) -> None:
    """Flip the job row to status=failed with the classified error_code.

    `error_host` is the URL's hostname; populated by the caller for
    UNSUPPORTED_SITE so the FE can render host-specific copy
    ("We can't analyze {host} yet"). When None, the SQL leaves the
    existing `error_host` value untouched (legacy paths that never
    populated it stay null) (TASK-1488.13).
    """
    async with pool.acquire() as conn:
        await conn.execute(
            _MARK_FAILED_SQL,
            job_id,
            error_code.value,
            error_message,
            task_attempt,
            error_host,
        )


async def _set_analyzing(pool: Any, job_id: UUID, task_attempt: UUID) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SET_ANALYZING_SQL, job_id, task_attempt)


async def _increment_extract_transient_attempts(
    pool: Any,
    job_id: UUID,
    *,
    task_attempt: UUID,
) -> int | None:
    """CAS-increment the per-row backstop counter. Returns the new value,
    or None when the CAS missed (stale attempt — caller should not act on
    the backstop), the column is missing on an un-migrated DB, or the DB
    write itself failed.

    Behavioral contract for the caller:
    - new_count is None: best-effort fallback — classify as TransientError
      so Cloud Tasks redelivers (we'd rather over-retry than silently
      flip terminal on a transient DB or schema problem).
    - new_count >= EXTRACT_TRANSIENT_MAX_ATTEMPTS: escalate to
      TerminalError(UPSTREAM_ERROR) so the row flips to failed BEFORE
      Cloud Tasks max_attempts=3 silently exhausts and leaves the row
      pending forever.

    The asyncpg.UndefinedColumnError catch is the deploy-time backstop:
    if the schema migration hasn't propagated yet, the worker keeps
    behaving exactly like the pre-counter system (transient → 503 →
    redelivery → eventual silent drop) instead of crashing on every
    transient flake.
    """
    try:
        async with pool.acquire() as conn:
            return await conn.fetchval(
                _INCREMENT_EXTRACT_TRANSIENT_SQL, job_id, task_attempt
            )
    except asyncpg.UndefinedColumnError:
        logger.warning(
            "extract_transient_attempts column missing on job %s; backstop "
            "disabled until schema migration is applied",
            job_id,
        )
        return None
    except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError):
        # Connection-class failures (pool exhaustion, peer reset, idle
        # disconnect, "pool is closed", "connection is closed"). The
        # increment didn't land but the failure mode is transient. Fall
        # through to plain TransientError so Cloud Tasks redelivers — the
        # next attempt's increment will catch up. Note: asyncpg.InterfaceError
        # also covers some client-misuse cases ("a connection is already
        # acquired"), but at this call site (single fetchval inside an
        # `async with pool.acquire()`) those would be programming bugs in
        # asyncpg/our pool code rather than transient runtime failures.
        # Programming bugs in OUR code (SQL syntax, RuntimeError) escape
        # this catch and the caller wraps them as TerminalError so they
        # don't silently disable the backstop.
        logger.exception(
            "extract_transient_attempts increment hit DB connection error "
            "for job %s",
            job_id,
        )
        return None


async def _set_last_stage(
    pool: Any, job_id: UUID, task_attempt: UUID, stage: str
) -> None:
    """Write the post-Gemini stage breadcrumb to `vibecheck_jobs.last_stage`.

    CAS-guarded on `attempt_id` so a stale worker can't overwrite the
    breadcrumb after a fresh attempt rotated. DB write failures are logged
    and swallowed — instrumentation must never tear down the pipeline.
    The breadcrumb survives a SIGKILL between stages because each write
    is a synchronous DB commit, giving operators a DB-visible marker even
    when no further log lines reach Cloud Logging or Logfire.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(_SET_LAST_STAGE_SQL, job_id, stage, task_attempt)
    except Exception as exc:
        logger.warning(
            "set_last_stage(%s) failed for job %s: %s", stage, job_id, exc
        )


# ---------------------------------------------------------------------------
# Heartbeat loop.
# ---------------------------------------------------------------------------


async def _heartbeat_loop(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    *,
    interval_sec: float,
) -> None:
    """Periodically bump `heartbeat_at` while the pipeline runs.

    The loop exits via CancelledError when the pipeline returns. Each
    bump CAS-guards on `attempt_id = task_attempt` so a heartbeat from a
    stale worker cannot keep a reclaimed job's row looking fresh.

    Lifecycle logs (TASK-1474.23.02 AC4) make it possible to distinguish
    'heartbeat task died early' from 'main handler died early' when the
    pipeline silently disappears post-Gemini.
    """
    logger.info(
        "heartbeat: started for job %s attempt %s", job_id, task_attempt
    )
    try:
        while True:
            await asyncio.sleep(interval_sec)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(_HEARTBEAT_SQL, job_id, task_attempt)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A heartbeat that can't reach the DB shouldn't tear
                # down the pipeline — the sweeper will reclaim if
                # needed. Log and continue.
                logger.warning(
                    "heartbeat update failed for job %s: %s", job_id, exc
                )
    except asyncio.CancelledError:
        logger.info(
            "heartbeat: cancelled for job %s attempt %s", job_id, task_attempt
        )
        return


# ---------------------------------------------------------------------------
# Scrape + revalidate + extract.
# ---------------------------------------------------------------------------


def _build_scrape_cache(settings: Settings) -> SupabaseScrapeCache:
    """Factory seam so tests can inject a fake cache.

    In production this wires a real Supabase client against the configured
    URL + service-role key. The scrape cache tables are RLS-locked down
    to service_role (see src/cache/schema.sql header), so anon-keyed
    clients 42501 on every get/put. Fall back to anon if service_role
    isn't configured so dev envs without the lockdown keep working.

    Screenshot blobs live in GCS (`VIBECHECK_GCS_SCREENSHOT_BUCKET`); when
    unset (dev/test), the cache falls back to an in-memory store so the
    DB leg still works and `screenshot_storage_key` rows just stay null.
    """
    from supabase import create_client  # noqa: PLC0415

    from src.cache.screenshot_store import (  # noqa: PLC0415
        GCSScreenshotStore,
        InMemoryScreenshotStore,
        ScreenshotStore,
    )

    key = (
        settings.VIBECHECK_SUPABASE_SERVICE_ROLE_KEY
        or settings.VIBECHECK_SUPABASE_ANON_KEY
    )
    client = create_client(settings.VIBECHECK_SUPABASE_URL, key)
    store: ScreenshotStore
    if settings.VIBECHECK_GCS_SCREENSHOT_BUCKET:
        store = GCSScreenshotStore(settings.VIBECHECK_GCS_SCREENSHOT_BUCKET)
    else:
        store = InMemoryScreenshotStore()
    return SupabaseScrapeCache(client, store, ttl_hours=settings.CACHE_TTL_HOURS)


def _build_firecrawl_client(settings: Settings) -> FirecrawlClient:
    """Factory seam mirroring `_build_scrape_cache` above.

    Default-retry client: `max_attempts=3` exponential-backoff. Used by the
    extractor's /v2/extract calls and by the Tier 2 /v2/interact escalation
    in `_scrape_step`. Callers that need the fail-fast Tier 1 probe should
    use `_build_firecrawl_tier1_client` instead.
    """
    return FirecrawlClient(api_key=settings.FIRECRAWL_API_KEY)


def _build_firecrawl_tier1_client(settings: Settings) -> FirecrawlClient:
    """Tier 1 client: single-attempt budget for fast escalation.

    The Tier 1 /scrape probe is paired with a Tier 2 /interact fallback,
    so retrying at this layer just delays the escalation. LinkedIn-style
    refusals arrive in <1s and inherit no value from the default 1s/2s/4s
    backoff. A separate seam (rather than a per-call kwarg) keeps tests
    able to inject a fail-fast fake without touching the default client
    used elsewhere in the pipeline.
    """
    return FirecrawlClient(api_key=settings.FIRECRAWL_API_KEY, max_attempts=1)


def _has_partial_coral_marker(html: str) -> bool:
    """Return True when the cleaned HTML has hints that a Coral embed is present.

    The fast /scrape pass strips more aggressive script/state metadata than
    full-page fetches. We treat these as "partial" Coral markers and only
    escalate to a bounded direct fetch when they are present and primary
    detection fails.
    """
    lowered = html.lower()
    if any(marker in lowered for marker in _CORAL_PARTIAL_MARKERS):
        return True
    return (
        "coral" in lowered
        and "data-env-url" in lowered
        and "data-story-id" in lowered
    )


def _is_la_times_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _LA_TIMES_HOSTS or host.endswith(".latimes.com")


def _la_times_render_only_signal(url: str) -> CoralSignal:
    return CoralSignal(
        iframe_src=f"{_LA_TIMES_CORAL_ORIGIN}/embed/stream",
        graphql_origin=_LA_TIMES_CORAL_ORIGIN,
        story_url=url,
        supports_graphql=False,
        embed_origin=_LA_TIMES_CORAL_ORIGIN,
        env_origin=_LA_TIMES_CORAL_ORIGIN,
    )


async def _fetch_coral_detection_html(url: str) -> str | None:
    """Fetch article HTML directly for a bounded Coral signature check.

    Only public URLs are fetched and failures are intentionally swallowed so
    detector misses are never terminal.
    """
    try:
        safe_url = validate_public_http_url(url)
    except InvalidURL:
        return None

    timeout = httpx.Timeout(_CORAL_DETECTION_FETCH_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(safe_url)
            response.raise_for_status()
    except Exception:
        return None

    content = response.text
    if not content:
        return None
    return content


async def _detect_platform_signal(  # noqa: PLR0911
    url: str,
    scrape: ScrapeResult,
) -> PlatformSignal | None:
    """Run staged comment-platform detection on scraped and optionally direct HTML."""
    candidates = [scrape.raw_html or "", scrape.html or ""]

    has_partial_marker = any(_has_partial_coral_marker(html) for html in candidates)

    for html in candidates:
        signal = detect_coral(html)
        if signal is not None:
            return signal
        signal = detect_viafoura(html)
        if signal is not None:
            return signal

    if not has_partial_marker:
        return None

    full_html = await _fetch_coral_detection_html(url)
    if full_html is None:
        if has_partial_marker and _is_la_times_url(url):
            return _la_times_render_only_signal(url)
        return None

    signal = detect_coral(full_html)
    if signal is None and has_partial_marker and _is_la_times_url(url):
        return _la_times_render_only_signal(url)
    if signal is not None:
        return signal
    return detect_viafoura(full_html)


# Tier 2 /interact action list. Default to a single 3s wait so JS-rendered
# pages have a chance to load before content is captured. Kept conservative
# — extending the action list would let the ladder masquerade as a richer
# interaction tier (login flows, scroll, click), which is out of scope for
# 1488.05 and would risk crossing ToS lines on auth-walled sites.
def _tier2_actions_for(platform_signal: PlatformSignal | None) -> list[dict[str, Any]]:
    """Build conservative Tier 2 /interact actions.

    For non-Coral pages we use the legacy single short wait so behavior
    stays unchanged. When a `CoralSignal` is present, we run a best-effort
    sequence to reveal comments in the embedded Coral stream. The selector-based
    steps are only used after upstream Coral detection has already succeeded.
    """
    if platform_signal is None:
        return [{"type": "wait", "milliseconds": 3000}]

    if isinstance(platform_signal, ViafouraSignal):
        return build_viafoura_actions(platform_signal)

    if not isinstance(platform_signal, CoralSignal):
        return [{"type": "wait", "milliseconds": 3000}]

    return [
        {"type": "wait", "milliseconds": 2000},
        {"type": "scroll", "direction": "down"},
        {
            "type": "executeJavascript",
            "script": """
                (async () => {
                    const selectors = __CORAL_TIER2_ACTION_SELECTORS__;
                    const sleep = (milliseconds) => new Promise((resolve) => {
                        setTimeout(resolve, milliseconds);
                    });
                    const shadowHostSelectors = [
                        "#coral-shadow-container",
                        "#coral-shadow-root",
                        "[id*='coral' i]",
                        "[class*='coral' i]",
                        "[data-testid*='coral' i]",
                        "[data-qa*='coral' i]",
                    ];
                    const lightDomHostSelectors = ["#comments", "#coral_thread", "#coral-thread"];
                    const markerSelector = "[data-platform-comments]";
                    const statusPrefix = "coral_status:";
                    const normalizeText = (value) => (value || "").replace(/\\s+/g, " ").trim();
                    const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
                    const isBoilerplateText = (text) => {
                        return (
                            text.length === 0
                            || /^(loading|show comments|comments)$/i.test(text)
                            || /^All Comments?\\(\\d+\\)$/i.test(text)
                            || /Our comments are moderated/i.test(text)
                            || /let's have a nice conversation/i.test(text)
                            || /advocating violence/i.test(text)
                        );
                    };
                    const isShadowIdleText = (text) => !text || /^(loading|show comments|comments)$/i.test(text);
                    const extractAuthorFromAriaLabel = (node) => {
                        const ariaLabel = normalizeText(node?.getAttribute?.("aria-label"));
                        if (!ariaLabel) {
                            return "";
                        }
                        const match = ariaLabel.match(
                            /^(?:Comment|Reply) from (.+?)\\s+\\d+\\s+(?:day|week|month|year|hour|minute|second)s?\\s+ago/i
                        ) || ariaLabel.match(/^(?:Comment|Reply) from (.+)$/i);
                        return normalizeText(match?.[1]);
                    };
                    const extractAuthor = (node) => {
                        const authorNode = node.querySelector?.(
                            "[data-testid*='author'],[class*='author'],[class*='username'],header"
                        );
                        if (authorNode) {
                            const text = normalizeText(authorNode.textContent);
                            if (text && text.toLowerCase() !== "commenter") {
                                return text;
                            }
                        }
                        return extractAuthorFromAriaLabel(node);
                    };
                    const appendStatusMarker = (status, comments = []) => {
                        document.querySelector(markerSelector)?.remove();
                        const marker = document.createElement("section");
                        marker.setAttribute("data-platform-comments", "true");
                        marker.setAttribute("data-platform", "coral");
                        marker.setAttribute("data-platform-status", status);
                        marker.setAttribute("aria-label", "Comments");

                        const heading = document.createElement("h2");
                        heading.textContent = "Comments";
                        marker.appendChild(heading);

                        for (const comment of comments) {
                            const item = document.createElement("article");
                            item.className = "comment";
                            const header = document.createElement("header");
                            header.textContent = comment.author;
                            const paragraph = document.createElement("p");
                            paragraph.textContent = comment.text;
                            item.appendChild(header);
                            item.appendChild(paragraph);
                            marker.appendChild(item);
                        }

                        (document.querySelector("article") || document.body).appendChild(marker);
                        return `${statusPrefix}${status};comments=${comments.length}`;
                    };
                    const commentFromNode = (node) => {
                        const text = normalizeText(node?.textContent);
                        if (!text || isBoilerplateText(text)) {
                            return null;
                        }
                        const author = extractAuthor(node);
                        if (!author) {
                            return null;
                        }
                        const body = normalizeText(node.querySelector?.("p")?.textContent) || text;
                        if (!body || isBoilerplateText(body)) {
                            return null;
                        }
                        return {author, text: body};
                    };
                    const cleanTextCommentBody = (author, value) => {
                        let body = normalizeText(value);
                        const authorPattern = escapeRegExp(author);
                        body = body.replace(
                            new RegExp(
                                `^${authorPattern}\\\\s*`
                                + "(?:Just now|\\\\d+\\\\s+"
                                + "(?:day|week|month|year|hour|minute|second)s?\\\\s+ago)",
                                "i"
                            ),
                            ""
                        );
                        body = body.replace(/^email-action-reply\\s*/i, "");
                        body = body.replace(/^In reply to [A-Za-z0-9_.-]+\\s*/i, "");
                        body = body.replace(
                            /(Respect\\d*email-action-reply|email-action-reply|ReplyShareReport|ShareReport|Thread Level \\d+:|\\d+\\s*Reactmore_horiz|Reactmore_horiz|more_horiz).*$/i,
                            ""
                        );
                        return normalizeText(body);
                    };
                    const collectCommentsFromText = (rootText) => {
                        const comments = [];
                        const text = normalizeText(rootText);
                        const pattern = /(?:Comment|Reply) from ([A-Za-z0-9_.-]{2,64})\\s+(?:Just now|\\d+\\s+(?:day|week|month|year|hour|minute|second)s?\\s+ago)/gi;
                        const matches = Array.from(text.matchAll(pattern));
                        for (let index = 0; index < matches.length; index += 1) {
                            const match = matches[index];
                            const author = normalizeText(match[1]);
                            const nextMatch = matches[index + 1];
                            const start = (match.index || 0) + match[0].length;
                            const end = nextMatch?.index ?? text.length;
                            const body = cleanTextCommentBody(author, text.slice(start, end));
                            if (!author || author.toLowerCase() === "commenter" || isBoilerplateText(body)) {
                                continue;
                            }
                            comments.push({author, text: body});
                        }
                        return comments;
                    };
                    const collectComments = (root) => {
                        const nodes = Array.from(root.querySelectorAll?.(
                            "article[data-testid='comment'],[data-testid='comment'],[class*='Comment_root'],[class*='comment-content'],[class*='commentContent'],[aria-label^='Comment from '],[aria-label^='Reply from ']"
                        ) || []);
                        const comments = nodes.map(commentFromNode).filter(Boolean);
                        if (comments.length > 0) {
                            return comments;
                        }
                        return collectCommentsFromText(root.textContent);
                    };
                    const queryAll = (selector) => Array.from(document.querySelectorAll?.(selector) || []);
                    const findShadowHost = () => {
                        let sawClosedShadowHost = false;
                        const seen = new Set();
                        for (const selector of shadowHostSelectors) {
                            for (const shadowHost of queryAll(selector)) {
                                if (!shadowHost || seen.has(shadowHost)) {
                                    continue;
                                }
                                seen.add(shadowHost);
                                if (shadowHost.shadowRoot) {
                                    return {host: shadowHost, root: shadowHost.shadowRoot, status: null};
                                }
                                const id = shadowHost.id || "";
                                if (/^coral-shadow-(container|root)$/i.test(id)) {
                                    sawClosedShadowHost = true;
                                }
                            }
                        }
                        return {
                            host: null,
                            root: null,
                            status: sawClosedShadowHost ? "shadow_closed" : null,
                        };
                    };
                    const findCommentsRoot = () => {
                        const shadow = findShadowHost();
                        if (shadow.root) {
                            return {root: shadow.root, status: null};
                        }
                        for (const selector of lightDomHostSelectors) {
                            const lightDomHost = document.querySelector(selector);
                            if (lightDomHost) {
                                return {root: lightDomHost, status: null};
                            }
                        }
                        if (shadow.status) {
                            return {root: null, status: shadow.status};
                        }
                        return {root: null, status: "host_missing"};
                    };
                    const copyShadowComments = () => {
                        const {root, status} = findCommentsRoot();
                        if (!root) {
                            return appendStatusMarker(status || "host_missing");
                        }
                        const rawText = normalizeText(root.textContent);
                        if (isShadowIdleText(rawText)) {
                            return appendStatusMarker("shadow_empty");
                        }

                        const comments = collectComments(root);
                        if (comments.length === 0) {
                            if (rawText) {
                                return appendStatusMarker("shell_only");
                            }
                            return appendStatusMarker("shadow_empty");
                        }
                        return appendStatusMarker("copied", comments);
                    };

                    const statusName = (status) => status.split(":", 2)[1]?.split(";", 1)[0] || "";
                    const initialStatus = copyShadowComments();
                    const initialStatusName = statusName(initialStatus);
                    if (initialStatusName === "copied") {
                        return initialStatus;
                    }

                    let clickedSelector = null;

                    for (const selector of selectors) {
                        const button = document.querySelector(selector);
                        if (button) {
                            button.click();
                            clickedSelector = selector;
                            if (typeof button.scrollIntoView === "function") {
                                button.scrollIntoView({block: "center"});
                            }
                            const commentsHost = findShadowHost().host
                                || lightDomHostSelectors
                                    .map((selector) => document.querySelector(selector))
                                    .find(Boolean);
                            if (typeof WheelEvent === "function" && commentsHost?.dispatchEvent) {
                                try {
                                    commentsHost.dispatchEvent(
                                        new WheelEvent("wheel", {deltaY: 500, bubbles: true})
                                    );
                                } catch (_error) {
                                    // best-effort for non-browser test runtimes
                                }
                            }
                            break;
                        }
                    }

                    if (clickedSelector === null) {
                        const buttons = Array.from(document.querySelectorAll?.("button,[role='button']") || []);
                        const button = buttons.find((candidate) => /show comments/i.test(candidate.textContent || ""));
                        if (button) {
                            button.click();
                            clickedSelector = "text:/show comments/i";
                        }
                    }

                    if (clickedSelector === null) {
                        if (
                            initialStatusName === "host_missing"
                            || initialStatusName === "shadow_closed"
                            || initialStatusName === "shell_only"
                        ) {
                            return initialStatus;
                        }
                        return appendStatusMarker("clicked_no_match");
                    }

                    for (let attempt = 0; attempt < 30; attempt += 1) {
                        const status = copyShadowComments();
                        if (statusName(status) === "copied") {
                            return clickedSelector ? `${status};clicked=${clickedSelector}` : status;
                        }
                        await sleep(1000);
                    }

                    return appendStatusMarker("timeout");
                })();
            """.replace(
                "__CORAL_TIER2_ACTION_SELECTORS__",
                json.dumps(list(_CORAL_TIER2_ACTION_SELECTORS)),
            ),
        },
        {"type": "wait", "milliseconds": 3000},
        {"type": "scroll", "direction": "down"},
    ]


async def _cache_put_or_keyless(
    scrape_cache: SupabaseScrapeCache,
    url: str,
    fresh: Any,
    *,
    tier: ScrapeTier,
) -> CachedScrape:
    """Persist `fresh` under `(url, tier)`; on DB failure fall back to a
    keyless `CachedScrape` wrapper so the caller still has usable bytes.
    Mirrors the pre-1488.05 fallback pattern from the original `_scrape_step`.
    """
    try:
        return await scrape_cache.put(url, fresh, tier=tier)
    except Exception as exc:
        logger.warning(
            "scrape cache put failed for %s (tier=%s): %s", url, tier, exc
        )
        return CachedScrape(
            markdown=fresh.markdown,
            html=fresh.html,
            raw_html=fresh.raw_html,
            screenshot=fresh.screenshot,
            links=fresh.links,
            metadata=fresh.metadata,
            warning=fresh.warning,
            storage_key=None,
        )


@dataclass
class _Tier1Outcome:
    """Result of running Tier 1. The caller dispatches on these fields:

    - `cached` is set on Tier 1 OK (return immediately).
    - `terminal` is set on AUTH_WALL / LEGITIMATELY_EMPTY (raise without
      escalating).
    - Otherwise, `escalation_reason` + `tier1_reason` describe why we
      need Tier 2.
    - `platform_signal` carries the detected comment-platform signal (if any)
      when Tier 1 succeeds/partially succeeds, and `platform_outcome` captures
      whether we merged comments or hit a fallback.

    `final_classification` is always populated so the orchestrator can
    record it on the span even when we're about to raise.
    """

    cached: CachedScrape | None
    terminal: TerminalError | None
    escalation_reason: str | None
    tier1_reason: str
    final_classification: str
    platform_signal: PlatformSignal | None
    platform_outcome: str | None


_SUCCESSFUL_CACHE_REUSE_TIERS: Final[tuple[ScrapeTier, ...]] = (
    "interact",
    "scrape",
)


async def _run_tier1(  # noqa: PLR0911, PLR0912
    url: str,
    scrape_client: FirecrawlClient,
    scrape_cache: SupabaseScrapeCache,
) -> _Tier1Outcome:
    """Tier 1 /scrape probe: classify and decide return / terminal / escalate.

    Raises `TransientError` on non-refusal upstream errors so Cloud Tasks
    redelivers via the envelope-level retry budget. AUTH_WALL and
    LEGITIMATELY_EMPTY are returned as `terminal` outcomes (not raised here)
    so the caller still gets to record span attributes before re-raising.
    """
    try:
        fresh = await scrape_client.scrape(
            url,
            formats=["markdown", "html", "rawHtml", "screenshot@fullPage"],
            only_main_content=True,
        )
    except FirecrawlBlocked as exc:
        return _Tier1Outcome(
            cached=None,
            terminal=None,
            escalation_reason="firecrawl_blocked",
            tier1_reason=f"firecrawl_blocked: {exc}",
            # No classification ran — we never saw a bundle. Track the
            # refusal as the "classification" for span observability.
            final_classification="firecrawl_blocked",
            platform_signal=None,
            platform_outcome=None,
        )
    except FirecrawlError as exc:
        raise TransientError(f"firecrawl scrape failed: {exc}") from exc
    except Exception as exc:
        raise TransientError(f"firecrawl scrape failed: {exc}") from exc

    quality = classify_scrape(fresh)
    if quality is ScrapeQuality.OK:
        signal = await _detect_platform_signal(url, fresh)
        if signal is None:
            cached_t1 = await _cache_put_or_keyless(
                scrape_cache, url, fresh, tier="scrape"
            )
            return _Tier1Outcome(
                cached=cached_t1,
                terminal=None,
                escalation_reason=None,
                tier1_reason="ok",
                final_classification="ok",
                platform_signal=None,
                platform_outcome=None,
            )

        if isinstance(signal, ViafouraSignal):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    comments = await fetch_viafoura_comments(
                        signal,
                        url,
                        client=client,
                    )
            except (ViafouraFetchError, ViafouraUnsupportedError) as exc:
                await _cache_put_or_keyless(scrape_cache, url, fresh, tier="scrape")
                return _Tier1Outcome(
                    cached=None,
                    terminal=None,
                    escalation_reason="viafoura_api_failed",
                    tier1_reason=f"viafoura_api_failed: {exc}",
                    final_classification="ok",
                    platform_signal=signal,
                    platform_outcome="viafoura_api_failed",
                )

            merged = merge_viafoura_into_scrape(fresh, comments.comments_markdown)
            cached_t1 = await _cache_put_or_keyless(
                scrape_cache, url, merged, tier="scrape"
            )
            return _Tier1Outcome(
                cached=cached_t1,
                terminal=None,
                escalation_reason=None,
                tier1_reason="ok",
                final_classification="ok",
                platform_signal=signal,
                platform_outcome="viafoura_merged",
            )

        if not isinstance(signal, CoralSignal):
            return _Tier1Outcome(
                cached=None,
                terminal=None,
                escalation_reason="platform_signal_unsupported",
                tier1_reason="platform_signal_unsupported",
                final_classification="ok",
                platform_signal=signal,
                platform_outcome="unsupported",
            )

        if not signal.supports_graphql:
            return _Tier1Outcome(
                cached=None,
                terminal=None,
                escalation_reason="coral_graphql_unsupported",
                tier1_reason="coral_graphql_unsupported",
                final_classification="ok",
                platform_signal=signal,
                platform_outcome="coral_render_only",
            )

        try:
            comments = await fetch_coral_comments(
                signal.graphql_origin,
                signal.story_url,
            )
        except (CoralFetchError, CoralUnsupportedError) as exc:
            iframe_markdown: str | None = None

            try:
                fallback_iframe_url = validate_public_http_url(signal.iframe_src)
            except InvalidURL:
                pass
            else:
                try:
                    iframe_scrape = await scrape_client.scrape(
                        fallback_iframe_url,
                        formats=["markdown", "html"],
                        only_main_content=False,
                    )
                except Exception:
                    pass
                else:
                    if (
                        classify_scrape(iframe_scrape) is ScrapeQuality.OK
                        and isinstance(iframe_scrape.markdown, str)
                        and iframe_scrape.markdown.strip()
                    ):
                        final_iframe_source_url = (
                            iframe_scrape.metadata.source_url
                            if iframe_scrape.metadata
                            else None
                        )
                        if final_iframe_source_url is None:
                            iframe_markdown = iframe_scrape.markdown
                        else:
                            try:
                                revalidate_redirect_target(final_iframe_source_url)
                            except (InvalidURL, ValueError):
                                pass
                            else:
                                iframe_markdown = iframe_scrape.markdown

            if iframe_markdown is not None:
                merged = merge_coral_into_scrape(fresh, iframe_markdown)
                cached_t1 = await _cache_put_or_keyless(
                    scrape_cache, url, merged, tier="scrape"
                )
                return _Tier1Outcome(
                    cached=cached_t1,
                    terminal=None,
                    escalation_reason=None,
                    tier1_reason="ok",
                    final_classification="ok",
                    platform_signal=signal,
                    platform_outcome="coral_iframe_merged",
                )

            await _cache_put_or_keyless(scrape_cache, url, fresh, tier="scrape")
            return _Tier1Outcome(
                cached=None,
                terminal=None,
                escalation_reason="coral_graphql_failed",
                tier1_reason=f"coral_graphql_failed: {exc}",
                final_classification="ok",
                platform_signal=signal,
                platform_outcome="coral_graphql_failed",
            )

        merged = merge_coral_into_scrape(fresh, comments.comments_markdown)
        cached_t1 = await _cache_put_or_keyless(
            scrape_cache, url, merged, tier="scrape"
        )
        return _Tier1Outcome(
            cached=cached_t1,
            terminal=None,
            escalation_reason=None,
            tier1_reason="ok",
            final_classification="ok",
            platform_signal=signal,
            platform_outcome="coral_merged",
        )
    if quality is ScrapeQuality.AUTH_WALL:
        return _Tier1Outcome(
            cached=None,
            terminal=TerminalError(
                ErrorCode.EXTRACTION_FAILED,
                "login wall on Tier 1 (auth_wall) — not escalated",
            ),
            escalation_reason=None,
            tier1_reason="auth_wall",
            final_classification="auth_wall",
            platform_signal=None,
            platform_outcome=None,
        )
    if quality is ScrapeQuality.LEGITIMATELY_EMPTY:
        return _Tier1Outcome(
            cached=None,
            terminal=TerminalError(
                ErrorCode.EXTRACTION_FAILED,
                "page empty on Tier 1 (legitimately_empty) — not escalated",
            ),
            escalation_reason=None,
            tier1_reason="legitimately_empty",
            final_classification="legitimately_empty",
            platform_signal=None,
            platform_outcome=None,
        )
    # INTERSTITIAL: cache the Tier 1 row so a retry can skip the classifier,
    # then signal escalation.
    assert quality is ScrapeQuality.INTERSTITIAL
    await _cache_put_or_keyless(scrape_cache, url, fresh, tier="scrape")
    return _Tier1Outcome(
        cached=None,
        terminal=None,
        escalation_reason="interstitial",
        tier1_reason="interstitial",
        final_classification="interstitial",
        platform_signal=None,
        platform_outcome=None,
    )


def _classify_cached_tier1(cached: CachedScrape) -> _Tier1Outcome:
    """Re-classify a cached Tier 1 bundle so retries don't trust degraded rows.

    The Tier 1 path caches both OK and INTERSTITIAL bundles under
    `tier='scrape'` so retries skip the upstream Firecrawl probe. Without
    re-classification on cache hit, an INTERSTITIAL row short-circuits the
    ladder and gets returned as if it were OK — bypassing the Tier 2
    escalation that the ladder is meant to provide. The same `_Tier1Outcome`
    shape used by `_run_tier1` lets `_scrape_step` dispatch through one
    code path regardless of cache vs probe origin. (codex P1, PR #426 review.)
    """
    quality = classify_scrape(cached)
    if quality is ScrapeQuality.OK:
        return _Tier1Outcome(
            cached=cached,
            terminal=None,
            escalation_reason=None,
            tier1_reason="ok",
            final_classification="ok",
            platform_signal=None,
            platform_outcome=None,
        )
    if quality is ScrapeQuality.AUTH_WALL:
        return _Tier1Outcome(
            cached=None,
            terminal=TerminalError(
                ErrorCode.EXTRACTION_FAILED,
                "login wall on Tier 1 cache (auth_wall) — not escalated",
            ),
            escalation_reason=None,
            tier1_reason="auth_wall",
            final_classification="auth_wall",
            platform_signal=None,
            platform_outcome=None,
        )
    if quality is ScrapeQuality.LEGITIMATELY_EMPTY:
        return _Tier1Outcome(
            cached=None,
            terminal=TerminalError(
                ErrorCode.EXTRACTION_FAILED,
                "page empty on Tier 1 cache (legitimately_empty) — not escalated",
            ),
            escalation_reason=None,
            tier1_reason="legitimately_empty",
            final_classification="legitimately_empty",
            platform_signal=None,
            platform_outcome=None,
        )
    assert quality is ScrapeQuality.INTERSTITIAL
    return _Tier1Outcome(
        cached=None,
        terminal=None,
        escalation_reason="interstitial",
        tier1_reason="interstitial",
        final_classification="interstitial",
        platform_signal=None,
        platform_outcome=None,
    )


async def _find_successful_cached_scrape(
    url: str,
    scrape_cache: SupabaseScrapeCache,
) -> tuple[ScrapeTier, _Tier1Outcome] | None:
    """Find a successful cached scrape across URL-scoped Firecrawl tiers.

    A timed-out job can already have good page content cached under a richer
    tier. Retrying should reuse that content instead of re-hitting the source.
    Non-OK interact rows are ignored; a non-OK `scrape` row is returned so
    `_scrape_step` preserves the existing Tier 1 terminal/escalation behavior.
    """
    for tier in _SUCCESSFUL_CACHE_REUSE_TIERS:
        cached = await scrape_cache.get(url, tier=tier)
        if cached is None:
            continue
        cached_t1 = _classify_cached_tier1(cached)
        if cached_t1.cached is not None:
            return tier, cached_t1
        if tier == "scrape":
            return tier, cached_t1
    return None


@dataclass
class _Tier2Outcome:
    """Result of running Tier 2. `cached` is set on OK; otherwise
    `tier2_reason` and `final_classification` describe the failure."""

    cached: CachedScrape | None
    tier2_reason: str
    final_classification: str
    coral_action_status: str | None = None


def _platform_action_status_from(scrape: ScrapeResult) -> str | None:
    actions = scrape.actions
    if not actions:
        return None
    prefixes = ("coral_status:", "viafoura_status:")
    javascript_returns = actions.get("javascriptReturns")
    if isinstance(javascript_returns, list):
        for item in reversed(javascript_returns):
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if isinstance(value, str) and value.startswith(prefixes):
                return value.split(":", 1)[1].split(";", 1)[0].strip() or None
    script_outputs = actions.get("scriptOutputs")
    if isinstance(script_outputs, list):
        for output in reversed(script_outputs):
            if isinstance(output, str) and output.startswith(prefixes):
                return output.split(":", 1)[1].split(";", 1)[0].strip() or None
    return None


def _legacy_coral_outcome(platform_outcome: str | None) -> str | None:
    """Map generalized platform outcomes back to legacy Coral span values."""
    match platform_outcome:
        case "coral_render_only":
            return "render_only"
        case "coral_iframe_merged":
            return "iframe_merged"
        case "coral_graphql_failed":
            return "graphql_failed"
        case "coral_merged":
            return "merged"
        case _:
            return None


async def _run_tier2(
    url: str,
    interact_client: FirecrawlClient,
    scrape_cache: SupabaseScrapeCache,
    *,
    platform_signal: PlatformSignal | None = None,
) -> _Tier2Outcome:
    """Tier 2 /interact escalation. Returns an outcome that the caller
    converts into either a return value or `TerminalError(UNSUPPORTED_SITE)`.
    """
    cached_t2 = await scrape_cache.get(url, tier="interact")
    if cached_t2 is not None:
        cached_quality = classify_scrape(cached_t2)
        if cached_quality is ScrapeQuality.OK:
            outcome = _Tier2Outcome(
                cached=cached_t2, tier2_reason="ok", final_classification="ok"
            )
        else:
            outcome = _Tier2Outcome(
                cached=None,
                tier2_reason=cached_quality.value,
                final_classification=cached_quality.value,
            )
    else:
        try:
            fresh = await interact_client.interact(
                url,
                actions=_tier2_actions_for(platform_signal),
                formats=["markdown", "html", "screenshot@fullPage"],
                only_main_content=platform_signal is None,
            )
        except FirecrawlBlocked as exc:
            outcome = _Tier2Outcome(
                cached=None,
                tier2_reason=f"firecrawl_blocked: {exc}",
                final_classification="firecrawl_blocked",
            )
        except FirecrawlError as exc:
            outcome = _Tier2Outcome(
                cached=None,
                tier2_reason=f"firecrawl_error: {exc}",
                final_classification="firecrawl_error",
            )
        except Exception as exc:
            outcome = _Tier2Outcome(
                cached=None,
                tier2_reason=f"unexpected_error: {exc}",
                final_classification="unexpected_error",
            )
        else:
            quality = classify_scrape(fresh)
            if quality is ScrapeQuality.OK:
                cached_after_t2 = await _cache_put_or_keyless(
                    scrape_cache, url, fresh, tier="interact"
                )
                outcome = _Tier2Outcome(
                    cached=cached_after_t2,
                    tier2_reason="ok",
                    final_classification="ok",
                    coral_action_status=_platform_action_status_from(fresh),
                )
            else:
                outcome = _Tier2Outcome(
                    cached=None,
                    tier2_reason=quality.value,
                    final_classification=quality.value,
                )

    return outcome


async def _scrape_step(
    url: str,
    scrape_client: FirecrawlClient,
    interact_client: FirecrawlClient,
    scrape_cache: SupabaseScrapeCache,
    *,
    force_tier: Literal["scrape", "interact"] | None = None,
) -> CachedScrape:
    """Run the tiered scrape ladder for `url` and return a `CachedScrape`.

    Tier 1 (`scrape_client.scrape`, single-attempt budget):
      - Cache hit (tier='scrape') → return.
      - `FirecrawlBlocked` → escalate to Tier 2 (no point classifying a
        refusal envelope; the ladder's whole point is to retry with a
        richer fetcher).
      - Other `FirecrawlError` / generic exception → `TransientError` so
        Cloud Tasks redelivers (transient upstream blips still get the
        envelope-level retry budget at run_job).
      - `OK` classification → cache as 'scrape' and return.
      - `INTERSTITIAL` → cache as 'scrape' (so a retry can skip the cheap
        classifier) and escalate to Tier 2.
      - `AUTH_WALL` → `TerminalError(EXTRACTION_FAILED, "login wall …")`.
        DO NOT escalate — bypassing auth is a hard ToS line.
      - `LEGITIMATELY_EMPTY` → `TerminalError(EXTRACTION_FAILED, "page empty …")`.
        DO NOT escalate — no richer fetch tier resurrects deleted content.

    Tier 2 (`interact_client.interact`, default-retry budget):
      - Cache hit (tier='interact') → return.
      - Refusal / generic error / non-OK classification → `TerminalError(
        UNSUPPORTED_SITE, "tier 1: …; tier 2: …")` with both tier reasons
        in the message.
      - `OK` → cache as 'interact' and return.

    `force_tier` (TASK-1488.06): when set to `'interact'`, Tier 1 is
    skipped entirely — neither the Tier 1 cache nor the Tier 1 probe is
    consulted, and the Tier 2 cache lookup + /interact path runs as if
    Tier 1 had escalated. This is the seam the once-only post-Gemini
    escalation uses when `extract_utterances` raises
    `ZeroUtterancesError` on the first pass: Tier 1 "succeeded" at the
    classifier but Gemini still couldn't parse a single utterance, so
    rerunning Tier 1 would just re-feed the same uninterpretable bundle.
    `force_tier='scrape'` is reserved for symmetry; today no caller uses
    it. `None` (the default) preserves all 1488.05 behavior. A non-OK
    Tier 2 outcome under `force_tier` still raises
    `TerminalError(UNSUPPORTED_SITE)` with `tier 1: skipped (forced)`
    in the reason so operators can tell the bypass fired.

    The whole body is wrapped in a single `logfire.span("vibecheck.scrape_step")`;
    attributes (`tier_attempted`, `tier_success`, `escalation_reason`,
    `final_classification`) are filled in incrementally as the ladder
    progresses so a partial trace still pinpoints where we ended up.
    Forced bypass sets `escalation_reason='zero_utterances'` so the trace
    distinguishes it from the `firecrawl_blocked` / `interstitial` paths.
    """
    tier_attempted: list[str] = []
    tier_success: str | None = None
    escalation_reason: str | None = None
    final_classification: str = "ok"
    platform_detected = False
    platform_outcome: str | None = None
    coral_detected = False
    coral_outcome: str | None = None
    coral_action_status: str | None = None

    span = logfire.span("vibecheck.scrape_step", url=url)
    with span:
        try:
            # ----- Forced Tier 2 bypass (TASK-1488.06) ------------------
            # Skip Tier 1 entirely: no cache read, no /scrape probe. The
            # caller has already decided Tier 1 cannot help (Gemini
            # returned 0 utterances on the first pass). Fall straight
            # through to Tier 2, which still consults its own cache and
            # records its own classification.
            if force_tier == "interact":
                escalation_reason = "zero_utterances"
                tier_attempted.append("interact")
                t2 = await _run_tier2(url, interact_client, scrape_cache)
                final_classification = t2.final_classification
                coral_action_status = t2.coral_action_status
                if t2.cached is not None:
                    tier_success = "interact"
                    return t2.cached
                raise TerminalError(
                    ErrorCode.UNSUPPORTED_SITE,
                    f"tier 1: skipped (forced); tier 2: {t2.tier2_reason}",
                    detail={"error_host": urlparse(url).hostname},
                )

            # Cache hit: scan URL-scoped Firecrawl tiers before probing
            # Firecrawl. Browser HTML submissions are job-scoped and are loaded
            # by `_load_browser_html_scrape`, not by normalized URL.
            cached_hit = await _find_successful_cached_scrape(url, scrape_cache)
            if cached_hit is not None:
                cached_tier, cached_t1 = cached_hit
                tier_attempted.append(cached_tier)
                final_classification = cached_t1.final_classification
                platform_detected = cached_t1.platform_signal is not None
                platform_outcome = cached_t1.platform_outcome
                coral_detected = isinstance(cached_t1.platform_signal, CoralSignal)
                coral_outcome = _legacy_coral_outcome(platform_outcome)
                if cached_t1.cached is not None:
                    tier_success = cached_tier
                    return cached_t1.cached
                if cached_t1.terminal is not None:
                    raise cached_t1.terminal
                # INTERSTITIAL — fall through to Tier 2 escalation using
                # the cached outcome's reason.
                assert cached_t1.escalation_reason is not None
                escalation_reason = cached_t1.escalation_reason
                tier_attempted.append("interact")
                t2_cached = await _run_tier2(
                    url,
                    interact_client,
                    scrape_cache,
                )
                final_classification = t2_cached.final_classification
                coral_action_status = t2_cached.coral_action_status
                if t2_cached.cached is not None:
                    tier_success = "interact"
                    return t2_cached.cached
                raise TerminalError(
                    ErrorCode.UNSUPPORTED_SITE,
                    f"tier 1: {cached_t1.tier1_reason} (cached); "
                    f"tier 2: {t2_cached.tier2_reason}",
                    detail={"error_host": urlparse(url).hostname},
                )

            # Tier 1 probe (cache miss).
            tier_attempted.append("scrape")
            t1 = await _run_tier1(url, scrape_client, scrape_cache)
            final_classification = t1.final_classification
            platform_detected = t1.platform_signal is not None
            platform_outcome = t1.platform_outcome
            coral_detected = isinstance(t1.platform_signal, CoralSignal)
            coral_outcome = _legacy_coral_outcome(platform_outcome)
            if t1.cached is not None:
                tier_success = "scrape"
                return t1.cached
            if t1.terminal is not None:
                # AUTH_WALL or LEGITIMATELY_EMPTY — no escalation.
                raise t1.terminal

            # Tier 2 escalation (refusal or interstitial).
            assert t1.escalation_reason is not None
            escalation_reason = t1.escalation_reason
            tier_attempted.append("interact")
            t2 = await _run_tier2(url, interact_client, scrape_cache, platform_signal=t1.platform_signal)
            final_classification = t2.final_classification
            coral_action_status = t2.coral_action_status
            if t2.cached is not None:
                tier_success = "interact"
                return t2.cached

            # Both tiers failed — UNSUPPORTED_SITE carries both reasons.
            raise TerminalError(
                ErrorCode.UNSUPPORTED_SITE,
                f"tier 1: {t1.tier1_reason}; tier 2: {t2.tier2_reason}",
                detail={"error_host": urlparse(url).hostname},
            )
        finally:
            # Set span attributes incrementally so a partial trace still
            # pinpoints how far we got. Done in finally so terminal /
            # transient paths still record their state.
            span.set_attribute("tier_attempted", list(tier_attempted))
            span.set_attribute("tier_success", tier_success)
            span.set_attribute("escalation_reason", escalation_reason)
            span.set_attribute("final_classification", final_classification)
            span.set_attribute("platform_detected", platform_detected)
            span.set_attribute("platform_outcome", platform_outcome)
            span.set_attribute("coral_detected", coral_detected)
            span.set_attribute("coral_outcome", coral_outcome)
            span.set_attribute("coral_action_status", coral_action_status)


async def _revalidate_final_url(
    scrape: CachedScrape,
    *,
    url: str,
    scrape_cache: SupabaseScrapeCache,
) -> None:
    """Post-scrape SSRF re-check (codex P1-3).

    Firecrawl follows redirects transparently, so `metadata.source_url` may
    point at a host we would never have accepted on the POST. Re-run the
    validator; on rejection, evict the cached scrape so a subsequent retry
    fetches fresh input rather than replaying the poisoned entry, then
    raise TerminalError invalid_url.

    `tier=None` flushes both Tier 1 and Tier 2 rows. The poisoned scrape may
    have been written at `tier="interact"` (Tier 2 escalation), so evicting
    only `tier="scrape"` would leave the SSRF-poisoned row alive for retry —
    a security regression. The cache contract at
    `SupabaseScrapeCache.evict()` documents `tier=None` as the all-tiers
    flush; this call honors that contract.
    """
    final = scrape.metadata.source_url if scrape.metadata else None
    if not final:
        return
    try:
        revalidate_redirect_target(final)
    except InvalidURL:
        try:
            await scrape_cache.evict(url, tier=None)
        except Exception as exc:
            logger.warning(
                "scrape cache evict failed after redirect-block for %s: %s",
                url,
                exc,
            )
        raise TerminalError(
            ErrorCode.INVALID_URL, "redirect to private host"
        )


# ---------------------------------------------------------------------------
# Section fan-out stub.
# ---------------------------------------------------------------------------


async def _run_section(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    slug: SectionSlug,
    payload: Any,
    settings: Settings,
    *,
    test_fail_slug: str | None = None,
) -> SectionState:
    """Run a single analysis slot and persist its output.

    Slugs registered in `_SECTION_HANDLERS` invoke the real analyzer and
    persist its returned payload. The empty-success fallback remains only
    as a defensive shape guard for future slugs during development.

    A slot failure is NOT a job failure: we call `mark_slot_failed` and
    return normally. `maybe_finalize_job` notices the failed slot later
    and waits (or the sweeper does) — terminal assembly happens only
    when every slot is done.

    `test_fail_slug` is the e2e Playwright hook (TASK-1473.35). When it
    matches `slug.value`, the handler is short-circuited and the slot is
    written as failed with a recognizable error string, letting the
    section-retry spec drive a real round-trip.
    """
    slot_attempt = uuid4()
    handler = _SECTION_HANDLERS.get(slug)
    slot_state = SectionState.DONE
    slot_error: str | None = None
    if test_fail_slug is not None and test_fail_slug == slug.value:
        slot_state = SectionState.FAILED
        slot_error = "synthetic test failure (X-Vibecheck-Test-Fail-Slug)"
        data: dict[str, Any] = {}
    elif handler is not None:
        try:
            data = await handler(pool, job_id, task_attempt, payload, settings)
        except Exception as exc:
            logger.exception(
                "section %s handler failed for job %s: %s",
                slug.value, job_id, exc,
            )
            slot_state = SectionState.FAILED
            slot_error = str(exc)
            data = {}
    else:
        data = _empty_section_data(slug)

    if (
        slug == SectionSlug.SAFETY_VIDEO_MODERATION
        and isinstance(data, dict)
        and data.get("status") == "polling"
    ):
        slot_state = SectionState.RUNNING

    # write_slot (not mark_slot_failed) works for the terminal write here
    # because its CAS only checks job.attempt_id — no pre-existing slot row
    # required. mark_slot_failed requires slot.state='running' in the DB,
    # which _run_section never sets (it writes the terminal state directly).
    slot = SectionSlot(
        state=slot_state,
        attempt_id=slot_attempt,
        data=data if slot_state in {SectionState.DONE, SectionState.RUNNING} else None,
        error=slot_error,
    )
    section_tokens = bind_contextvars(slug=slug)
    started = time.monotonic()
    try:
        try:
            rowcount = await write_slot(pool, job_id, task_attempt, slug, slot)
        except Exception as exc:
            logger.exception(
                "section %s failed for job %s: %s", slug.value, job_id, exc
            )
            SECTION_FAILURES.labels(
                slug=slug.value, error_type=classify_error(exc)
            ).inc()
            try:
                failed_rowcount = await mark_slot_failed(
                    pool,
                    job_id,
                    slug,
                    slot_attempt,
                    error=str(exc),
                    expected_task_attempt=task_attempt,
                )
                del failed_rowcount
            except Exception as mark_exc:
                logger.exception(
                    "section %s: mark_slot_failed also failed for job %s: %s",
                    slug.value, job_id, mark_exc,
                )
            raise TransientError(
                f"write_slot failed for job={job_id} slug={slug.value}: {exc}"
            ) from exc
        else:
            if rowcount == 0:
                raise TransientError(
                    f"write_slot CAS returned rowcount=0 for job={job_id} slug={slug.value}"
                )
            if slot_state == SectionState.RUNNING and slug == SectionSlug.SAFETY_VIDEO_MODERATION:
                await enqueue_video_moderation_poll(
                    job_id,
                    task_attempt,
                    slot_attempt,
                    settings,
                    schedule_delay_seconds=30,
                )
        finally:
            SECTION_DURATION.labels(slug=slug.value).observe(
                time.monotonic() - started
            )
    finally:
        clear_contextvars(section_tokens)
    return slot_state


async def _video_moderation_dispatch(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
) -> dict[str, Any]:
    if settings.VIDEO_MODERATION_PROVIDER == "video_intelligence":
        return await run_video_intelligence(pool, job_id, task_attempt, payload, settings)
    return await run_video_moderation(pool, job_id, task_attempt, payload, settings)


_SECTION_HANDLERS: dict[SectionSlug, Any] = {
    SectionSlug.SAFETY_MODERATION: run_safety_moderation,
    SectionSlug.SAFETY_WEB_RISK: run_web_risk,
    SectionSlug.SAFETY_IMAGE_MODERATION: run_image_moderation,
    SectionSlug.SAFETY_VIDEO_MODERATION: _video_moderation_dispatch,
    SectionSlug.TONE_DYNAMICS_FLASHPOINT: run_flashpoint,
    SectionSlug.TONE_DYNAMICS_SCD: run_scd,
    SectionSlug.FACTS_CLAIMS_DEDUP: run_claims_dedup,
    SectionSlug.FACTS_CLAIMS_EVIDENCE: run_claims_evidence,
    SectionSlug.FACTS_CLAIMS_PREMISES: run_claims_premises,
    SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: run_facts_claims_known_misinfo,
    SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: run_sentiment,
    SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: run_subjective,
    SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS: run_trends_oppositions,
    SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS: run_highlights,
}


async def _persist_empty_claim_enrichment_slots(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    slugs: tuple[SectionSlug, ...],
) -> None:
    for slug in slugs:
        slot = SectionSlot(
            state=SectionState.DONE,
            attempt_id=uuid4(),
            data=_empty_section_data(slug),
        )
        try:
            await write_slot(pool, job_id, task_attempt, slug, slot)
        except Exception as exc:
            logger.exception(
                "claim-enrichment empty-default write_slot failed for job %s slug %s: %s",
                job_id,
                slug.value,
                exc,
            )


async def _run_all_sections(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    payload: Any,
    settings: Settings,
    *,
    test_fail_slug: str | None = None,
) -> None:
    """Fan out every section in parallel; enforce claim-evidence dependencies.

    Per-section handler failures are caught inside `_run_section` and
    persisted as a failed slot, so handler exceptions don't surface here.
    Anything that DOES surface — `TransientError` from a CAS-missed slot
    write, a DB pool exhaustion, etc. — must propagate so `run_job` can
    classify it (TransientError → 503 → Cloud Tasks redeliver). Previous
    `return_exceptions=True` discarded these silently and led to jobs
    that 200'd back to Cloud Tasks while leaving slots unwritten
    (TASK-1473.41).
    """
    dedup_dependent_slugs: tuple[SectionSlug, ...] = (
        SectionSlug.FACTS_CLAIMS_EVIDENCE,
        SectionSlug.FACTS_CLAIMS_PREMISES,
        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO,
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
        SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS,
    )
    dedup_dependent_set = set(dedup_dependent_slugs)
    independent_slugs: list[SectionSlug] = [
        slug
        for slug in SectionSlug
        if slug not in dedup_dependent_set
    ]

    initial_tasks = {
        slug: asyncio.create_task(
            _run_section(
                pool,
                job_id,
                task_attempt,
                slug,
                payload,
                settings,
                test_fail_slug=test_fail_slug,
            )
        )
        for slug in independent_slugs
    }
    dedup_state = await initial_tasks[SectionSlug.FACTS_CLAIMS_DEDUP]
    if dedup_state != SectionState.DONE:
        await asyncio.gather(*initial_tasks.values())
        await _persist_empty_claim_enrichment_slots(
            pool, job_id, task_attempt, dedup_dependent_slugs
        )
        return

    dependent_tasks = [
        asyncio.create_task(
            _run_section(
                pool,
                job_id,
                task_attempt,
                slug,
                FIRST_RUN_DEPENDENCY_PAYLOAD,
                settings,
                test_fail_slug=test_fail_slug,
            )
        )
        for slug in dedup_dependent_slugs
        if slug in _SECTION_HANDLERS
    ]

    await asyncio.gather(*initial_tasks.values(), *dependent_tasks)


def _parse_sections(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def _coerce_page_kind(page_kind_raw: str | None) -> PageKind:
    try:
        return PageKind(page_kind_raw) if page_kind_raw else PageKind.OTHER
    except ValueError:
        return PageKind.OTHER


def _headline_and_weather_slot_inputs(
    sections: dict[str, Any],
    unavailable_inputs: list[str],
) -> dict[str, dict[str, Any]]:
    return {
        "moderation_data": _done_slot_data(
            sections, SectionSlug.SAFETY_MODERATION, unavailable_inputs, "moderation"
        ),
        "web_risk_data": _done_slot_data(
            sections, SectionSlug.SAFETY_WEB_RISK, unavailable_inputs, "web_risk"
        ),
        "image_data": _done_slot_data(
            sections,
            SectionSlug.SAFETY_IMAGE_MODERATION,
            unavailable_inputs,
            "image_moderation",
        ),
        "video_data": _done_slot_data(
            sections,
            SectionSlug.SAFETY_VIDEO_MODERATION,
            unavailable_inputs,
            "video_moderation",
        ),
        "flashpoint_data": _done_slot_data(
            sections,
            SectionSlug.TONE_DYNAMICS_FLASHPOINT,
            unavailable_inputs,
            "flashpoint",
        ),
        "scd_data": _done_slot_data(
            sections,
            SectionSlug.TONE_DYNAMICS_SCD,
            unavailable_inputs,
            "scd",
        ),
        "dedup_data": _done_slot_data(
            sections,
            SectionSlug.FACTS_CLAIMS_DEDUP,
            unavailable_inputs,
            "claims_dedup",
        ),
        "known_data": _done_slot_data(
            sections,
            SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO,
            unavailable_inputs,
            "known_misinformation",
        ),
        "sentiment_data": _done_slot_data(
            sections,
            SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT,
            unavailable_inputs,
            "sentiment",
        ),
        "subjective_data": _done_slot_data(
            sections,
            SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE,
            unavailable_inputs,
            "subjective",
        ),
        "trends_data": _done_slot_data(
            sections,
            SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
            unavailable_inputs,
            "trends_oppositions",
        ),
        "highlights_data": _done_slot_data(
            sections,
            SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS,
            unavailable_inputs,
            "highlights",
        ),
    }


def _weather_transcript_excerpt(  # noqa: PLR0912
    claims_data: dict[str, Any],
    subjective_data: dict[str, Any],
    flashpoint_data: dict[str, Any],
    trends_data: dict[str, Any],
    highlights_data: dict[str, Any],
    scd_data: dict[str, Any],
) -> str:
    snippets: list[str] = []

    raw_highlights = highlights_data.get("highlights_report", {}).get("highlights")
    if isinstance(raw_highlights, list):
        for raw in raw_highlights:
            if len(snippets) >= 6:
                break
            if not isinstance(raw, dict):
                continue
            cluster = raw.get("cluster")
            if isinstance(cluster, dict):
                canonical = cluster.get("canonical_text")
                if isinstance(canonical, str) and canonical:
                    snippets.append(canonical)

    if trends_payload := trends_data.get("trends_oppositions_report"):
        raw_trends = trends_payload.get("trends")
        if isinstance(raw_trends, list):
            for trend in raw_trends:
                if len(snippets) >= 6:
                    break
                if isinstance(trend, dict):
                    summary = trend.get("summary")
                    if isinstance(summary, str) and summary:
                        snippets.append(summary)

    if (
        claims_payload := claims_data.get("claims_report")
    ) and isinstance(claims_payload, dict) and isinstance(
        claims_data_entries := claims_payload.get("deduped_claims", []),
        list,
    ):
        for claim in claims_data_entries:
            if len(snippets) >= 6:
                break
            if isinstance(claim, dict):
                text = claim.get("canonical_text")
                if isinstance(text, str) and text:
                    snippets.append(text)

    for subjective_claim in subjective_data.get("subjective_claims", []):
        if len(snippets) >= 6:
            break
        if isinstance(subjective_claim, dict):
            claim_text = subjective_claim.get("claim_text")
            if isinstance(claim_text, str) and claim_text:
                snippets.append(claim_text)

    for match in flashpoint_data.get("flashpoint_matches", []):
        if len(snippets) >= 6:
            break
        if isinstance(match, dict):
            reasoning = match.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                snippets.append(reasoning)

    if isinstance(scd_data, dict):
        scd_summary = scd_data.get("summary")
        if isinstance(scd_summary, str) and scd_summary:
            snippets.append(scd_summary)

    return " ".join(snippets)


def _done_slot_data(
    sections: dict[str, Any],
    slug: SectionSlug,
    unavailable_inputs: list[str],
    unavailable_name: str,
) -> dict[str, Any]:
    raw = sections.get(slug.value)
    if raw is None:
        unavailable_inputs.append(unavailable_name)
        return {}
    slot = SectionSlot.model_validate(raw)
    if slot.state != SectionState.DONE or slot.data is None:
        unavailable_inputs.append(unavailable_name)
        return {}
    return slot.data


def _build_safety_recommendation_inputs(
    sections: dict[str, Any],
) -> SafetyRecommendationInputs:
    unavailable_inputs: list[str] = []
    moderation_data = _done_slot_data(
        sections,
        SectionSlug.SAFETY_MODERATION,
        unavailable_inputs,
        "moderation",
    )
    web_risk_data = _done_slot_data(
        sections,
        SectionSlug.SAFETY_WEB_RISK,
        unavailable_inputs,
        "web_risk",
    )
    image_data = _done_slot_data(
        sections,
        SectionSlug.SAFETY_IMAGE_MODERATION,
        unavailable_inputs,
        "image_moderation",
    )
    video_data = _done_slot_data(
        sections,
        SectionSlug.SAFETY_VIDEO_MODERATION,
        unavailable_inputs,
        "video_moderation",
    )
    return SafetyRecommendationInputs(
        harmful_content_matches=[
            HarmfulContentMatch.model_validate(match)
            for match in moderation_data.get("harmful_content_matches", [])
        ],
        web_risk_findings=[
            WebRiskFinding.model_validate(finding)
            for finding in web_risk_data.get("findings", [])
        ],
        image_moderation_matches=[
            ImageModerationMatch.model_validate(match)
            for match in image_data.get("matches", [])
        ],
        video_moderation_matches=[
            VideoModerationMatch.model_validate(match)
            for match in video_data.get("matches", [])
        ],
        unavailable_inputs=unavailable_inputs,
    )


async def _run_safety_recommendation_step(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    settings: Settings,
) -> None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LOAD_SAFETY_SECTIONS_SQL, job_id, task_attempt)
    if row is None:
        return

    try:
        inputs = _build_safety_recommendation_inputs(_parse_sections(row["sections"]))
        recommendation = await run_safety_recommendation(inputs, settings)
    except Exception:
        logger.exception(
            "safety recommendation step failed for job %s attempt %s",
            job_id,
            task_attempt,
        )
        return

    recommendation_json = json.dumps(recommendation.model_dump(mode="json"))
    async with pool.acquire() as conn:
        await conn.execute(
            _WRITE_SAFETY_RECOMMENDATION_SQL,
            job_id,
            recommendation_json,
            task_attempt,
        )


def _build_headline_summary_inputs(
    sections: dict[str, Any],
    safety_recommendation_raw: Any,
    page_title: str | None,
    page_kind_raw: str | None,
) -> HeadlineSummaryInputs:
    unavailable_inputs: list[str] = []
    slot_inputs = _headline_and_weather_slot_inputs(sections, unavailable_inputs)

    moderation_data = slot_inputs["moderation_data"]
    web_risk_data = slot_inputs["web_risk_data"]
    image_data = slot_inputs["image_data"]
    video_data = slot_inputs["video_data"]
    flashpoint_data = slot_inputs["flashpoint_data"]
    scd_data = slot_inputs["scd_data"]
    dedup_data = slot_inputs["dedup_data"]
    known_data = slot_inputs["known_data"]
    sentiment_data = slot_inputs["sentiment_data"]
    subjective_data = slot_inputs["subjective_data"]
    trends_data = slot_inputs["trends_data"]
    highlights_data = slot_inputs["highlights_data"]

    safety_recommendation: SafetyRecommendation | None = None
    if safety_recommendation_raw is not None:
        raw_payload = (
            json.loads(safety_recommendation_raw)
            if isinstance(safety_recommendation_raw, str)
            else safety_recommendation_raw
        )
        safety_recommendation = SafetyRecommendation.model_validate(raw_payload)
    else:
        unavailable_inputs.append("safety_recommendation")

    scd_report = (
        SCDReport.model_validate(scd_data["scd"])
        if scd_data and "scd" in scd_data
        else None
    )
    claims_report = (
        ClaimsReport.model_validate(dedup_data["claims_report"])
        if dedup_data and "claims_report" in dedup_data
        else None
    )
    sentiment_stats = (
        SentimentStatsReport.model_validate(sentiment_data["sentiment_stats"])
        if sentiment_data and "sentiment_stats" in sentiment_data
        else None
    )
    trends_oppositions = (
        TrendsOppositionsReport.model_validate(
            trends_data["trends_oppositions_report"]
        )
        if trends_data and "trends_oppositions_report" in trends_data
        else None
    )
    highlights = (
        OpinionsHighlightsReport.model_validate(highlights_data["highlights_report"])
        if highlights_data and "highlights_report" in highlights_data
        else None
    )

    page_kind = _coerce_page_kind(page_kind_raw)

    return HeadlineSummaryInputs(
        safety_recommendation=safety_recommendation,
        harmful_content_matches=[
            HarmfulContentMatch.model_validate(match)
            for match in moderation_data.get("harmful_content_matches", [])
        ],
        web_risk_findings=[
            WebRiskFinding.model_validate(finding)
            for finding in web_risk_data.get("findings", [])
        ],
        image_moderation_matches=[
            ImageModerationMatch.model_validate(match)
            for match in image_data.get("matches", [])
        ],
        video_moderation_matches=[
            VideoModerationMatch.model_validate(match)
            for match in video_data.get("matches", [])
        ],
        flashpoint_matches=[
            FlashpointMatch.model_validate(match)
            for match in flashpoint_data.get("flashpoint_matches", [])
        ],
        scd=scd_report,
        claims_report=claims_report,
        known_misinformation=[
            FactCheckMatch.model_validate(match)
            for match in known_data.get("known_misinformation", [])
        ],
        sentiment_stats=sentiment_stats,
        subjective_claims=[
            SubjectiveClaim.model_validate(claim)
            for claim in subjective_data.get("subjective_claims", [])
        ],
        trends_oppositions=trends_oppositions,
        highlights=highlights,
        page_title=page_title,
        page_kind=page_kind,
        unavailable_inputs=unavailable_inputs,
    )


def _build_weather_report_inputs(
    sections: dict[str, Any],
    page_title: str | None,
    page_kind_raw: str | None,
) -> WeatherInputs:
    unavailable_inputs: list[str] = []
    slot_inputs = _headline_and_weather_slot_inputs(sections, unavailable_inputs)

    flashpoint_data = slot_inputs["flashpoint_data"]
    scd_data = slot_inputs["scd_data"]
    dedup_data = slot_inputs["dedup_data"]
    trends_data = slot_inputs["trends_data"]
    highlights_data = slot_inputs["highlights_data"]
    sentiment_data = slot_inputs["sentiment_data"]
    subjective_data = slot_inputs["subjective_data"]

    scd_report = (
        SCDReport.model_validate(scd_data["scd"])
        if scd_data and "scd" in scd_data
        else None
    )
    claims_report = (
        ClaimsReport.model_validate(dedup_data["claims_report"])
        if dedup_data and "claims_report" in dedup_data
        else None
    )
    sentiment_stats = (
        SentimentStatsReport.model_validate(sentiment_data["sentiment_stats"])
        if sentiment_data and "sentiment_stats" in sentiment_data
        else None
    )
    trends_oppositions = (
        TrendsOppositionsReport.model_validate(
            trends_data["trends_oppositions_report"]
        )
        if trends_data and "trends_oppositions_report" in trends_data
        else None
    )
    highlights = (
        OpinionsHighlightsReport.model_validate(highlights_data["highlights_report"])
        if highlights_data and "highlights_report" in highlights_data
        else None
    )

    transcript_excerpt = _weather_transcript_excerpt(
        dedup_data,
        subjective_data,
        flashpoint_data,
        trends_data,
        highlights_data,
        scd_data,
    )

    return WeatherInputs(
        page_title=page_title,
        page_kind=_coerce_page_kind(page_kind_raw),
        transcript_excerpt=transcript_excerpt,
        claims_report=claims_report,
        highlights=highlights,
        trends_oppositions=trends_oppositions,
        sentiment_stats=sentiment_stats,
        subjective_claims=[
            SubjectiveClaim.model_validate(claim)
            for claim in subjective_data.get("subjective_claims", [])
        ],
        flashpoint_matches=[
            FlashpointMatch.model_validate(match)
            for match in flashpoint_data.get("flashpoint_matches", [])
        ],
        scd=scd_report,
        unavailable_inputs=unavailable_inputs,
    )


async def _run_weather_report_step(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    settings: Settings,
) -> None:
    """Synthesize the weather report and persist it to vibecheck_jobs.

    Like headline summary, this is best-effort: agent failure logs and
    returns without raising so a bad weather synthesis never fails the
    job — finalize will continue with `weather_report = null`.
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(_LOAD_HEADLINE_INPUTS_SQL, job_id, task_attempt)
        if row is None:
            return

        inputs = _build_weather_report_inputs(
            _parse_sections(row["sections"]),
            row["page_title"],
            row["page_kind"],
        )
        report = await evaluate_weather(
            inputs,
            settings,
            job_id=job_id,
        )
        report_json = json.dumps(report.model_dump(mode="json"))
        async with pool.acquire() as conn:
            await conn.execute(
                _WRITE_WEATHER_REPORT_SQL,
                job_id,
                report_json,
                task_attempt,
            )
    except Exception:
        logger.exception(
            "weather report step failed for job %s attempt %s",
            job_id,
            task_attempt,
        )
        return


async def _run_headline_weather_steps(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    settings: Settings,
    *,
    stage_prefix: str,
    slug: SectionSlug | None = None,
) -> None:
    """Run headline + weather synthesis in parallel and update stages.

    Both steps are best-effort (see their individual implementations). This
    helper keeps the post-Gemini and section-retry orchestration shapes
    consistent and avoids duplicated span wiring.
    """

    async def _run_headline_stage() -> None:
        if slug is None:
            with logfire.span(
                f"{stage_prefix}.headline_summary",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_HEADLINE_SUMMARY
                )
                await _run_headline_summary_step(
                    pool, job_id, task_attempt, settings
                )
        else:
            with logfire.span(
                f"{stage_prefix}.headline_summary",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
                slug=slug.value,
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_HEADLINE_SUMMARY
                )
                await _run_headline_summary_step(
                    pool, job_id, task_attempt, settings
                )

    async def _run_weather_stage() -> None:
        if slug is None:
            with logfire.span(
                f"{stage_prefix}.weather_report",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_WEATHER_REPORT
                )
                await _run_weather_report_step(pool, job_id, task_attempt, settings)
        else:
            with logfire.span(
                f"{stage_prefix}.weather_report",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
                slug=slug.value,
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_WEATHER_REPORT
                )
                await _run_weather_report_step(pool, job_id, task_attempt, settings)

    await asyncio.gather(_run_headline_stage(), _run_weather_stage())


async def _run_headline_summary_step(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    settings: Settings,
) -> None:
    """Synthesize the headline summary and persist it to vibecheck_jobs.

    Mirrors `_run_safety_recommendation_step`: load section data with an
    attempt-id guard, call the agent, write the result with another
    attempt-id guard. Agent failure logs and returns without raising so a
    bad summarization never fails the job — finalize will assemble
    SidebarPayload with `headline=None` and the UI degrades gracefully.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LOAD_HEADLINE_INPUTS_SQL, job_id, task_attempt)
    if row is None:
        return

    try:
        inputs = _build_headline_summary_inputs(
            _parse_sections(row["sections"]),
            row["safety_recommendation"],
            row["page_title"],
            row["page_kind"],
        )
        headline = await run_headline_summary(inputs, settings, job_id)
    except Exception:
        logger.exception(
            "headline summary step failed for job %s attempt %s",
            job_id,
            task_attempt,
        )
        return

    headline_json = json.dumps(headline.model_dump(mode="json"))
    async with pool.acquire() as conn:
        await conn.execute(
            _WRITE_HEADLINE_SUMMARY_SQL,
            job_id,
            headline_json,
            task_attempt,
        )


# ---------------------------------------------------------------------------
# Pipeline body.
# ---------------------------------------------------------------------------


async def _run_pipeline(  # noqa: PLR0912
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    url: str,
    settings: Settings,
    *,
    source_type: str = "url",
    test_fail_slug: str | None = None,
) -> None:
    """The scrape->extract->analyze sequence, error-classified.

    Isolated from the top-level `run_job` so unit tests can substitute an
    `AsyncMock` on this function to exercise the handler's error-handling
    without booting Firecrawl/Gemini/OpenAI.
    """
    scrape_cache = _build_scrape_cache(settings)
    # Tier 2 / extract default-retry client; Tier 1 fail-fast probe client.
    # Both are seams tests can monkeypatch independently; the default-retry
    # client is shared with `extract_utterances` below so the extractor's
    # /v2/extract calls keep their existing retry budget.
    client = _build_firecrawl_client(settings)
    tier1_client = _build_firecrawl_tier1_client(settings)

    # Scrape (cache or fresh) via the tiered ladder, then extract.
    #
    # Once-only post-Gemini escalation (TASK-1488.06): if the first
    # extract_utterances call raises `ZeroUtterancesError`, Gemini saw
    # no parseable utterances despite the pre-Gemini quality classifier
    # passing — re-fetch via Tier 2 and try the extractor once more. The
    # `escalated` boolean below is the explicit once-only guard: a second
    # `ZeroUtterancesError` raises `TerminalError(EXTRACTION_FAILED)`
    # without re-entering the loop. No recursion, no while-loop.
    escalated = False

    async def _scrape_and_extract(
        *, force_tier: Literal["scrape", "interact"] | None,
    ) -> UtterancesPayload:
        """Run a single scrape→revalidate→extract cycle. Lets the
        once-only escalation re-use the same plumbing for both passes —
        the only difference is the `force_tier` argument threaded into
        `_scrape_step`.
        """
        if source_type == "pdf":
            if force_tier is not None:
                raise PDFExtractionError(
                    "PDF extraction does not support tier escalation"
                )
            return await pdf_extract_step(
                pool,
                job_id,
                url,
                settings=settings,
                client=client,
                scrape_cache=scrape_cache,
            )

        if source_type == "browser_html":
            scrape = await _load_browser_html_scrape(pool, job_id)
            if scrape is None:
                raise TerminalError(
                    ErrorCode.EXTRACTION_FAILED,
                    "browser-submitted HTML cache row missing",
                    detail={"error_host": urlparse(url).hostname},
                )
        else:
            try:
                scrape = await _scrape_step(
                    url, tier1_client, client, scrape_cache, force_tier=force_tier
                )
            except (TransientError, TerminalError):
                raise
            except Exception as exc:
                raise TransientError(f"scrape step failed: {exc}") from exc

        # Post-scrape revalidate: reject redirects into private space.
        await _revalidate_final_url(scrape, url=url, scrape_cache=scrape_cache)

        # Thread the bundle we just resolved through the ladder into the
        # extractor so a Tier 2 escalation actually reaches Gemini. Without
        # this, `extract_utterances._get_or_scrape` would re-read
        # `tier="scrape"` from cache and overwrite the Tier 2 bundle with the
        # cached Tier 1 INTERSTITIAL — silently defeating force_tier.
        return await extract_utterances(
            url, client, scrape_cache, settings=settings, scrape=scrape
        )

    async def _classify_transient_or_raise(
        exc: TransientExtractionError,
    ) -> NoReturn:
        """Run the in-row backstop counter logic for a transient extraction
        error. Either raises TerminalError(UPSTREAM_ERROR) when the counter
        exhausts, or TransientError so Cloud Tasks redelivers.

        Unexpected failures inside the increment helper convert to a
        TerminalError(EXTRACTION_FAILED) so the row flips to failed and the
        SQL bug becomes visible to operators instead of looping forever.
        """
        try:
            new_count = await _increment_extract_transient_attempts(
                pool, job_id, task_attempt=task_attempt
            )
        except Exception as inc_exc:
            raise TerminalError(
                ErrorCode.EXTRACTION_FAILED,
                f"backstop counter increment failed: {inc_exc}; flipping "
                f"terminal to prevent silent Cloud Tasks exhaustion",
            ) from inc_exc
        if (
            new_count is not None
            and new_count >= EXTRACT_TRANSIENT_MAX_ATTEMPTS
        ):
            raise TerminalError(
                ErrorCode.UPSTREAM_ERROR,
                f"upstream extraction error after {new_count} transient "
                f"attempts: provider={exc.provider} "
                f"status_code={exc.status_code} status={exc.status}: {exc}",
                detail={
                    "provider": exc.provider,
                    "status_code": exc.status_code,
                    "status": exc.status,
                    "transient_attempts": new_count,
                },
            ) from exc
        raise TransientError(
            f"transient extraction error "
            f"(attempt {new_count}, provider={exc.provider}, "
            f"status_code={exc.status_code}): {exc}"
        ) from exc

    # Extract utterances from the scrape bundle. Four-arm classification:
    # (1) TransientExtractionError: upstream flake (Vertex 504/503/429 or
    #     Firecrawl 5xx). Bump in-row backstop counter; on exhaustion
    #     escalate to TerminalError(UPSTREAM_ERROR) so the row flips to
    #     failed BEFORE Cloud Tasks silently exhausts at max_attempts=3.
    # (2) UtteranceExtractionError: parse / output-validation. Terminal.
    # (3) ZeroUtterancesError: pre-Gemini quality classifier said OK but
    #     Gemini still saw nothing. Once-only Tier 2 escalation.
    # (4) Anything else: defensive catch-all, terminal so we don't loop
    #     forever on unknown bugs.
    try:
        payload = await _scrape_and_extract(force_tier=None)
    except PDFExtractionError as exc:
        raise TerminalError(
            ErrorCode.PDF_EXTRACTION_FAILED, f"pdf extraction failed: {exc}"
        ) from exc
    except TransientExtractionError as exc:
        await _classify_transient_or_raise(exc)
    except UtteranceExtractionError as exc:
        logger.warning(
            "vibecheck.extraction_failed",
            extra={"url": url, "job_id": job_id},
            exc_info=True,
        )
        raise TerminalError(
            ErrorCode.EXTRACTION_FAILED, f"extraction failed: {exc}"
        ) from exc
    except ZeroUtterancesError:
        # First pass: Gemini couldn't extract from the Tier 1 bundle.
        # Escalate by forcing Tier 2 once. Toggle the boolean BEFORE the
        # second attempt so a second-pass success path can't accidentally
        # leave the guard armed.
        escalated = True
        try:
            payload = await _scrape_and_extract(force_tier="interact")
        except TransientExtractionError as exc:
            await _classify_transient_or_raise(exc)
        except UtteranceExtractionError as exc:
            logger.warning(
                "vibecheck.extraction_failed",
                extra={"url": url, "job_id": job_id},
                exc_info=True,
            )
            raise TerminalError(
                ErrorCode.EXTRACTION_FAILED, f"extraction failed: {exc}"
            ) from exc
        except ZeroUtterancesError as exc:
            # Second pass also empty — terminal. Once-only is enforced
            # by the absence of any third branch here; the boolean
            # `escalated` makes the policy explicit even though no
            # third try could fire from this control flow.
            assert escalated  # documents the once-only invariant
            raise TerminalError(
                ErrorCode.EXTRACTION_FAILED,
                "0 utterances after /interact",
            ) from exc
        except (TransientError, TerminalError):
            raise
        except Exception as exc:
            logger.warning(
                "vibecheck.extraction_failed",
                extra={"url": url, "job_id": job_id},
                exc_info=True,
            )
            raise TerminalError(
                ErrorCode.EXTRACTION_FAILED, f"extraction failed: {exc}"
            ) from exc
    except (TransientError, TerminalError):
        raise
    except Exception as exc:
        # Defensive catch-all: anything not yet classified by the typed
        # arms still terminates so we don't loop forever on unknown bugs.
        logger.warning(
            "vibecheck.extraction_failed",
            extra={"url": url, "job_id": job_id},
            exc_info=True,
        )
        raise TerminalError(
            ErrorCode.EXTRACTION_FAILED, f"extraction failed: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # Post-Gemini path (TASK-1474.23.02 instrumentation).
    #
    # Three confirmed silent worker deaths (jobs 541d61e9, 5841a264,
    # 4374881d) all died somewhere between this point and the next
    # observable side-effect, leaving zero log lines and no breadcrumb.
    # Each step below is wrapped in:
    #   1. A named Logfire span so any partial trace exported to the
    #      vibecheck Logfire project pinpoints the dying stage.
    #   2. A `last_stage` DB write that survives even a SIGKILL — a direct
    #      query on `vibecheck_jobs` yields the breadcrumb when no log
    #      line ever made it out.
    # The whole block is guarded by a top-level except that re-raises but
    # logs with traceback first, defeating any downstream catch-all that
    # would otherwise swallow the stack trace before it hits Logfire.
    # ------------------------------------------------------------------
    try:
        with logfire.span(
            "vibecheck.with_utterances",
            job_id=str(job_id),
            attempt_id=str(task_attempt),
        ):
            with logfire.span(
                "vibecheck.with_utterances.persist_utterances",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_PERSIST_UTTERANCES
                )
                try:
                    await persist_utterances(
                        pool, job_id, task_attempt, payload
                    )
                except UtterancePersistenceSuperseded as exc:
                    logger.info(
                        "pipeline: utterance persistence superseded for job %s: %s",
                        job_id, exc,
                    )
                    raise HandlerSuperseded() from exc

            with logfire.span(
                "vibecheck.with_utterances.set_analyzing",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_SET_ANALYZING
                )
                # Flip status to analyzing before fan-out so the poll
                # endpoint returns the right cadence hint.
                await _set_analyzing(pool, job_id, task_attempt)

            with logfire.span(
                "vibecheck.with_utterances.run_sections",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_RUN_SECTIONS
                )
                # Fan out per-section analysis. Slot-level failures are
                # written by `_run_section` itself; this await only
                # raises on orchestrator infrastructure errors.
                await _run_all_sections(
                    pool, job_id, task_attempt, payload, settings,
                    test_fail_slug=test_fail_slug,
                )

            with logfire.span(
                "vibecheck.with_utterances.safety_recommendation",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_SAFETY_RECOMMENDATION
                )
                await _run_safety_recommendation_step(
                    pool, job_id, task_attempt, settings
                )

            await _run_headline_weather_steps(
                pool, job_id, task_attempt, settings, stage_prefix="vibecheck.with_utterances"
            )

            with logfire.span(
                "vibecheck.with_utterances.finalize",
                job_id=str(job_id),
                attempt_id=str(task_attempt),
            ):
                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_FINALIZE
                )
                # Finalize: UPSERT the sidebar_payload cache if every slot
                # is done. When finalize returns False the job is
                # intentionally NOT cached yet (e.g. a slot is still in
                # pending/running, attempt_id rotated, or the job already
                # moved to a terminal status owned by the error path).
                finalized = await maybe_finalize_job(
                    pool, job_id, expected_task_attempt=task_attempt
                )
                if not finalized:
                    logger.info(
                        "maybe_finalize_job returned False after _run_all_sections "
                        "for job %s (attempt %s) — slots not yet all done or attempt "
                        "was rotated",
                        job_id,
                        task_attempt,
                    )
    except (TransientError, TerminalError, HandlerSuperseded):
        # Classified errors carry their own logging / outer-handler
        # behavior; let them flow through unchanged.
        raise
    except Exception:
        # Defensive top-level capture for the post-Gemini path. Logging
        # here (rather than only at run_job's outer except) guarantees a
        # traceback even if some downstream catch-all between this scope
        # and run_job's handler swallows the exception. AC2 of
        # TASK-1474.23.02.
        logger.exception(
            "post-gemini handler crashed for job %s attempt %s",
            job_id,
            task_attempt,
        )
        raise


# ---------------------------------------------------------------------------
# Top-level entrypoint.
# ---------------------------------------------------------------------------


async def run_job(
    pool: Any,
    job_id: UUID,
    expected_attempt_id: UUID,
    settings: Settings,
) -> RunResult:
    """Drive one Cloud Tasks delivery through the pipeline.

    Returns a `RunResult` with the HTTP status the caller should emit:
    200 on success, stale-claim (no-op), or TerminalError (failed),
    503 on TransientError or any unclassified Exception.

    The heartbeat task is spawned after the claim and cancelled in
    `finally` so no background work outlives the handler's response.
    """
    claim = await _claim_job(pool, job_id, expected_attempt_id)
    if claim is None:
        # Stale redelivery — the job has already been picked up by a
        # fresher attempt, or the status moved on. 200 so Cloud Tasks
        # doesn't retry.
        CLOUD_TASKS_REDELIVERIES.inc()
        job_tokens = bind_contextvars(
            job_id=job_id, attempt_id=expected_attempt_id
        )
        try:
            logger.info(
                "worker: stale claim for job %s expected_attempt=%s — no-op",
                job_id,
                expected_attempt_id,
            )
        finally:
            clear_contextvars(job_tokens)
        return RunResult(status_code=200)

    task_attempt, url, source_type, test_fail_slug = claim
    job_tokens = bind_contextvars(job_id=job_id, attempt_id=task_attempt)
    heartbeat = asyncio.create_task(
        _heartbeat_loop(
            pool, job_id, task_attempt, interval_sec=HEARTBEAT_INTERVAL_SEC
        )
    )
    ACTIVE_JOBS.inc()
    started = time.monotonic()
    terminal_status = "done"

    try:
        try:
            await _run_pipeline(
                pool, job_id, task_attempt, url, settings,
                source_type=source_type,
                test_fail_slug=test_fail_slug,
            )
        except TransientError as exc:
            terminal_status = "pending"
            logger.warning(
                "worker: transient failure for job %s: %s", job_id, exc
            )
            await _reset_for_retry(
                pool,
                job_id,
                task_attempt=task_attempt,
                expected_attempt_id=expected_attempt_id,
            )
            return RunResult(status_code=503)
        except TerminalError as exc:
            terminal_status = "failed"
            logger.warning(
                "worker: terminal failure for job %s: error_code=%s detail=%s",
                job_id,
                exc.error_code.value,
                exc.error_detail,
                exc_info=True,
            )
            error_host_raw = exc.detail.get("error_host")
            error_host = (
                error_host_raw if isinstance(error_host_raw, str) else None
            )
            await _mark_failed(
                pool,
                job_id,
                task_attempt=task_attempt,
                error_code=exc.error_code,
                error_message=exc.error_detail,
                error_host=error_host,
            )
            return RunResult(status_code=200)
        except HandlerSuperseded:
            # A mid-pipeline step detected the attempt rotated; nothing
            # else to do — the newer worker owns the row.
            terminal_status = "superseded"
            logger.info("worker: handler superseded for job %s", job_id)
            return RunResult(status_code=200)
        except Exception:
            # Unclassified — log with traceback so operators can see the
            # underlying bug, but treat as transient (reset + 503).
            terminal_status = "pending"
            logger.log(
                logging.ERROR,
                "worker: unclassified failure for job %s",
                job_id,
                exc_info=True,
            )
            await _reset_for_retry(
                pool,
                job_id,
                task_attempt=task_attempt,
                expected_attempt_id=expected_attempt_id,
            )
            return RunResult(status_code=503)

        return RunResult(status_code=200)
    finally:
        ACTIVE_JOBS.dec()
        JOB_DURATION.labels(status=terminal_status).observe(
            time.monotonic() - started
        )
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("heartbeat cancellation raised: %s", exc)
        clear_contextvars(job_tokens)


# ---------------------------------------------------------------------------
# Section-retry entrypoint (TASK-1473.13).
# ---------------------------------------------------------------------------


_LOAD_JOB_ATTEMPT_SQL = """
SELECT attempt_id, sections -> $2::text AS slot
FROM vibecheck_jobs
WHERE job_id = $1
"""

_RECORD_TRENDS_DEPENDENCY_WAIT_SQL = """
UPDATE vibecheck_jobs
SET sections = sections || jsonb_build_object($3::text, $5::jsonb),
    updated_at = now()
WHERE job_id = $1
  AND attempt_id = $2
  AND sections ? $3::text
  AND sections -> $3::text ->> 'attempt_id' = $4::text
  AND sections -> $3::text ->> 'state' = 'running'
"""


def _update_rowcount(result: Any) -> int:
    if isinstance(result, str) and result.startswith("UPDATE"):
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
    return 0


async def _load_job_attempt_and_slot(
    pool: Any,
    job_id: UUID,
    slug: SectionSlug,
) -> tuple[UUID, dict[str, Any]] | None:
    """Read the job's current `attempt_id` and the target slot JSON.

    Returns None when the job row is missing or the slot isn't present —
    the caller treats that as a stale redelivery and returns 200 no-op.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LOAD_JOB_ATTEMPT_SQL, job_id, slug.value)
    if row is None:
        return None
    slot_raw = row["slot"]
    if slot_raw is None:
        return None
    import json as _json  # noqa: PLC0415

    slot = (
        _json.loads(slot_raw)
        if isinstance(slot_raw, str)
        else dict(slot_raw)
    )
    if not isinstance(row["attempt_id"], UUID):
        return None
    return row["attempt_id"], slot


def _trends_dependency_wait_task_name(
    expected_slot_attempt_id: UUID,
    wait_iteration: int,
) -> str:
    return f"vibecheck-retry-trends-deps-{expected_slot_attempt_id}-wait-{wait_iteration}"


def _next_trends_dependency_wait_iteration(slot: dict[str, Any]) -> int:
    slot_data = slot.get("data")
    if not isinstance(slot_data, dict):
        return 1
    raw_iteration = slot_data.get(_TRENDS_DEPENDENCY_WAIT_ITERATION_KEY)
    if not isinstance(raw_iteration, int):
        return 1
    return max(raw_iteration, 0) + 1


def _slot_with_trends_dependency_wait_iteration(
    slot: dict[str, Any],
    expected_slot_attempt_id: UUID,
    wait_iteration: int,
) -> SectionSlot:
    try:
        parsed_slot = SectionSlot.model_validate(slot)
    except Exception:
        parsed_slot = SectionSlot(
            state=SectionState.RUNNING,
            attempt_id=expected_slot_attempt_id,
        )
    data = dict(parsed_slot.data or {})
    data[_TRENDS_DEPENDENCY_WAIT_ITERATION_KEY] = wait_iteration
    return SectionSlot(
        state=SectionState.RUNNING,
        attempt_id=expected_slot_attempt_id,
        data=data,
        started_at=parsed_slot.started_at,
    )


async def _record_trends_dependency_wait_slot(
    pool: Any,
    job_id: UUID,
    task_attempt: UUID,
    slug: SectionSlug,
    expected_slot_attempt_id: UUID,
    slot: SectionSlot,
) -> int:
    async with pool.acquire() as conn:
        result = await conn.execute(
            _RECORD_TRENDS_DEPENDENCY_WAIT_SQL,
            job_id,
            task_attempt,
            slug.value,
            str(expected_slot_attempt_id),
            json.dumps(slot.model_dump(mode="json")),
        )
    return _update_rowcount(result)


async def run_section_retry(  # noqa: PLR0911, PLR0912
    pool: Any,
    job_id: UUID,
    slug: SectionSlug,
    expected_slot_attempt_id: UUID,
    settings: Settings,
) -> RunResult:
    """Drive one section-retry Cloud Tasks delivery.

    Semantics:
      1. Load `(job.attempt_id, slot)`. Missing job or missing slot → 200
         idempotent no-op (a prune or re-submit happened after enqueue).
      2. If the slot's current attempt_id no longer matches
         `expected_slot_attempt_id`, or the slot is no longer `running`,
         a newer retry already claimed the slot. Return 200 no-op.
      3. Run the per-slug analysis. Registered handlers reload any persisted
         inputs they need from `vibecheck_job_utterances`.
      4. `mark_slot_done` with `expected_task_attempt=job.attempt_id`.
         If the CAS fails (stale job attempt, or job moved terminal out
         from under us), we return 200 no-op — the newer owner will
         handle finalization.
      5. `maybe_finalize_job(expected_task_attempt=job.attempt_id)`. If
         every slot is now `done`, the sidebar_payload cache is UPSERTed.
      6. Unclassified exceptions are treated as transient: write a failed
         slot (best-effort) and return 503 so Cloud Tasks retries.
    """
    retry_tokens = bind_contextvars(job_id=job_id, slug=slug)
    try:
        loaded = await _load_job_attempt_and_slot(pool, job_id, slug)
        if loaded is None:
            CLOUD_TASKS_REDELIVERIES.inc()
            logger.info(
                "section-retry: job or slot missing for job=%s slug=%s — no-op",
                job_id,
                slug.value,
            )
            return RunResult(status_code=200)
        task_attempt, slot = loaded
        attempt_tokens = bind_contextvars(attempt_id=task_attempt)

        try:
            slot_state = slot.get("state")
            slot_attempt_str = str(slot.get("attempt_id") or "")
            if slot_state != "running" or slot_attempt_str != str(expected_slot_attempt_id):
                CLOUD_TASKS_REDELIVERIES.inc()
                logger.info(
                    "section-retry: stale slot for job=%s slug=%s expected=%s "
                    "current=%s state=%s — no-op",
                    job_id,
                    slug.value,
                    expected_slot_attempt_id,
                    slot_attempt_str,
                    slot_state,
                )
                return RunResult(status_code=200)

            # TASK-1474.27: doubled per-section timeouts (e.g. video sampler
            # 60s download + 30s extract per video, x N videos) push a single
            # section retry well past the sweeper's 30s heartbeat window.
            # Mirror run_job's heartbeat lifecycle so the retry cannot be
            # marked stale mid-flight.
            heartbeat = asyncio.create_task(
                _heartbeat_loop(
                    pool,
                    job_id,
                    task_attempt,
                    interval_sec=HEARTBEAT_INTERVAL_SEC,
                )
            )
            section_started = time.monotonic()
            try:
                handler = _SECTION_HANDLERS.get(slug)
                if handler is None:
                    data = _empty_section_data(slug)
                else:
                    data = await handler(pool, job_id, task_attempt, None, settings)
                rows = await mark_slot_done(
                    pool,
                    job_id,
                    slug,
                    expected_slot_attempt_id,
                    data,
                    expected_task_attempt=task_attempt,
                )
                if rows == 0:
                    CLOUD_TASKS_REDELIVERIES.inc()
                    logger.info(
                        "section-retry: mark_slot_done CAS failed for job=%s slug=%s — no-op",
                        job_id,
                        slug.value,
                    )
                    return RunResult(status_code=200)

                if slug == SectionSlug.FACTS_CLAIMS_DEDUP:
                    for dependent_slug in (
                        SectionSlug.FACTS_CLAIMS_EVIDENCE,
                        SectionSlug.FACTS_CLAIMS_PREMISES,
                        SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO,
                        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS,
                        SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS,
                    ):
                        await _run_section(
                            pool,
                            job_id,
                            task_attempt,
                            dependent_slug,
                            None,
                            settings,
                        )

                with logfire.span(
                    "vibecheck.section_retry.safety_recommendation",
                    job_id=str(job_id),
                    attempt_id=str(task_attempt),
                    slug=slug.value,
                ):
                    await _set_last_stage(
                        pool, job_id, task_attempt, _STAGE_SAFETY_RECOMMENDATION
                    )
                    await _run_safety_recommendation_step(
                        pool, job_id, task_attempt, settings
                    )

                await _run_headline_weather_steps(
                    pool,
                    job_id,
                    task_attempt,
                    settings,
                    stage_prefix="vibecheck.section_retry",
                    slug=slug,
                )

                await _set_last_stage(
                    pool, job_id, task_attempt, _STAGE_FINALIZE
                )
                await maybe_finalize_job(
                    pool, job_id, expected_task_attempt=task_attempt
                )
                return RunResult(status_code=200)
            except Exception as exc:
                if isinstance(exc, TrendsDependenciesNotReadyError):
                    logger.info(
                        "section-retry: trends dependencies not ready for job=%s slug=%s — "
                        "rescheduling dependency retry",
                        job_id,
                        slug.value,
                    )
                    try:
                        wait_iteration = _next_trends_dependency_wait_iteration(slot)
                        wait_slot = _slot_with_trends_dependency_wait_iteration(
                            slot,
                            expected_slot_attempt_id,
                            wait_iteration,
                        )
                        rows = await _record_trends_dependency_wait_slot(
                            pool,
                            job_id,
                            task_attempt,
                            slug,
                            expected_slot_attempt_id,
                            wait_slot,
                        )
                        if rows == 0:
                            CLOUD_TASKS_REDELIVERIES.inc()
                            logger.info(
                                "section-retry: dependency wait CAS failed for job=%s slug=%s — no-op",
                                job_id,
                                slug.value,
                            )
                            return RunResult(status_code=200)
                        await enqueue_section_retry(
                            job_id,
                            slug,
                            expected_slot_attempt_id,
                            settings,
                            task_name=_trends_dependency_wait_task_name(
                                expected_slot_attempt_id,
                                wait_iteration,
                            ),
                            use_deterministic_task_name=True,
                            schedule_delay_seconds=_SECTION_RETRY_DEPENDENCY_BACKOFF_SECONDS,
                        )
                    except Exception as reenqueue_exc:
                        logger.warning(
                            "section-retry: failed to re-enqueue dependency wait for job=%s slug=%s: %s",
                            job_id,
                            slug.value,
                            reenqueue_exc,
                        )
                        return RunResult(status_code=503)
                    return RunResult(status_code=200)

                SECTION_FAILURES.labels(
                    slug=slug.value, error_type=classify_error(exc)
                ).inc()
                logger.log(
                    logging.ERROR,
                    "section-retry: unclassified failure for job=%s slug=%s",
                    job_id,
                    slug.value,
                    exc_info=True,
                )
                try:
                    await mark_slot_failed(
                        pool,
                        job_id,
                        slug,
                        expected_slot_attempt_id,
                        error=str(exc),
                        expected_task_attempt=task_attempt,
                    )
                except Exception as inner:
                    logger.warning(
                        "section-retry: mark_slot_failed also raised for job=%s slug=%s: %s",
                        job_id,
                        slug.value,
                        inner,
                    )
                return RunResult(status_code=503)
            finally:
                SECTION_DURATION.labels(slug=slug.value).observe(
                    time.monotonic() - section_started
                )
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.warning(
                        "section-retry: heartbeat cancellation raised: %s", exc
                    )
        finally:
            clear_contextvars(attempt_tokens)
    finally:
        clear_contextvars(retry_tokens)


__all__ = [
    "HEARTBEAT_INTERVAL_SEC",
    "HandlerSuperseded",
    "RunResult",
    "TerminalError",
    "TransientError",
    "run_job",
    "run_section_retry",
]
