from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class RiskLevel(StrEnum):
    LOW_RISK = "Low Risk"
    GUARDED = "Guarded"
    HEATED = "Heated"
    HOSTILE = "Hostile"
    DANGEROUS = "Dangerous"


class UtteranceStreamType(StrEnum):
    """Discourse shape observed in the extracted utterance stream."""

    DIALOGUE = "dialogue"
    COMMENT_SECTION = "comment_section"
    ARTICLE_OR_MONOLOGUE = "article_or_monologue"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class FlashpointMatch(BaseModel):
    scan_type: Literal["conversation_flashpoint"] = "conversation_flashpoint"
    utterance_id: str = Field(
        ..., description="Platform-agnostic identifier of the scored utterance"
    )
    derailment_score: int = Field(..., ge=0, le=100, description="Derailment risk score (0-100)")
    risk_level: RiskLevel = Field(..., description="Categorical risk assessment level")
    reasoning: str = Field(..., description="Explanation of detected escalation signals")
    context_messages: int = Field(..., ge=0, description="Number of context messages analyzed")


class SpeakerArc(BaseModel):
    speaker: str = Field(
        ...,
        description=(
            "Speaker label as it appears in the formatted transcript (e.g. 'alice', 'Speaker1')."
        ),
    )
    note: str = Field(
        ...,
        description=(
            "1-2 sentence observation about this speaker's arc: how their "
            "tone, intent, or stance evolves across the conversation."
        ),
    )
    utterance_id_range: list[Annotated[int, Field(ge=1)]] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description=(
            "Inclusive [start, end] 1-indexed utterance index range that this "
            "arc covers, for timeline-viz alignment. Exactly two integers "
            "with start <= end and start >= 1."
        ),
    )

    @field_validator("utterance_id_range", mode="after")
    @classmethod
    def validate_utterance_id_range(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if len(value) != 2:
            raise ValueError("utterance_id_range must have exactly 2 elements (start, end)")
        start, end = value
        if start > end:
            raise ValueError("utterance_id_range start must be <= end")
        if start < 1:
            raise ValueError("utterance_id_range indices must be 1-indexed (>= 1)")
        return value


class SCDReport(BaseModel):
    narrative: str = Field(
        default="",
        description=(
            "Conversational-register narrative (~80-150 words) describing how "
            "the conversation unfolds."
        ),
    )
    speaker_arcs: list[SpeakerArc] = Field(default_factory=list)
    summary: str = Field(...)
    tone_labels: list[str] = Field(default_factory=list)
    per_speaker_notes: dict[str, str] = Field(default_factory=dict)
    insufficient_conversation: bool = Field(default=False)
    upstream_stream_type: UtteranceStreamType = Field(
        default=UtteranceStreamType.UNKNOWN,
        description="Extractor-provided advisory utterance stream type.",
    )
    observed_stream_type: UtteranceStreamType = Field(
        default=UtteranceStreamType.UNKNOWN,
        description="SCD model's own classification of the utterance stream shape.",
    )
    observed_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in observed_stream_type, from 0.0 to 1.0.",
    )
    disagreement_rationale: str = Field(
        default="",
        description="Short rationale when observed_stream_type differs from upstream_stream_type.",
    )
