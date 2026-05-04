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
from src.services.gemini_agent import build_agent, run_vertex_agent_with_retry
from src.services.vertex_limiter import vertex_slot

HEADLINE_SUMMARY_SYSTEM_PROMPT = """You synthesize a 1-2 sentence narrative lead for one analyzed page.
Use the inputs (safety verdict, conversation dynamics, claims, and sentiment)
to describe the page's overall thrust and dynamic — the core story, not an
inventory of available signals.
By default, write one pithy sentence.
Only add a second sentence when it contributes a distinct high-signal point.

Do not write like a tabloid headline.
Do not list which specific sections were missing or absent — never name slot
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

# Deterministic phrasing for the degraded-coverage path: every available
# signal came back clear, but at least one section failed to report. We
# must NOT claim global all-clear here, so the wording is qualified to
# reflect partial coverage. Same hash-mod-len selection as the all-clear
# pool so a given job_id is stable across re-polls.
_DEGRADED_STOCK_PHRASES: tuple[str, ...] = (
    "Coverage was incomplete; nothing flagged in the analyzed sections.",
    "Partial analysis; the available checks did not surface anything.",
    "Limited coverage this run; analyzed sections came back clean.",
    "Some sections did not report; the rest are unremarkable.",
    "Reduced coverage; the completed analyses are quiet.",
    "Analysis was partial; what completed had nothing to flag.",
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
    treats as "nothing to flag" (see SAFETY_EMPTINESS / OPINIONS_EMPTINESS
    in Sidebar.tsx) so the stock-phrase short-circuit and the rendered
    sidebar agree on emptiness — a stock "Nothing of note" headline must
    not coexist with a sidebar section the UI considers non-empty.
    """
    # Sidebar treats any image/video match (regardless of max_likelihood)
    # as a non-empty section, so the headline must as well.
    image_signal = bool(inputs.image_moderation_matches)
    video_signal = bool(inputs.video_moderation_matches)
    # Sidebar TONE_EMPTINESS only treats SCD as empty when
    # insufficient_conversation is true AND tone_labels and
    # per_speaker_notes are both empty. So insufficient_conversation alone
    # is not enough — a report flagged insufficient that still carries
    # legacy labels/notes renders the section in the sidebar and must be
    # treated as a signal here.
    scd_signal = inputs.scd is not None and (
        not inputs.scd.insufficient_conversation
        or bool(inputs.scd.tone_labels)
        or bool(inputs.scd.per_speaker_notes)
    )
    claims_signal = inputs.claims_report is not None and bool(inputs.claims_report.deduped_claims)
    # Sidebar OPINIONS_EMPTINESS treats sentiment as non-empty when any of
    # per_utterance, positive_pct, negative_pct, or mean_valence is set.
    # An all-neutral page (per_utterance>0, neutral_pct=100) renders the
    # section, so a stock all-clear headline above it would contradict
    # what's on screen.
    sentiment_signal = inputs.sentiment_stats is not None and (
        bool(inputs.sentiment_stats.per_utterance)
        or inputs.sentiment_stats.positive_pct > 0.0
        or inputs.sentiment_stats.negative_pct > 0.0
        or inputs.sentiment_stats.mean_valence != 0.0
    )
    # `run_safety_recommendation` emits CAUTION (not SAFE) for purely
    # coverage-degraded jobs — the prompt classes "partial data" as a
    # caution trigger. When the only reason for CAUTION is missing
    # coverage (no top_signals AND unavailable_inputs is non-empty), the
    # headline must NOT treat it as a real signal — otherwise the
    # clear-but-degraded shape skips the deterministic degraded-stock
    # branch and goes to the model path. UNSAFE is always a signal;
    # CAUTION counts when there are concrete top_signals OR when
    # coverage is complete (so the caution is sourced from a real
    # finding, not from the coverage gap itself).
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
    """Pick a deterministic stock phrase for ``job_id``.

    Uses ``int(job_id.hex, 16) % len(_STOCK_PHRASES)`` so the same job
    always produces the same phrase but different jobs spread across the
    pool.
    """
    index = int(job_id.hex, 16) % len(_STOCK_PHRASES)
    return _STOCK_PHRASES[index]


def pick_degraded_stock_phrase(job_id: UUID) -> str:
    """Pick a deterministic degraded-coverage stock phrase for ``job_id``.

    Same hash-mod-len selection as ``pick_stock_phrase`` so re-polls of
    the same job render the same phrase, but drawn from the qualified
    pool that does not claim global all-clear.
    """
    index = int(job_id.hex, 16) % len(_DEGRADED_STOCK_PHRASES)
    return _DEGRADED_STOCK_PHRASES[index]


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


async def run_headline_summary(
    inputs: HeadlineSummaryInputs,
    settings: Settings,
    job_id: UUID,
) -> HeadlineSummary:
    """Produce a ``HeadlineSummary`` for the analyzed page.

    Three deterministic branches; the model is only called for the
    third.

    1. All signals empty/clear AND no missing coverage: pick from
       ``_STOCK_PHRASES`` (the reassuring all-clear pool). ``kind="stock"``.
    2. All signals empty/clear BUT coverage was incomplete: pick from
       ``_DEGRADED_STOCK_PHRASES`` (qualified phrasing that does not
       claim global all-clear). ``kind="stock"``. This branch is what
       prevents the lying-about-coverage failure mode where every
       analyzed section happened to be clear but the analysis itself
       was partial.
    3. Otherwise: call the synthesis agent. Force ``kind="synthesized"``
       and the caller-supplied ``unavailable_inputs`` so callers can
       trust the discriminator and the coverage list regardless of
       what the model echoes back. The system prompt forbids slot-name
       enumeration and forbids all-clear wording when
       ``unavailable_inputs`` is non-empty.
    """
    if all_inputs_clear(inputs):
        if inputs.unavailable_inputs:
            return HeadlineSummary(
                text=pick_degraded_stock_phrase(job_id),
                kind="stock",
                unavailable_inputs=list(inputs.unavailable_inputs),
            )
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
            tier="synthesis",
        ),
    )
    async with vertex_slot(settings):
        result = await run_vertex_agent_with_retry(agent, _serialize_inputs(inputs))
    model_output = cast(HeadlineSummary, result.output)
    return HeadlineSummary(
        text=model_output.text,
        kind="synthesized",
        unavailable_inputs=list(inputs.unavailable_inputs),
    )
