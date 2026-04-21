"""Top-level sidebar payload aggregating every analysis section.

Each sub-analysis owns its own `_schemas.py` (or equivalently-named schema
module) under `src/analyses/<name>/`. This module is the single place that
composes those sub-schemas into the single `SidebarPayload` contract the
frontend consumes from `POST /api/analyze`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._schemas import OpinionsReport
from src.analyses.safety._schemas import HarmfulContentMatch
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport


class SafetySection(BaseModel):
    """Harmful-content matches surfaced by OpenAI moderation."""

    harmful_content_matches: list[HarmfulContentMatch] = Field(default_factory=list)


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
    page_kind: Literal["blog_post", "forum_thread", "article", "other"] = "other"
    scraped_at: datetime
    cached: bool = False
    safety: SafetySection
    tone_dynamics: ToneDynamicsSection
    facts_claims: FactsClaimsSection
    opinions_sentiments: OpinionsSection


__all__ = [
    "FactsClaimsSection",
    "OpinionsSection",
    "SafetySection",
    "SidebarPayload",
    "ToneDynamicsSection",
]
