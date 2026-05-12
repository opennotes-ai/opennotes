"""Domain schemas for the safety analysis (harmful-content moderation).

Kept local to this analysis module to avoid merge conflicts with other
parallel analyses (tone, claims, opinions). The orchestrator aggregates
these sub-schemas into the final `SidebarPayload`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class SafetyLevel(StrEnum):
    SAFE = "safe"
    MILD = "mild"
    CAUTION = "caution"
    UNSAFE = "unsafe"


class SafetyRecommendation(BaseModel):
    level: SafetyLevel
    rationale: str
    top_signals: list[str] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


class HarmfulContentMatch(BaseModel):
    """A single flagged utterance from a content moderation API.

    `utterance_text` and `source` default so `sidebar_payload` blobs
    written before these fields existed (pre PR #411) still deserialize
    when `GET /api/analyze/{job_id}` reads them. New writes always
    populate both (see `jobs/finalize.py` and `moderation_slot.py`).
    """

    utterance_id: str
    utterance_text: str = ""
    max_score: float
    categories: dict[str, bool]
    scores: dict[str, float]
    flagged_categories: list[str] = Field(default_factory=list)
    source: Literal["openai", "gcp"] = "openai"
    chunk_idx: int | None = None
    chunk_count: int | None = None


class WebRiskFinding(BaseModel):
    """A URL flagged by GCP Web Risk."""

    url: str
    threat_types: list[
        Literal[
            "MALWARE",
            "SOCIAL_ENGINEERING",
            "UNWANTED_SOFTWARE",
            "POTENTIALLY_HARMFUL_APPLICATION",
        ]
    ]


class VideoSegmentFinding(BaseModel):
    """SafeSearch scores for a video segment or sampled frame."""

    start_offset_ms: int
    end_offset_ms: int
    adult: float
    violence: float
    racy: float
    medical: float
    spoof: float
    flagged: bool
    max_likelihood: float


class ImageModerationMatch(BaseModel):
    """GCP Vision SafeSearch result for a single image."""

    utterance_id: str
    image_url: str
    adult: float
    violence: float
    racy: float
    medical: float
    spoof: float
    flagged: bool
    max_likelihood: float


class VideoModerationMatch(BaseModel):
    """GCP Video Intelligence SafeSearch result for a single video."""

    utterance_id: str
    video_url: str
    segment_findings: list[VideoSegmentFinding] = Field(
        validation_alias=AliasChoices("segment_findings", "frame_findings")
    )
    flagged: bool
    max_likelihood: float

    model_config = ConfigDict(populate_by_name=True)
