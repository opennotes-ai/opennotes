"""Synthesis agent producing the 1-2 sentence sidebar headline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.llm_config.model_id import ModelId
from src.url_content_scan.claims_schemas import ClaimsReport, FactCheckMatch
from src.url_content_scan.opinions_schemas import SentimentStatsReport, SubjectiveClaim
from src.url_content_scan.safety_schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.url_content_scan.schemas import HeadlineSummary, PageKind
from src.url_content_scan.tone_schemas import FlashpointMatch, SCDReport

if TYPE_CHECKING:
    from src.config import Settings


DEFAULT_HEADLINE_MODEL = "google-vertex:gemini-3.1-pro-preview"

HEADLINE_SUMMARY_SYSTEM_PROMPT = """You synthesize a 1-2 sentence narrative lead for one analyzed page.
Use the inputs (safety verdict, conversation dynamics, claims, and sentiment)
to describe the page's overall thrust and dynamic - the core story, not an
inventory of available signals.
By default, write one pithy sentence.
Only add a second sentence when it contributes a distinct high-signal point.

Do not write like a tabloid headline.
Do not list which specific sections were missing or absent - never name slot
identifiers like "scd" or "web_risk".

When `unavailable_inputs` is non-empty, coverage was incomplete: your line
MUST NOT claim everything is clear or that there is nothing of note. Describe
what the available analyses surfaced, and frame the absence of flags as
"in what was analyzed" rather than as a global all-clear.

