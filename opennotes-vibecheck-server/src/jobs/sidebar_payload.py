"""Shared sidebar payload assembler for partial and final use.

`assemble_sidebar_payload` builds a `SidebarPayload` from any SectionSlot map,
using neutral defaults for missing, pending, running, or failed slots.
`payload_for_url_cache` serializes a payload for the legacy 72h cache,
stripping job-scoped utterance anchors.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._highlights_schemas import OpinionsHighlightsReport
from src.analyses.opinions._schemas import OpinionsReport
from src.analyses.opinions._trends_schemas import TrendsOppositionsReport
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
    UtteranceStreamType,
    VideoModerationSection,
    WebRiskSection,
)
from src.analyses.synthesis._weather_schemas import WeatherReport
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport
from src.jobs.section_defaults import empty_section_data


def assemble_sidebar_payload(
    url: str,
    sections: dict[SectionSlug, SectionSlot],
    safety_recommendation: Any | None = None,
    headline_summary: Any | None = None,
    weather_report: Any | None = None,
    utterances: list[UtteranceAnchor] | None = None,
    page_title: str | None = None,
    page_kind: PageKind = PageKind.OTHER,
    utterance_stream_type: UtteranceStreamType = UtteranceStreamType.UNKNOWN,
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

    image_mod_matches = data_for(SectionSlug.SAFETY_IMAGE_MODERATION).get("matches", [])
    image_moderation = ImageModerationSection(
        matches=[ImageModerationMatch.model_validate(m) for m in image_mod_matches]
    )

    video_mod_matches = data_for(SectionSlug.SAFETY_VIDEO_MODERATION).get("matches", [])
    video_moderation = VideoModerationSection(
        matches=[VideoModerationMatch.model_validate(m) for m in video_mod_matches]
    )

    flashpoint_data = data_for(SectionSlug.TONE_DYNAMICS_FLASHPOINT)
    scd_data = data_for(SectionSlug.TONE_DYNAMICS_SCD)
    tone = ToneDynamicsSection(
        scd=SCDReport.model_validate(
            scd_data.get("scd", empty_section_data(SectionSlug.TONE_DYNAMICS_SCD)["scd"])
        ),
        flashpoint_matches=[
            FlashpointMatch.model_validate(m) for m in flashpoint_data.get("flashpoint_matches", [])
        ],
    )

    dedup_data = data_for(SectionSlug.FACTS_CLAIMS_DEDUP)
    known_data = data_for(SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO)
    evidence_data = data_for(SectionSlug.FACTS_CLAIMS_EVIDENCE)
    premises_data = data_for(SectionSlug.FACTS_CLAIMS_PREMISES)

    dedup_claims_report = ClaimsReport.model_validate(
        dedup_data.get(
            "claims_report",
            empty_section_data(SectionSlug.FACTS_CLAIMS_DEDUP)["claims_report"],
        )
    )
    evidence_claims_report = ClaimsReport.model_validate(
        evidence_data.get(
            "claims_report",
            empty_section_data(SectionSlug.FACTS_CLAIMS_EVIDENCE)["claims_report"],
        )
    )
    premises_report = ClaimsReport.model_validate(
        premises_data.get(
            "claims_report",
            empty_section_data(SectionSlug.FACTS_CLAIMS_PREMISES)["claims_report"],
        )
    )

    enriched_claims_by_canonical = {
        claim.canonical_text: claim for claim in evidence_claims_report.deduped_claims
    }
    premises_claims_by_canonical = {
        claim.canonical_text: claim for claim in premises_report.deduped_claims
    }

    merged_claims = []
    for claim in dedup_claims_report.deduped_claims:
        by_text = claim.model_copy()
        if claim.canonical_text in enriched_claims_by_canonical:
            evidence_claim = enriched_claims_by_canonical[claim.canonical_text]
            by_text.supporting_facts = evidence_claim.supporting_facts
            by_text.facts_to_verify = evidence_claim.facts_to_verify
        if claim.canonical_text in premises_claims_by_canonical:
            by_text.premise_ids = premises_claims_by_canonical[claim.canonical_text].premise_ids
        merged_claims.append(by_text)

    merged_claims_payload = dedup_claims_report.model_copy(
        update={
            "deduped_claims": merged_claims,
            "premises": premises_report.premises if premises_report.premises else None,
        }
    ).model_dump(mode="json")

    def _slot_status(
        slug: SectionSlug,
    ) -> Literal["pending", "running", "done", "failed"]:
        slot = sections.get(slug)
        state = slot.state if slot is not None else SectionState.PENDING
        return cast(Literal["pending", "running", "done", "failed"], state.value)

    facts = FactsClaimsSection(
        claims_report=ClaimsReport.model_validate(merged_claims_payload),
        known_misinformation=[
            FactCheckMatch.model_validate(m) for m in known_data.get("known_misinformation", [])
        ],
        evidence_status=_slot_status(SectionSlug.FACTS_CLAIMS_EVIDENCE),
        premises_status=_slot_status(SectionSlug.FACTS_CLAIMS_PREMISES),
    )

    sentiment_data = data_for(SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT)
    subjective_data = data_for(SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE)
    trends_oppositions_slot = sections.get(SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS)
    trends_oppositions_data = data_for(SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS)
    trends_oppositions = None
    if (
        trends_oppositions_slot is not None
        and trends_oppositions_slot.state == SectionState.DONE
        and isinstance(trends_oppositions_slot.data, dict)
        and "trends_oppositions_report" in trends_oppositions_slot.data
    ):
        trends_oppositions = TrendsOppositionsReport.model_validate(
            trends_oppositions_data["trends_oppositions_report"]
        )
    highlights_slot = sections.get(SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS)
    highlights_data = data_for(SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS)
    highlights = None
    if (
        highlights_slot is not None
        and highlights_slot.state == SectionState.DONE
        and isinstance(highlights_slot.data, dict)
        and "highlights_report" in highlights_slot.data
    ):
        highlights = OpinionsHighlightsReport.model_validate(highlights_data["highlights_report"])

    opinions = OpinionsSection(
        opinions_report=OpinionsReport(
            sentiment_stats=sentiment_data.get(
                "sentiment_stats",
                empty_section_data(SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT)["sentiment_stats"],
            ),
            subjective_claims=subjective_data.get("subjective_claims", []),
        ),
        trends_oppositions=trends_oppositions,
        highlights=highlights,
    )

    headline = (
        HeadlineSummary.model_validate(
            json.loads(headline_summary) if isinstance(headline_summary, str) else headline_summary
        )
        if headline_summary is not None
        else None
    )

    weather = (
        WeatherReport.model_validate(json.loads(weather_report))
        if isinstance(weather_report, str)
        else WeatherReport.model_validate(weather_report)
        if weather_report is not None
        else None
    )

    return SidebarPayload(
        source_url=url,
        page_title=page_title,
        page_kind=page_kind,
        utterance_stream_type=utterance_stream_type,
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
        weather_report=weather,
        utterances=utterances or [],
    )


def payload_for_url_cache(payload: SidebarPayload) -> str:
    """Serialize URL-cache payload without job-scoped utterance anchors."""
    cache_payload = payload.model_copy(update={"utterances": []})
    return json.dumps(cache_payload.model_dump(mode="json"))


__all__ = ["assemble_sidebar_payload", "payload_for_url_cache"]
