from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class SafetyLevel(StrEnum):
    SAFE = "safe"
    CAUTION = "caution"
    UNSAFE = "unsafe"


class SafetyRecommendation(BaseModel):
    level: SafetyLevel
    rationale: str
    top_signals: list[str] = Field(default_factory=list)
    unavailable_inputs: list[str] = Field(default_factory=list)


class HarmfulContentMatch(BaseModel):
    utterance_id: str
    utterance_text: str = ""
    max_score: float
    categories: dict[str, bool]
    scores: dict[str, float]
    flagged_categories: list[str] = Field(default_factory=list)
    source: Literal["openai", "gcp"] = "openai"


class WebRiskFinding(BaseModel):
    url: str
    threat_types: list[
        Literal[
            "MALWARE",
            "SOCIAL_ENGINEERING",
            "UNWANTED_SOFTWARE",
            "POTENTIALLY_HARMFUL_APPLICATION",
        ]
    ]


class FrameFinding(BaseModel):
    frame_offset_ms: int
    adult: float
    violence: float
    racy: float
    medical: float
    spoof: float
    flagged: bool
    max_likelihood: float


class ImageModerationMatch(BaseModel):
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
    utterance_id: str
    video_url: str
    frame_findings: list[FrameFinding]
    flagged: bool
    max_likelihood: float
