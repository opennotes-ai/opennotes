"""Top-level sidebar payload aggregating every analysis section.

Each sub-analysis owns its own `_schemas.py` (or equivalently-named schema
module) under `src/analyses/<name>/`. This module is the single place that
composes those sub-schemas into the single `SidebarPayload` contract the
frontend consumes from `POST /api/analyze`.

This module also hosts the typed contracts for the async job pipeline
introduced in TASK-1473: `SectionSlug`, `SectionState`, `SectionSlot`,
`JobStatus`, `ErrorCode`, `JobState`, `PageKind`. Downstream tickets wire
these into routes and storage; emission into the generated OpenAPI schema
is anchored by `routes/_schema_anchor.py` until TASK-1473.14 lands the real
`GET /api/analyze/{job_id}` endpoint.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._highlights_schemas import OpinionsHighlightsReport
from src.analyses.opinions._schemas import OpinionsReport
from src.analyses.opinions._trends_schemas import TrendsOppositionsReport
from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.stream_types import UtteranceStreamType
from src.analyses.synthesis._weather_schemas import WeatherReport
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport


class PageKind(StrEnum):
    """Shape of the source page the extractor handled.

    The extractor in TASK-1473.10 picks one of these; downstream rendering
    and analysis logic branches on the value (e.g., hierarchical_thread
    enables tree-aware flashpoint context).
    """

    BLOG_POST = "blog_post"
    FORUM_THREAD = "forum_thread"
    HIERARCHICAL_THREAD = "hierarchical_thread"
    BLOG_INDEX = "blog_index"
    ARTICLE = "article"
    OTHER = "other"


class SectionSlug(StrEnum):
    """The sidebar slots the async pipeline fills independently."""

    SAFETY_MODERATION = "safety__moderation"
    SAFETY_WEB_RISK = "safety__web_risk"
    SAFETY_IMAGE_MODERATION = "safety__image_moderation"
    SAFETY_VIDEO_MODERATION = "safety__video_moderation"
    TONE_DYNAMICS_FLASHPOINT = "tone_dynamics__flashpoint"
    TONE_DYNAMICS_SCD = "tone_dynamics__scd"
    FACTS_CLAIMS_DEDUP = "facts_claims__dedup"
    FACTS_CLAIMS_EVIDENCE = "facts_claims__evidence"
    FACTS_CLAIMS_PREMISES = "facts_claims__premises"
    FACTS_CLAIMS_KNOWN_MISINFO = "facts_claims__known_misinfo"
    OPINIONS_SENTIMENTS_SENTIMENT = "opinions_sentiments__sentiment"
    OPINIONS_SENTIMENTS_SUBJECTIVE = "opinions_sentiments__subjective"
    OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS = "opinions_sentiments__trends_oppositions"
    OPINIONS_SENTIMENTS_HIGHLIGHTS = "opinions_sentiments__highlights"


class SectionState(StrEnum):
    """Lifecycle of a single sidebar slot during a job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobStatus(StrEnum):
    """Lifecycle of a vibecheck job from POST to terminal state."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class ErrorCode(StrEnum):
    """Stable error codes the frontend branches on for inline copy + retry UX."""

    INVALID_URL = "invalid_url"
    UNSAFE_URL = "unsafe_url"
    UNSUPPORTED_SITE = "unsupported_site"
    UPSTREAM_ERROR = "upstream_error"
    EXTRACTION_FAILED = "extraction_failed"
    SECTION_FAILURE = "section_failure"
    PDF_TOO_LARGE = "pdf_too_large"
    PDF_EXTRACTION_FAILED = "pdf_extraction_failed"
    UPLOAD_KEY_INVALID = "upload_key_invalid"
    UPLOAD_NOT_FOUND = "upload_not_found"
    INVALID_PDF_TYPE = "invalid_pdf_type"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    INTERNAL = "internal"


class SectionSlot(BaseModel):
    """One sidebar slot's state inside a JobState.

    `attempt_id` is regenerated on each retry; Cloud Tasks redeliveries that
    carry a stale attempt_id are rejected by the worker. `data` holds the
    section-specific payload once `state == DONE` (shape varies by slug).
    """

    state: SectionState
    attempt_id: UUID
    data: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SafetySection(BaseModel):
    """Harmful-content matches surfaced by OpenAI moderation."""

    harmful_content_matches: list[HarmfulContentMatch] = Field(default_factory=list)
    recommendation: SafetyRecommendation | None = None


class WebRiskSection(BaseModel):
    """GCP Web Risk findings for URLs referenced in the page."""

    findings: list[WebRiskFinding] = Field(default_factory=list)
    urls_checked: int = Field(
        default=0,
        description="Number of distinct URLs submitted to Web Risk for this job (page URL plus any URLs extracted from utterances).",
    )


class ImageModerationSection(BaseModel):
    """GCP Vision SafeSearch results for images referenced in the page."""

    matches: list[ImageModerationMatch] = Field(default_factory=list)


class VideoModerationSection(BaseModel):
    """GCP Video Intelligence SafeSearch results for videos referenced in the page."""

    matches: list[VideoModerationMatch] = Field(default_factory=list)


class ToneDynamicsSection(BaseModel):
    """Speaker conversational dynamics + per-utterance flashpoint matches."""

    scd: SCDReport
    flashpoint_matches: list[FlashpointMatch] = Field(default_factory=list)


class FactsClaimsSection(BaseModel):
    """Deduped verifiable claims and any matching published fact-checks.

    `evidence_status` and `premises_status` expose the terminal lifecycle
    of the two enrichment slots (`FACTS_CLAIMS_EVIDENCE` /
    `FACTS_CLAIMS_PREMISES`) at sidebar-payload assembly time. Frontend
    surfaces use them to distinguish "evidence ran and found nothing" from
    "evidence failed" — without these, both paths render the same empty
    `supporting_facts` and the user sees a misleading "No sources extracted"
    placeholder for sub-slots that actually errored.
    """

    claims_report: ClaimsReport
    known_misinformation: list[FactCheckMatch] = Field(default_factory=list)
    evidence_status: Literal["pending", "running", "done", "failed"] | None = Field(
        default=None,
        description=(
            "Terminal state of the FACTS_CLAIMS_EVIDENCE slot at the time the "
            "sidebar payload was assembled. `done` means the slot ran (rows may "
            "still be empty); `failed` means the slot errored and any empty "
            "`supporting_facts` should be surfaced as a failure rather than "
            "a clean empty result; `pending` / `running` mean the slot has not "
            "yet reached a terminal state for this payload snapshot. Null when "
            "an older cached payload was assembled before this field existed."
        ),
    )
    premises_status: Literal["pending", "running", "done", "failed"] | None = Field(
        default=None,
        description=(
            "Terminal state of the FACTS_CLAIMS_PREMISES slot at the time the "
            "sidebar payload was assembled. Same semantics as `evidence_status`."
        ),
    )


class OpinionsSection(BaseModel):
    """Sentiment distribution and extracted subjective claims."""

    opinions_report: OpinionsReport
    trends_oppositions: TrendsOppositionsReport | None = None
    highlights: OpinionsHighlightsReport | None = None


class HeadlineSummary(BaseModel):
    """1-2 sentence synthesis rendered above the safety recommendation.

    `kind` discriminates the deterministic stock-phrase short-circuit (when
    every input section is empty/clear/neutral) from the model-generated
    synthesis path. `unavailable_inputs` mirrors the SafetyRecommendation
    pattern so the UI can later annotate degraded coverage.
    """

    text: str
    kind: Literal["stock", "synthesized"]
    unavailable_inputs: list[str] = Field(default_factory=list)


class UtteranceAnchor(BaseModel):
    """Minimal position-to-id map for client-side transcript jumps."""

    position: int = Field(description="1-indexed utterance position in the extracted thread.")
    utterance_id: str = Field(description="Stable utterance id stored in vibecheck_job_utterances.")
    timestamp: datetime | None = Field(
        default=None,
        description="Wall-clock timestamp for the utterance when the source thread exposed one.",
    )


class SidebarPayload(BaseModel):
    """Top-level response for `POST /api/analyze`.

    Aggregates all four sidebar sections plus identity/metadata fields the
    frontend needs to render the result. `cached=True` indicates the payload
    was served from the Supabase cache (72h TTL) instead of a freshly run
    pipeline.
    """

    source_url: str
    page_title: str | None = None
    page_kind: PageKind = PageKind.OTHER
    utterance_stream_type: UtteranceStreamType = UtteranceStreamType.UNKNOWN
    scraped_at: datetime
    cached: bool = False
    cached_at: datetime | None = None
    safety: SafetySection
    tone_dynamics: ToneDynamicsSection
    facts_claims: FactsClaimsSection
    opinions_sentiments: OpinionsSection
    web_risk: WebRiskSection = Field(default_factory=WebRiskSection)
    image_moderation: ImageModerationSection = Field(default_factory=ImageModerationSection)
    video_moderation: VideoModerationSection = Field(default_factory=VideoModerationSection)
    headline: HeadlineSummary | None = None
    weather_report: WeatherReport | None = None
    utterances: list[UtteranceAnchor] = Field(
        default_factory=list,
        description="Minimal position-to-id anchors used by sidebar controls to jump into the archived transcript.",
    )


class JobState(BaseModel):
    """GET /api/analyze/{job_id} response shape.

    Combines job-level lifecycle (status/error_code/error_message), per-slot
    progress (sections), an adaptive polling hint (next_poll_ms), and the
    sidebar payload. During active polling (pending/extracting/analyzing),
    sidebar_payload is assembled from whichever section slots have finished
    and is partial — check sidebar_payload_complete to distinguish partial
    from canonical. Once the job reaches a terminal status (done/partial/
    failed), sidebar_payload holds the persisted result. sidebar_payload_complete
    is true only for done/partial jobs whose persisted payload represents the
    final canonical sidebar; failed jobs may carry a deliberately minimal
    payload and keep sidebar_payload_complete false.
    """

    job_id: UUID
    url: str
    status: JobStatus
    attempt_id: UUID
    error_code: ErrorCode | None = None
    error_message: str | None = None
    source_type: Literal["url", "pdf", "browser_html"] = "url"
    pdf_archive_url: str | None = None
    error_host: str | None = Field(
        default=None,
        description="When ErrorCode.UNSUPPORTED_SITE is returned, the host that triggered the rejection.",
    )
    created_at: datetime
    updated_at: datetime
    sections: dict[SectionSlug, SectionSlot] = Field(default_factory=dict)
    sidebar_payload: SidebarPayload | None = Field(
        default=None,
        description=(
            "Assembled sidebar content. During polling (non-terminal status) this is "
            "a partial aggregate built from whichever section slots have finished — "
            "it is not canonical until sidebar_payload_complete is true. On done/partial "
            "terminal jobs this is the persisted canonical result. Failed jobs may carry "
            "a minimal persisted payload and keep sidebar_payload_complete false."
        ),
    )
    sidebar_payload_complete: bool = Field(
        default=False,
        description=(
            "True only when sidebar_payload holds the final canonical result for done or "
            "partial terminal jobs. False during polling, meaning sidebar_payload may be "
            "partial and will keep changing as more section slots finish. False for failed "
            "jobs that carry only a minimal error payload. Clients must not treat a non-null "
            "sidebar_payload as canonical until this flag is true."
        ),
    )
    activity_at: datetime | None = None
    activity_label: str | None = None
    cached: bool = False
    next_poll_ms: int = Field(
        default=1500,
        description="Server-suggested delay until the client should re-poll. Clients use this to implement adaptive cadence (typically 500ms early, 1500ms+ near completion).",
    )
    # Page metadata extracted from vibecheck_job_utterances (codex W4 P2-2).
    # Null / 0 before the extractor writes utterance rows; populated once at
    # least one utterance exists for the job. Keeping these top-level on
    # JobState (rather than nested inside sidebar_payload) lets the client
    # render the page header as soon as extraction finishes without waiting
    # for every slot to complete.
    page_title: str | None = Field(
        default=None,
        description="Extracted page title, sourced from vibecheck_job_utterances. Null until the extractor runs.",
    )
    page_kind: PageKind | None = Field(
        default=None,
        description="Extracted page shape, sourced from vibecheck_job_utterances. Null until the extractor runs.",
    )
    utterance_stream_type: UtteranceStreamType | None = Field(
        default=None,
        description=(
            "Extracted utterance-stream shape, sourced from vibecheck_job_utterances. "
            "Null until the extractor runs."
        ),
    )
    utterance_count: int = Field(
        default=0,
        description="Number of utterances extracted for this job. 0 until the extractor writes any rows.",
    )
    expired_at: datetime | None = Field(
        default=None,
        description=(
            "When set, this job has been soft-deleted by the 7-day purge cron. "
            "Heavy payload columns are cleared: sidebar_payload is NULL, sections is "
            "'{}' (empty JSON object). "
            "The job_id permalink remains addressable; clients should render an "
            "'analysis expired — re-analyze' card instead of the standard sidebar."
        ),
    )


class RecentAnalysis(BaseModel):
    """One card in the "Recently vibe checked" gallery (TASK-1485).

    Returned by `GET /api/analyses/recent`. The endpoint guarantees
    `preview_description` is non-null at the API boundary so the frontend
    never has to handle null preview text. `screenshot_url` is a 15-min
    signed GCS URL; clients re-request the endpoint to refresh.
    """

    job_id: UUID = Field(
        description="vibecheck_jobs.job_id; cards link to /analyze?job=<job_id>.",
    )
    source_url: str
    page_title: str | None = None
    screenshot_url: str = Field(
        description="15-min signed GCS URL for the page screenshot.",
    )
    preview_description: str = Field(
        description="Short blurb (~140 chars) summarizing the most interesting finding. Non-null at the API boundary.",
    )
    completed_at: datetime


__all__ = [
    "ErrorCode",
    "FactsClaimsSection",
    "ImageModerationSection",
    "JobState",
    "JobStatus",
    "OpinionsSection",
    "PageKind",
    "RecentAnalysis",
    "SafetyRecommendation",
    "SafetySection",
    "SectionSlot",
    "SectionSlug",
    "SectionState",
    "SidebarPayload",
    "ToneDynamicsSection",
    "UtteranceAnchor",
    "UtteranceStreamType",
    "VideoModerationSection",
    "WebRiskSection",
]
