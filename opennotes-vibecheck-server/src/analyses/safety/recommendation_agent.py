"""Aggregate safety recommendation agent."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, cast

import logfire

from src.analyses.safety._schemas import (
    Divergence,
    HarmfulContentMatch,
    ImageModerationMatch,
    SafetyLevel,
    SafetyRecommendation,
    VideoModerationMatch,
    WebRiskFinding,
)
from src.analyses.safety.vision_client import FLAG_THRESHOLD
from src.config import Settings
from src.services.gemini_agent import build_agent, run_vertex_agent_with_retry
from src.services.vertex_limiter import vertex_slot

RECOMMENDATION_SYSTEM_PROMPT = """You synthesize the safety findings for one scraped page.
Inputs are already-filtered safety matches from four analyses: text moderation,
Web Risk, image SafeSearch, and video SafeSearch. Return one SafetyRecommendation.

- Web Risk findings for the same URL being analyzed are pre-filtered before
  this prompt. The Web Risk findings you see here are for external or
  non-matching URLs only.

Use these levels:
- safe: all available inputs are clear.
- mild: exactly one supported low-severity signal after context review, such as
  a topic-match-only moderation hit, one isolated Web Risk
  POTENTIALLY_HARMFUL_APPLICATION finding, or one low image/video
  max_likelihood score from verified frames.
- caution: partial data, unavailable inputs, or multiple low-severity signals
  together when at least one remains supported after context review.
- unsafe: verified high-risk signals such as Web Risk MALWARE, multiple
  high-score text flags, or high image/video max_likelihood scores from real
  frames.

Tier-selection rules:
- If every raw signal is judged a false positive or otherwise discounted by
  context, unavailable_inputs is empty, and there are no Web Risk findings or
  verified visual findings, return `safe`.
- Multiple low-severity signals together requires at least one remains supported after context review.
- Exactly one supported low-severity signal can be `mild`.
- Multiple supported low-severity signals can still justify `caution`.

Important caveats:
- top_signals entries must be short human-readable noun phrases or sentences;
  never raw category names, float scores, or enum labels. Prefer concise phrases
  such as "Violent topics", "Adult imagery", or "Phishing link". For
  false-positive moderation, use
  "Text moderation flags triggered, but judged to be false positives."
- In false-positive-heavy caution cases, do not lead top_signals with dismissed raw
  moderation scores.
- Keep raw category names and float scores in rationale only when they help
  explain the decision; do not put them in top_signals.
- top_signals from raw model output must be sanitized server-side before being
  returned.
- Divergence signal_source, signal_detail, and reason must also be short,
  display-ready human-readable text. Do not put raw category names, snake_case
  identifiers, float scores, or enum labels in divergence fields. Use labels
  such as "Text moderation", "Web Risk", "Image moderation", "Video moderation",
  or "Combined signals".
- Vision SafeSearch enum labels are not available downstream. Describe image/video signals
  in rationale with float scores only, such as "adult max_likelihood 0.91";
  never mention enum labels like VERY_LIKELY.
- A video match with sampling_inconclusive=true means sampling failed or returned
  no segment-level findings. This is incomplete evidence. It is not a supported video safety signal,
  and it must not by itself justify `caution` or `unsafe`. If no other
  supported safety signal remains, return `safe` and explain that video analysis
  was inconclusive.
- Echo the unavailable_inputs list exactly in the output.
- Use the `divergences` field to record how your final verdict differs from the raw
  signals in inputs:
  - If your final level and rationale align with the raw signals, set
    `divergences: []`.
  - If you discount a raw signal due to context, you MUST emit a corresponding direction="discounted" divergence and include:
    - discounted sensitive-topic signal when the text is a sensitive topic that is
      the page subject or intended educational framing (ex: public-health article),
    - discounted external Web Risk finding when surrounding context makes the
      destination less concerning than the raw threat type alone,
    - discounted image/video signal when visual findings are likely
      instructional, educational, documentary, or in-domain context.
  - If you escalate beyond the weakest raw signals, add direction="escalated" when
    combined low-signal cues or context justify caution/unsafe:
    - multiple mild signals together (topic + POTENTIALLY_HARMFUL_APPLICATION +
      low visual concern) producing caution,
    - weak visual score plus weak textual cues and in-context risk alignment.
