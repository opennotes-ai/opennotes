"""Domain schemas for the safety analysis (harmful-content moderation).

Kept local to this analysis module to avoid merge conflicts with other
parallel analyses (tone, claims, opinions). The orchestrator aggregates
these sub-schemas into the final `SidebarPayload`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HarmfulContentMatch(BaseModel):
    """A single flagged utterance from the OpenAI moderation API."""

    utterance_id: str
    max_score: float
    categories: dict[str, bool]
    scores: dict[str, float]
    flagged_categories: list[str] = Field(default_factory=list)
