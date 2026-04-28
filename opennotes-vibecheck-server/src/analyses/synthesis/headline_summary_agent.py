"""Synthesis agent producing the 1-2 sentence sidebar headline.

Aggregates the structured outputs of every analysis section (safety, tone,
claims, opinions) and emits a single ``HeadlineSummary``. When every input
is empty/clear/neutral, the agent is bypassed and a deterministic stock
phrase keyed by ``job_id`` is returned, so a quiet page never burns a
model call and never produces a sentence that enumerates which signals
were absent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.opinions._schemas import SentimentStatsReport, SubjectiveClaim
from src.analyses.safety._schemas import (
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.schemas import HeadlineSummary, PageKind
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport
from src.config import Settings
from src.services.gemini_agent import build_agent

HEADLINE_SUMMARY_SYSTEM_PROMPT = """You synthesize a 1-2 sentence summation of one analyzed page.
Inputs include the safety verdict, conversation dynamics, claims, and sentiment.
Write a single perceptive opening line. Do not write like a tabloid headline.
Do not list which signals were missing or absent. If inputs are minimal, be direct
and brief. Output a HeadlineSummary with `kind` set to "synthesized" - the caller
will overwrite kind anyway, but always set it."""


_STOCK_PHRASES: tuple[str, ...] = (
    "Nothing of note in this content.",
    "Routine content with no signals to flag.",
    "Calm content; little to call out.",
    "Standard content; nothing remarkable.",
    "Quiet page; nothing to highlight.",
    "An ordinary page; not much to say.",
)


@dataclass
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


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def all_inputs_clear(inputs: HeadlineSummaryInputs) -> bool:
    """Return True when no analysis section produced a notable signal.

    The headline agent is bypassed in this case in favour of a deterministic
    stock phrase. The thresholds below intentionally mirror what the UI
    treats as "nothing to flag" so the stock-phrase short-circuit and the
    rendered sidebar agree on emptiness.
    """
    image_signal = any(
        match.max_likelihood > 0.5 for match in inputs.image_moderation_matches
    )
    video_signal = any(
        match.max_likelihood > 0.5 for match in inputs.video_moderation_matches
    )
    scd_signal = (
        inputs.scd is not None and not inputs.scd.insufficient_conversation
    )
    claims_signal = (
        inputs.claims_report is not None
        and bool(inputs.claims_report.deduped_claims)
    )
    sentiment_signal = inputs.sentiment_stats is not None and (
        inputs.sentiment_stats.positive_pct > 0.0
        or inputs.sentiment_stats.negative_pct > 0.0
    )
    safety_signal = inputs.safety_recommendation is not None and (
        inputs.safety_recommendation.level != SafetyLevel.SAFE
        or bool(inputs.safety_recommendation.top_signals)
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
    """Pick a deterministic stock phrase for ``job_id``.

    Uses ``int(job_id.hex, 16) % len(_STOCK_PHRASES)`` so the same job
    always produces the same phrase but different jobs spread across the
    pool.
    """
    index = int(job_id.hex, 16) % len(_STOCK_PHRASES)
    return _STOCK_PHRASES[index]


def _serialize_inputs(inputs: HeadlineSummaryInputs) -> str:
    payload = {
        "safety_recommendation": _model_dump(inputs.safety_recommendation)
        if inputs.safety_recommendation is not None
        else None,
        "harmful_content_matches": [
            _model_dump(match) for match in inputs.harmful_content_matches
        ],
        "web_risk_findings": [
            _model_dump(finding) for finding in inputs.web_risk_findings
        ],
        "image_moderation_matches": [
            _model_dump(match) for match in inputs.image_moderation_matches
        ],
        "video_moderation_matches": [
            _model_dump(match) for match in inputs.video_moderation_matches
        ],
        "flashpoint_matches": [
            _model_dump(match) for match in inputs.flashpoint_matches
        ],
        "scd": _model_dump(inputs.scd) if inputs.scd is not None else None,
        "claims_report": _model_dump(inputs.claims_report)
        if inputs.claims_report is not None
        else None,
        "known_misinformation": [
            _model_dump(match) for match in inputs.known_misinformation
        ],
        "sentiment_stats": _model_dump(inputs.sentiment_stats)
        if inputs.sentiment_stats is not None
        else None,
        "subjective_claims": [
            _model_dump(claim) for claim in inputs.subjective_claims
        ],
        "page_title": inputs.page_title,
        "page_kind": inputs.page_kind.value,
        "unavailable_inputs": list(inputs.unavailable_inputs),
    }
    return json.dumps(payload)


async def run_headline_summary(
    inputs: HeadlineSummaryInputs,
    settings: Settings,
    job_id: UUID,
) -> HeadlineSummary:
    """Produce a ``HeadlineSummary`` for the analyzed page.

    Short-circuits to a deterministic stock phrase (``kind="stock"``) when
    every input is empty/clear/neutral; otherwise calls the synthesis
    agent and forces ``kind="synthesized"`` plus the input-supplied
    ``unavailable_inputs`` so callers can trust the discriminator and the
    coverage list regardless of what the model echoes back.
    """
    if all_inputs_clear(inputs):
        return HeadlineSummary(
            text=pick_stock_phrase(job_id),
            kind="stock",
            unavailable_inputs=list(inputs.unavailable_inputs),
        )

    agent = cast(
        Any,
        build_agent(
            settings,
            output_type=HeadlineSummary,
            system_prompt=HEADLINE_SUMMARY_SYSTEM_PROMPT,
            name="vibecheck.headline_summary",
        ),
    )
    result = await agent.run(_serialize_inputs(inputs))
    model_output = cast(HeadlineSummary, result.output)
    return HeadlineSummary(
        text=model_output.text,
        kind="synthesized",
        unavailable_inputs=list(inputs.unavailable_inputs),
    )
