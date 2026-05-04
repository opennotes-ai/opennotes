"""Wire contracts for URL content scan polling and sidebar payloads."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.url_content_scan.claims_schemas import ClaimsReport, FactCheckMatch
from src.url_content_scan.opinions_schemas import OpinionsReport
from src.url_content_scan.safety_schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.url_content_scan.tone_schemas import FlashpointMatch, SCDReport


class PageKind(StrEnum):
    BLOG_POST = "blog_post"
    FORUM_THREAD = "forum_thread"
    HIERARCHICAL_THREAD = "hierarchical_thread"
    BLOG_INDEX = "blog_index"
    ARTICLE = "article"
    OTHER = "other"


class SectionSlug(StrEnum):
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
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobStatus(StrEnum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class ErrorCode(StrEnum):
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
    state: SectionState
    attempt_id: UUID
    data: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SafetySection(BaseModel):
    harmful_content_matches: list[HarmfulContentMatch] = Field(default_factory=list)
    recommendation: SafetyRecommendation | None = None


class WebRiskSection(BaseModel):
    findings: list[WebRiskFinding] = Field(default_factory=list)


class ImageModerationSection(BaseModel):
    matches: list[ImageModerationMatch] = Field(default_factory=list)


class VideoModerationSection(BaseModel):
    matches: list[VideoModerationMatch] = Field(default_factory=list)


class ToneDynamicsSection(BaseModel):
    scd: SCDReport
    flashpoint_matches: list[FlashpointMatch] = Field(default_factory=list)


class FactsClaimsSection(BaseModel):
    claims_report: ClaimsReport
    known_misinformation: list[FactCheckMatch] = Field(default_factory=list)


class OpinionsSection(BaseModel):
    opinions_report: OpinionsReport


class HeadlineSummary(BaseModel):
    text: str
    kind: Literal["stock", "synthesized"]
    unavailable_inputs: list[str] = Field(default_factory=list)


class SidebarPayload(BaseModel):
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
    headline: HeadlineSummary | None = None


class JobState(BaseModel):
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
    sidebar_payload_complete: bool = False
    activity_at: datetime | None = None
    activity_label: str | None = None
    cached: bool = False
    next_poll_ms: int = 1500
    page_title: str | None = None
    page_kind: PageKind | None = None
    utterance_count: int = 0


__all__ = [
    "ErrorCode",
    "FactsClaimsSection",
    "HeadlineSummary",
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