- Divergences from upstream outputs must also be sanitized server-side.

Only emit divergences that are directly supported by inputs. Do not fabricate
divergences."""


@dataclass
class SafetyRecommendationInputs:
    harmful_content_matches: list[HarmfulContentMatch]
    web_risk_findings: list[WebRiskFinding]
    image_moderation_matches: list[ImageModerationMatch]
    video_moderation_matches: list[VideoModerationMatch]
    unavailable_inputs: list[str]
    source_url: str | None = None


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _serialize_inputs(inputs: SafetyRecommendationInputs) -> str:
    video_matches: list[dict[str, Any]] = []
    for match in inputs.video_moderation_matches:
        dumped = cast(dict[str, Any], _model_dump(match))
        dumped["sampling_inconclusive"] = (
            match.max_likelihood == 1.0 and len(match.segment_findings) == 0
        )
        video_matches.append(dumped)

    payload = {
        "harmful_content_matches": [_model_dump(match) for match in inputs.harmful_content_matches],
        "web_risk_findings": [_model_dump(finding) for finding in inputs.web_risk_findings],
        "image_moderation_matches": [
            _model_dump(match) for match in inputs.image_moderation_matches
        ],
        "video_moderation_matches": video_matches,
        "unavailable_inputs": list(inputs.unavailable_inputs),
        "source_url": inputs.source_url,
    }
    return json.dumps(payload)


_RAW_TEXT_MOD_SCORE_RE = re.compile(
    r"^(?:text\s*:\s*)?[a-z][a-z /-]*\s+(?:score\s+)?\d+\.\d+$",
    re.IGNORECASE,
)
_VISION_FLOAT_RE = re.compile(
    r"(adult|violence|racy|medical|spoof)\s+(max_likelihood|score)\s+\d+\.\d+",
    re.IGNORECASE,
)
_VISION_ENUM_RE = re.compile(
    r"\b(VERY_LIKELY|LIKELY|POSSIBLE|UNLIKELY|VERY_UNLIKELY)\b",
)
_RAW_SCORE_RE = re.compile(r"\b\d+\.\d+\b")
_RAW_ENUM_RE = re.compile(
    r"\b(?:VERY_LIKELY|LIKELY|POSSIBLE|UNLIKELY|VERY_UNLIKELY|POTENTIALLY_HARMFUL_APPLICATION|SOCIAL_ENGINEERING|UNWANTED_SOFTWARE|MALWARE)\b",
)
_RAW_IDENTIFIER_RE = re.compile(
    r"(?:^|[\s,;:])(?:[a-z]+(?:_[a-z]+)+)(?:$|[\s,;:])",
    re.IGNORECASE,
)
_RAW_PROVIDER_RE = re.compile(r"\b(?:openai|gcp)\b", re.IGNORECASE)
_RAW_MODERATION_CATEGORIES: tuple[str, ...] = (
    "violence",
    "violence/graphic",
    "sexual",
    "sexual/minors",
    "hate",
    "hate/threatening",
    "harassment",
    "harassment/threatening",
    "self-harm",
    "self-harm/intent",
    "self-harm/instructions",
    "illicit",
    "illicit/violent",
)
_SOURCE_LABELS: dict[str, str] = {
    "web_risk": "Web Risk",
    "web risk": "Web Risk",
    "text": "Text moderation",
    "text_moderation": "Text moderation",
    "text moderation": "Text moderation",
    "text_moderation/openai": "Text moderation",
    "text_moderation/gcp": "Text moderation",
    "openai": "Text moderation",
    "gcp": "Text moderation",
    "image": "Image moderation",
    "image_moderation": "Image moderation",
    "image moderation": "Image moderation",
    "video": "Video moderation",
    "video_moderation": "Video moderation",
    "video moderation": "Video moderation",
    "combined": "Combined signals",
    "combined_signals": "Combined signals",
    "combined signals": "Combined signals",
}
_KNOWN_SOURCE_LABELS = frozenset(_SOURCE_LABELS.values())
_SANITIZED_SOURCE_FALLBACK = "Safety signal"
_SANITIZED_DETAIL_FALLBACK = "Signal detail adjusted"
_SANITIZED_REASON_FALLBACKS = {
    "discounted": "Signal context discounted",
    "escalated": "Signal context escalated",
}
_SANITIZER_PLACEHOLDER = "Verified concern requires review"
_PLACEHOLDER_LEVELS = {SafetyLevel.CAUTION, SafetyLevel.UNSAFE}
_FALSE_POSITIVE_TOP_SIGNAL = (
    "Text moderation flags triggered, but judged to be false positives."
)


def _is_raw_signal(value: str) -> bool:
    stripped = value.strip()
    if _RAW_TEXT_MOD_SCORE_RE.match(stripped):
        return True
    if _VISION_FLOAT_RE.search(stripped):
        return True
    return bool(_VISION_ENUM_RE.search(stripped))


def _contains_raw_divergence_token(value: str) -> bool:
    normalized = value.strip()
    if _RAW_SCORE_RE.search(normalized):
        return True
    if _RAW_ENUM_RE.search(normalized):
        return True
    if _RAW_IDENTIFIER_RE.search(normalized):
        return True
    if _RAW_PROVIDER_RE.search(normalized):
        return True
    normalized_lower = normalized.lower()
    for category in _RAW_MODERATION_CATEGORIES:
        category_forms = (
            category,
            category.replace("_", " "),
            category.replace("/", "_"),
            category.replace("/", " "),
        )
        for form in category_forms:
            if form and re.search(
                rf"(?:^|[^a-z0-9_-]){re.escape(form)}(?:$|[^a-z0-9_-])",
                normalized_lower,
            ):
                return True
    return False


def _normalize_divergence_field(value: str, fallback: str) -> tuple[str, bool]:
    trimmed = value.strip()
    if not trimmed:
        return fallback, True
    if _contains_raw_divergence_token(trimmed):
        return fallback, True
    return re.sub(r"\s+", " ", trimmed), False


def _sanitize_divergence_source(value: str) -> tuple[str, bool]:
    raw = value.strip()
    if not raw:
        return _SANITIZED_SOURCE_FALLBACK, True

    mapped = _SOURCE_LABELS.get(raw.lower())
    if mapped is not None:
        return mapped, False

    if "/" in raw:
        return _SANITIZED_SOURCE_FALLBACK, True

    if _contains_raw_divergence_token(raw):
        return _SANITIZED_SOURCE_FALLBACK, True

    return re.sub(r"\s+", " ", raw), False


def _sanitize_divergence(divergence: Divergence) -> tuple[Divergence, int]:
    replacement_count = 0

    source, source_replaced = _sanitize_divergence_source(divergence.signal_source)
    if source_replaced:
        replacement_count += 1

    detail, detail_replaced = _normalize_divergence_field(
        divergence.signal_detail,
        _SANITIZED_DETAIL_FALLBACK,
    )
    if detail_replaced:
        replacement_count += 1

    fallback = _SANITIZED_REASON_FALLBACKS[divergence.direction]
    reason_text = re.sub(
        r"^\s*(?:escalated|discounted)\s*:?\s*",
        "",
        divergence.reason,
        flags=re.IGNORECASE,
    )
    reason, reason_replaced = _normalize_divergence_field(reason_text, fallback)
    if reason_replaced:
        replacement_count += 1

    return (
        Divergence(
            direction=divergence.direction,
            signal_source=source,
            signal_detail=detail,
            reason=reason,
        ),
        replacement_count,
    )


def _sanitize_divergences(
    recommendation: SafetyRecommendation,
) -> tuple[
    SafetyRecommendation,
    int,
    dict[str, int],
    dict[str, Any],
]:
    sanitized: list[Divergence] = []
    fallback_count = 0

    for divergence in recommendation.divergences:
        sanitized_divergence, replacements = _sanitize_divergence(divergence)
        fallback_count += replacements
        sanitized.append(sanitized_divergence)

    if not recommendation.divergences:
        return (
            recommendation,
            0,
            {"discounted": 0, "escalated": 0},
            {"known": {}, "unknown_count": 0},
        )

    sanitized_recommendation = (
        recommendation
        if sanitized == list(recommendation.divergences)
        else recommendation.model_copy(update={"divergences": sanitized})
    )
    attrs = safety_recommendation_divergence_attrs(
        sanitized_recommendation,
        sanitizer_replacement_count=fallback_count,
    )

    if sanitized == list(recommendation.divergences):
        return (
            recommendation,
            fallback_count,
            attrs["divergence_direction_distribution"],
            attrs["divergence_source_distribution"],
        )

    if fallback_count > 0:
        logfire.warning(
            "safety_recommendation_divergence_sanitized",
            replacement_count=fallback_count,
            divergence_count=len(sanitized),
        )

    return (
        sanitized_recommendation,
        fallback_count,
        attrs["divergence_direction_distribution"],
        attrs["divergence_source_distribution"],
    )


def safety_recommendation_divergence_attrs(
    recommendation: SafetyRecommendation,
    *,
    sanitizer_replacement_count: int = 0,
) -> dict[str, Any]:
    direction_distribution: Counter[str] = Counter()
    known_sources: Counter[str] = Counter()
    unknown_count = 0

    for divergence in recommendation.divergences:
        direction_distribution[divergence.direction] += 1
        if divergence.signal_source in _KNOWN_SOURCE_LABELS:
            known_sources[divergence.signal_source] += 1
        else:
            unknown_count += 1

    return {
        "divergence_count": len(recommendation.divergences),
        "divergence_direction_distribution": {
            "discounted": direction_distribution["discounted"],
            "escalated": direction_distribution["escalated"],
        },
        "divergence_source_distribution": {
            "known": dict(known_sources),
            "unknown_count": unknown_count,
        },
        "divergence_sanitizer_replacement_count": sanitizer_replacement_count,
    }


def _sanitize_top_signals(recommendation: SafetyRecommendation) -> SafetyRecommendation:
    original = list(recommendation.top_signals)
    kept: list[str] = []
    for entry in original:
        if _is_raw_signal(entry):
            logfire.warning(
                "safety_recommendation_top_signal_stripped",
                level=recommendation.level.value,
            )
            continue
        kept.append(entry)
    if not kept and original and recommendation.level in _PLACEHOLDER_LEVELS:
        kept = [_SANITIZER_PLACEHOLDER]
    if kept == original:
        return recommendation
    return recommendation.model_copy(update={"top_signals": kept})


def _has_guardrail_downgrade_blocker(
    recommendation: SafetyRecommendation,
    inputs: SafetyRecommendationInputs,
) -> bool:
    if inputs.unavailable_inputs:
        return True
    if inputs.web_risk_findings:
        return True
    if any(divergence.direction == "escalated" for divergence in recommendation.divergences):
        return True
    if any(_has_verified_video_signal(match) for match in inputs.video_moderation_matches):
        return True
    return any(
        match.flagged or match.max_likelihood >= FLAG_THRESHOLD
        for match in inputs.image_moderation_matches
    )


def _is_inconclusive_video_match(match: VideoModerationMatch) -> bool:
    return match.max_likelihood == 1.0 and not match.segment_findings


def _has_verified_video_signal(match: VideoModerationMatch) -> bool:
    return any(
        finding.flagged or finding.max_likelihood >= FLAG_THRESHOLD
        for finding in match.segment_findings
    )


def _discounted_text_signal_count(
    recommendation: SafetyRecommendation,
    inputs: SafetyRecommendationInputs,
) -> int:
    if not inputs.harmful_content_matches:
        return 0
    if (
        not recommendation.divergences
        and recommendation.top_signals == [_FALSE_POSITIVE_TOP_SIGNAL]
    ):
        return len(inputs.harmful_content_matches)

    discounted = sum(
        1
        for divergence in recommendation.divergences
        if divergence.direction == "discounted"
        and divergence.signal_source == "Text moderation"
    )
    return min(discounted, len(inputs.harmful_content_matches))


def _apply_recommendation_guardrail(
    recommendation: SafetyRecommendation,
    inputs: SafetyRecommendationInputs,
) -> tuple[SafetyRecommendation, str | None]:
    if (
        recommendation.level is not SafetyLevel.CAUTION
        or _has_guardrail_downgrade_blocker(recommendation, inputs)
    ):
        return recommendation, None

    has_inconclusive_video = any(
        _is_inconclusive_video_match(match)
        for match in inputs.video_moderation_matches
    )
    if not inputs.harmful_content_matches:
        if not has_inconclusive_video:
            return recommendation, None
        return (
            recommendation.model_copy(
                update={
                    "level": SafetyLevel.SAFE,
                    "rationale": (
                        "Video analysis was inconclusive; no verified safety "
                        "concern remains."
                    ),
                    "top_signals": [],
                }
            ),
            "only_video_sampling_inconclusive",
        )

    discounted_text_signals = _discounted_text_signal_count(recommendation, inputs)
    supported_text_signals = len(inputs.harmful_content_matches) - discounted_text_signals

    if supported_text_signals == 0:
        return (
            recommendation.model_copy(
                update={
                    "level": SafetyLevel.SAFE,
                    "rationale": (
                        "Raw safety signals were discounted by context; no supported "
                        "safety concern remains."
                    ),
                    "top_signals": [],
                }
            ),
            "all_text_signals_discounted",
        )

    if supported_text_signals == 1:
        return (
            recommendation.model_copy(
                update={
                    "level": SafetyLevel.MILD,
                    "rationale": (
                        "One low-severity safety signal remains after context review."
                    ),
                }
            ),
            "one_supported_low_severity_signal",
        )

    return recommendation, None


async def run_safety_recommendation(
    inputs: SafetyRecommendationInputs,
    settings: Settings,
) -> SafetyRecommendation:
    with logfire.span(
        "vibecheck.safety_recommendation.run",
        harmful_input_count=len(inputs.harmful_content_matches),
        web_risk_input_count=len(inputs.web_risk_findings),
        image_input_count=len(inputs.image_moderation_matches),
        video_input_count=len(inputs.video_moderation_matches),
        unavailable_input_count=len(inputs.unavailable_inputs),
        source_url_present=inputs.source_url is not None,
    ) as span:
        agent = cast(
            Any,
            build_agent(
                settings,
                output_type=SafetyRecommendation,
                system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
                name="vibecheck.safety_recommendation",
                tier="synthesis",
            ),
        )
        async with vertex_slot(settings):
            result = await run_vertex_agent_with_retry(agent, _serialize_inputs(inputs))
        output = cast(SafetyRecommendation, result.output)

        sanitized_output = _sanitize_top_signals(output)
        (
            sanitized_output,
            replacement_count,
            _direction_distribution,
            _source_distribution,
        ) = _sanitize_divergences(sanitized_output)

        if settings.VIBECHECK_SAFETY_RECOMMENDATION_GUARDRAIL_ENABLED:
            original_level = sanitized_output.level
            sanitized_output, guardrail_reason = _apply_recommendation_guardrail(
                sanitized_output,
                inputs,
            )
            if guardrail_reason is not None:
                logfire.warning(
                    "safety_recommendation_guardrail_downgrade",
                    original_level=original_level.value,
                    downgraded_level=sanitized_output.level.value,
                    reason=guardrail_reason,
                )

        span.set_attributes(
            safety_recommendation_divergence_attrs(
                sanitized_output,
                sanitizer_replacement_count=replacement_count,
            )
        )

        return sanitized_output
