"""Pydantic schemas for Speaker Conversational Dynamics (SCD) analysis.

Kept in a module-private file (`_scd_schemas.py`) so the sibling flashpoint
module can own its own schemas without touching `src/analyses/tone/__init__.py`.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SCDReport(BaseModel):
    """Structured output of `analyze_scd`.

    Mirrors the structural intent of Cornell ConvoKit's SCD trajectory summary:
    a short dynamics narrative, a small set of tone labels, and per-speaker
    observations. For inputs that lack a real multi-speaker conversation, the
    model is bypassed and `insufficient_conversation=True` is set.
    """

    summary: str = Field(
        ...,
        description=(
            "Overall conversational-dynamics narrative (<= ~80 words). "
            "Captures sentiment shifts, intentions, and persuasive strategies "
            "without restating specific topics or claims."
        ),
    )
    tone_labels: list[str] = Field(
        default_factory=list,
        description=(
            "Short tone descriptors for the conversation as a whole "
            "(e.g. 'combative', 'collaborative', 'dismissive', 'civil')."
        ),
    )
    per_speaker_notes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of speaker label -> 1-2 sentence observation about that "
            "speaker's tone, intent, or conversational strategy."
        ),
    )
    insufficient_conversation: bool = Field(
        default=False,
        description=(
            "True when the input lacks a real multi-speaker exchange "
            "(e.g. a blog post with no comments). When true, callers "
            "should treat `summary` as a fixed placeholder and ignore "
            "`tone_labels` / `per_speaker_notes`."
        ),
    )
