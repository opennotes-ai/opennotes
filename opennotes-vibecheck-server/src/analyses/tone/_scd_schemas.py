"""Pydantic schemas for Speaker Conversational Dynamics (SCD) analysis.

Kept in a module-private file (`_scd_schemas.py`) so the sibling flashpoint
module can own its own schemas without touching `src/analyses/tone/__init__.py`.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class SpeakerArc(BaseModel):
    """Per-speaker arc within a conversation, intended for timeline visualization.

    Each arc localizes one speaker's contribution to the conversational shape:
    a short prose `note` paired with an optional `utterance_id_range` so the
    frontend can map the arc back onto the rendered transcript timeline. The
    range is `None` when the LLM cannot confidently localize the arc to a
    contiguous span (e.g. interleaved or sparse contributions).
    """

    speaker: str = Field(
        ...,
        description=(
            "Speaker label as it appears in the formatted transcript "
            "(e.g. 'alice', 'Speaker1')."
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
            "with start <= end and start >= 1. `None` when the LLM cannot "
            "localize the arc to a contiguous span. Modeled as a list (not a "
            "tuple) so the generated OpenAPI schema produces a plain integer "
            "array rather than a fixed-length prefixItems tuple, which "
            "openapi-fetch widens to `number[]` and would otherwise cause a "
            "TS2719 mismatch with the named JobState response type."
        ),
    )

    @field_validator("utterance_id_range", mode="after")
    @classmethod
    def _validate_utterance_id_range(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if len(v) != 2:
            raise ValueError(
                "utterance_id_range must have exactly 2 elements (start, end)"
            )
        start, end = v[0], v[1]
        if start > end:
            raise ValueError("utterance_id_range start must be <= end")
        if start < 1:
            raise ValueError("utterance_id_range indices must be 1-indexed (>= 1)")
        return v


class SCDReport(BaseModel):
    """Structured output of `analyze_scd`.

    Mirrors the structural intent of Cornell ConvoKit's SCD trajectory summary,
    but in a conversational register: a free-form `narrative` describing how
    the conversation unfolds, and a structured `speaker_arcs` list ready for
    timeline visualization. Legacy fields (`summary`, `tone_labels`,
    `per_speaker_notes`, `insufficient_conversation`) are retained so existing
    consumers continue to work while orchestrator slot wiring is migrated.
    For inputs that lack a real multi-speaker conversation, the model is
    bypassed and `insufficient_conversation=True` is set.
    """

    narrative: str = Field(
        default="",
        description=(
            "Conversational-register narrative (~80-150 words) describing how "
            "the conversation unfolds: turn-taking dynamics, escalation or "
            "de-escalation, shifts in stance, and persuasive moves. Prose "
            "voice — does not restate specific topics, claims, or quotes."
        ),
    )
    speaker_arcs: list[SpeakerArc] = Field(
        default_factory=list,
        description=(
            "Per-speaker arcs across the conversation, ordered for timeline "
            "visualization. Each arc carries the speaker label, a short note "
            "on their evolution, and an optional utterance index range so "
            "the frontend can align the arc with the rendered transcript."
        ),
    )
    summary: str = Field(
        ...,
        description=(
            "Legacy: overall conversational-dynamics narrative (<= ~80 words). "
            "Captures sentiment shifts, intentions, and persuasive strategies "
            "without restating specific topics or claims. Preserved for "
            "back-compat with existing consumers; new code should read "
            "`narrative` instead."
        ),
    )
    tone_labels: list[str] = Field(
        default_factory=list,
        description=(
            "Legacy: short tone descriptors for the conversation as a whole "
            "(e.g. 'combative', 'collaborative', 'dismissive', 'civil'). "
            "Preserved for back-compat."
        ),
    )
    per_speaker_notes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Legacy: map of speaker label -> 1-2 sentence observation about "
            "that speaker's tone, intent, or conversational strategy. "
            "Preserved for back-compat; new code should read `speaker_arcs` "
            "for timeline-viz-ready per-speaker information."
        ),
    )
    insufficient_conversation: bool = Field(
        default=False,
        description=(
            "True when the input lacks a real multi-speaker exchange "
            "(e.g. a blog post with no comments). When true, callers "
            "should treat `summary` as a fixed placeholder and ignore "
            "`tone_labels` / `per_speaker_notes` / `speaker_arcs`."
        ),
    )
