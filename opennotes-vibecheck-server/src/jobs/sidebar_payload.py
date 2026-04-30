"""Shared sidebar payload assembler for partial and final use.

`assemble_sidebar_payload` builds a `SidebarPayload` from any SectionSlot map,
using neutral defaults for missing, pending, running, or failed slots.
`payload_for_url_cache` serializes a payload for the legacy 72h cache,
stripping job-scoped utterance anchors.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

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
from src.analyses.schemas import (
    FactsClaimsSection,
    HeadlineSummary,
    ImageModerationSection,
    OpinionsSection,
    PageKind,
    SafetySection,
    SectionSlot,
    SectionSlug,
    SectionState,
    SidebarPayload,
    ToneDynamicsSection,
    UtteranceAnchor,
    VideoModerationSection,
    WebRiskSection,
)
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport
from src.jobs.section_defaults import empty_section_data


def assemble_sidebar_payload(
    url: str,
    sections: dict[SectionSlug, SectionSlot],
    safety_recommendation: Any | None = None,
    headline_summary: Any | None = None,
    utterances: list[UtteranceAnchor] | None = None,
) -> SidebarPayload:
    """Compose SidebarPayload from slot fragments.

    Each slot stores the sub-fragment its destination section needs. The
    merge rules here are the only place we reconcile slot-level shapes with
    the section-level schemas that `SidebarPayload` requires.
    """
    def data_for(slug: SectionSlug) -> dict[str, Any]:
        slot = sections.get(slug)
        if slot is None or slot.state != SectionState.DONE or not isinstance(slot.data, dict):
            return empty_section_data(slug)
        return slot.data

    safety_data = data_for(SectionSlug.SAFETY_MODERATION)
    raw_matches = safety_data.get("harmful_content_matches", [])
    validated_matches: list[HarmfulContentMatch] = []
    for raw_match in raw_matches:
        match_data = (
            {**raw_match, "source": "openai"}
            if isinstance(raw_match, dict) and "source" not in raw_match
            else raw_match
        )
        validated_matches.append(HarmfulContentMatch.model_validate(match_data))
    recommendation = (
        SafetyRecommendation.model_validate(
            json.loads(safety_recommendation)
            if isinstance(safety_recommendation, str)
            else safety_recommendation
        )
        if safety_recommendation is not None
        else None
    )
    safety = SafetySection(
        harmful_content_matches=validated_matches,
        recommendation=recommendation,
    )

    # TASK-1474: three new safety sections carry their own shape into the
    # sidebar. Any slug not registered with a handler still returns the
    # default-empty stub, which shapes validate.
    web_risk_findings = data_for(SectionSlug.SAFETY_WEB_RISK).get("findings", [])
    web_risk = WebRiskSection(
        findings=[WebRiskFinding.model_validate(f) for f in web_risk_findings]
    )

    image_mod_matches = data_for(SectionSlug.SAFETY_IMAGE_MODERATION).get(
        "matches", []
    )
    image_moderation = ImageModerationSection(
        matches=[ImageModerationMatch.model_validate(m) for m in image_mod_matches]
    )

    video_mod_matches = data_for(SectionSlug.SAFETY_VIDEO_MODERATION).get(
        "matches", []
    )
    video_moderation = VideoModerationSection(
        matches=[VideoModerationMatch.model_validate(m) for m in video_mod_matches]
    )

    flashpoint_data = data_for(SectionSlug.TONE_DYNAMICS_FLASHPOINT)
    scd_data = data_for(SectionSlug.TONE_DYNAMICS_SCD)
    tone = ToneDynamicsSection(
        scd=SCDReport.model_validate(scd_data["scd"]),
        flashpoint_matches=[
            FlashpointMatch.model_validate(m)
            for m in flashpoint_data.get("flashpoint_matches", [])
        ],
    )

    dedup_data = data_for(SectionSlug.FACTS_CLAIMS_DEDUP)
    known_data = data_for(SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO)
    facts = FactsClaimsSection(
        claims_report=ClaimsReport.model_validate(dedup_data["claims_report"]),
        known_misinformation=[
            FactCheckMatch.model_validate(m)
            for m in known_data.get("known_misinformation", [])
        ],
    )

    sentiment_data = data_for(SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT)
    subjective_data = data_for(SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE)
    opinions = OpinionsSection(
        opinions_report=OpinionsReport(
            sentiment_stats=sentiment_data["sentiment_stats"],
            subjective_claims=subjective_data.get("subjective_claims", []),
        )
    )

    headline = (
        HeadlineSummary.model_validate(
            json.loads(headline_summary)
            if isinstance(headline_summary, str)
            else headline_summary
        )
        if headline_summary is not None
        else None
    )

    return SidebarPayload(
        source_url=url,
        page_title=None,
        page_kind=PageKind.OTHER,
        scraped_at=datetime.now(UTC),
        cached=False,
        safety=safety,
        web_risk=web_risk,
        image_moderation=image_moderation,
        video_moderation=video_moderation,
        tone_dynamics=tone,
        facts_claims=facts,
        opinions_sentiments=opinions,
        headline=headline,
        utterances=utterances or [],
    )


def payload_for_url_cache(payload: SidebarPayload) -> str:
    """Serialize URL-cache payload without job-scoped utterance anchors."""
    cache_payload = payload.model_copy(update={"utterances": []})
    return json.dumps(cache_payload.model_dump(mode="json"))


__all__ = ["assemble_sidebar_payload", "payload_for_url_cache"]