If inputs are minimal, be direct and brief. Output a HeadlineSummary with
`kind` set to "synthesized" - the caller will overwrite kind anyway, but
always set it."""

_STOCK_PHRASES: tuple[str, ...] = (
    "Nothing of note in this content.",
    "Routine content with no signals to flag.",
    "Calm content; little to call out.",
    "Standard content; nothing remarkable.",
    "Quiet page; nothing to highlight.",
    "An ordinary page; not much to say.",
)

_DEGRADED_STOCK_PHRASES: tuple[str, ...] = (
    "Coverage was incomplete; nothing flagged in the analyzed sections.",
    "Partial analysis; the available checks did not surface anything.",
    "Limited coverage this run; analyzed sections came back clean.",
    "Some sections did not report; the rest are unremarkable.",
    "Reduced coverage; the completed analyses are quiet.",
    "Analysis was partial; what completed had nothing to flag.",
)

_SIGNAL_FALLBACK_PHRASES: tuple[str, ...] = (
    "The available checks surfaced signals worth reviewing.",
    "This page has signals that merit a closer look.",
    "The analysis found activity that should be reviewed.",
    "Available signals suggest this page needs human attention.",
    "This page is not an all-clear; review the completed sections.",
    "The completed checks found enough to warrant review.",
)


@dataclass(frozen=True)
class HeadlineSummaryInputs:
    safety_recommendation: SafetyRecommendation | None
    harmful_content_matches: list[HarmfulContentMatch]
    web_risk_findings: list[WebRiskFinding]
    image_moderation_matches: list[ImageModerationMatch]
    video_moderation_matches: list[VideoModerationMatch]
    flashpoint_matches: list[FlashpointMatch]
    scd: SCDReport | None
    claims_report: ClaimsReport | None
    known_misinformation: list[FactCheckMatch]
    sentiment_stats: SentimentStatsReport | None
    subjective_claims: list[SubjectiveClaim]
    page_title: str | None
    page_kind: PageKind
    unavailable_inputs: list[str]


headline_summary_agent: Agent[None, HeadlineSummary] = Agent(
    name="url-content-scan-headline-summary",
    output_type=HeadlineSummary,
    instrument=True,
)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def all_inputs_clear(inputs: HeadlineSummaryInputs) -> bool:
    image_signal = bool(inputs.image_moderation_matches)
    video_signal = bool(inputs.video_moderation_matches)
    scd_signal = inputs.scd is not None and (
        not inputs.scd.insufficient_conversation
        or bool(inputs.scd.tone_labels)
        or bool(inputs.scd.per_speaker_notes)
    )
    claims_signal = inputs.claims_report is not None and bool(inputs.claims_report.deduped_claims)
    sentiment_signal = inputs.sentiment_stats is not None and (
        bool(inputs.sentiment_stats.per_utterance)
        or inputs.sentiment_stats.positive_pct > 0.0
        or inputs.sentiment_stats.negative_pct > 0.0
        or inputs.sentiment_stats.mean_valence != 0.0
    )
    level = inputs.safety_recommendation.level if inputs.safety_recommendation is not None else None
    safety_signal = inputs.safety_recommendation is not None and (
        level == SafetyLevel.UNSAFE
        or bool(inputs.safety_recommendation.top_signals)
        or (level == SafetyLevel.CAUTION and not inputs.unavailable_inputs)
    )
    return not (
        inputs.harmful_content_matches
        or inputs.web_risk_findings
        or image_signal
        or video_signal
        or inputs.flashpoint_matches
        or scd_signal
        or claims_signal
        or inputs.known_misinformation
        or inputs.subjective_claims
        or sentiment_signal
        or safety_signal
    )


def pick_stock_phrase(job_id: UUID) -> str:
    index = int(job_id.hex, 16) % len(_STOCK_PHRASES)
    return _STOCK_PHRASES[index]


def pick_degraded_stock_phrase(job_id: UUID) -> str:
    index = int(job_id.hex, 16) % len(_DEGRADED_STOCK_PHRASES)
    return _DEGRADED_STOCK_PHRASES[index]


def pick_signal_fallback_phrase(job_id: UUID) -> str:
    index = int(job_id.hex, 16) % len(_SIGNAL_FALLBACK_PHRASES)
    return _SIGNAL_FALLBACK_PHRASES[index]


def _serialize_inputs(inputs: HeadlineSummaryInputs) -> str:
    payload = {
        "safety_recommendation": _model_dump(inputs.safety_recommendation)
        if inputs.safety_recommendation is not None
        else None,
        "harmful_content_matches": [_model_dump(match) for match in inputs.harmful_content_matches],
        "web_risk_findings": [_model_dump(finding) for finding in inputs.web_risk_findings],
        "image_moderation_matches": [
            _model_dump(match) for match in inputs.image_moderation_matches
        ],
        "video_moderation_matches": [
            _model_dump(match) for match in inputs.video_moderation_matches
        ],
        "flashpoint_matches": [_model_dump(match) for match in inputs.flashpoint_matches],
        "scd": _model_dump(inputs.scd) if inputs.scd is not None else None,
        "claims_report": _model_dump(inputs.claims_report)
        if inputs.claims_report is not None
        else None,
        "known_misinformation": [_model_dump(match) for match in inputs.known_misinformation],
        "sentiment_stats": _model_dump(inputs.sentiment_stats)
        if inputs.sentiment_stats is not None
        else None,
        "subjective_claims": [_model_dump(claim) for claim in inputs.subjective_claims],
        "page_title": inputs.page_title,
        "page_kind": inputs.page_kind.value,
        "unavailable_inputs": list(inputs.unavailable_inputs),
    }
    return json.dumps(payload)


def _default_headline_model(_settings: Settings | object) -> Any:
    return ModelId.from_pydantic_ai(DEFAULT_HEADLINE_MODEL).to_pydantic_ai_model()


async def _run_default_headline_summary_agent(
    inputs: HeadlineSummaryInputs,
    *,
    model: Any,
) -> HeadlineSummary:
    result = await headline_summary_agent.run(
        _serialize_inputs(inputs),
        model=model,
        instructions=HEADLINE_SUMMARY_SYSTEM_PROMPT,
        model_settings=ModelSettings(temperature=0.0),
    )
    return cast(HeadlineSummary, result.output)


async def run_headline_summary(
    inputs: HeadlineSummaryInputs,
    settings: Settings | object,
    job_id: UUID,
) -> HeadlineSummary:
    if all_inputs_clear(inputs):
        text = (
            pick_degraded_stock_phrase(job_id)
            if inputs.unavailable_inputs
            else pick_stock_phrase(job_id)
        )
        return HeadlineSummary(
            text=text,
            kind="stock",
            unavailable_inputs=list(inputs.unavailable_inputs),
        )

    try:
        model_output = await _run_default_headline_summary_agent(
            inputs,
            model=_default_headline_model(settings),
        )
    except Exception:
        return HeadlineSummary(
            text=pick_signal_fallback_phrase(job_id),
            kind="stock",
            unavailable_inputs=list(inputs.unavailable_inputs),
        )
    return HeadlineSummary(
        text=model_output.text,
        kind="synthesized",
        unavailable_inputs=list(inputs.unavailable_inputs),
    )


__all__ = [
    "DEFAULT_HEADLINE_MODEL",
    "HEADLINE_SUMMARY_SYSTEM_PROMPT",
    "HeadlineSummaryInputs",
    "all_inputs_clear",
    "headline_summary_agent",
    "pick_degraded_stock_phrase",
    "pick_signal_fallback_phrase",
    "pick_stock_phrase",
    "run_headline_summary",
]
