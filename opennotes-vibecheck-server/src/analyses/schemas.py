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
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._schemas import OpinionsReport
from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
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
    FACTS_CLAIMS_KNOWN_MISINFO = "facts_claims__known_misinfo"
    OPINIONS_SENTIMENTS_SENTIMENT = "opinions_sentiments__sentiment"
    OPINIONS_SENTIMENTS_SUBJECTIVE = "opinions_sentiments__subjective"


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
    """Deduped verifiable claims and any matching published fact-checks."""

    claims_report: ClaimsReport
    known_misinformation: list[FactCheckMatch] = Field(default_factory=list)


class OpinionsSection(BaseModel):
    """Sentiment distribution and extracted subjective claims."""

    opinions_report: OpinionsReport


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


class JobState(BaseModel):
    """GET /api/analyze/{job_id} response shape (wired in TASK-1473.14).

    Combines job-level lifecycle (status/error_code/error_message), per-slot
    progress (sections), the assembled sidebar (sidebar_payload, populated
    once all slots finish), and an adaptive polling hint (next_poll_ms) so
    clients can back off as the job completes.
    """

    job_id: UUID
    url: str
    status: JobStatus
    attempt_id: UUID
    error_code: ErrorCode | None = None
    error_message: str | None = None
    error_host: str | None = Field(
        default=None,
        description="When ErrorCode.UNSUPPORTED_SITE is returned, the host that triggered the rejection.",
    )
    created_at: datetime
    updated_at: datetime
    sections: dict[SectionSlug, SectionSlot] = Field(default_factory=dict)
    sidebar_payload: SidebarPayload | None = None
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
    utterance_count: int = Field(
        default=0,
        description="Number of utterances extracted for this job. 0 until the extractor writes any rows.",
    )


__all__ = [
    "ErrorCode",
    "FactsClaimsSection",
    "ImageModerationSection",
    "JobState",
    "JobStatus",
    "OpinionsSection",
    "PageKind",
    "SafetyRecommendation",
    "SafetySection",
    "SectionSlot",
    "SectionSlug",
    "SectionState",
    "SidebarPayload",
    "ToneDynamicsSection",
    "VideoModerationSection",
    "WebRiskSection",
]
