"""Pure-function derivation of the gallery preview blurb (TASK-1485.02).

Computes a short (~140 char) summary of the most interesting finding in
an assembled SidebarPayload. Persisted on `vibecheck_jobs.preview_description`
at job-completion time so the Recently Vibe Checked gallery never recomputes
on poll.

Priority order (parent-defined; first branch with usable signal wins):
1. HeadlineSummary text
2. SafetyRecommendation rationale (level + rationale)
3. Top harmful_content_match (max_score DESC)
4. Top FlashpointMatch (derailment_score DESC)
5. Top DedupedClaim (occurrence_count DESC, author_count DESC)
6. Dominant sentiment (largest pct)
7. page_title (from DerivationContext)
8. first_utterance_text (from DerivationContext)
9. Last-resort placeholder so the column is never empty.

Output is always non-empty and hard-capped at 140 chars (truncate with `…`).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.analyses.schemas import SidebarPayload

PREVIEW_MAX_LEN = 140
_ELLIPSIS = "…"
_FALLBACK_PLACEHOLDER = "Analysis complete."


@dataclass(frozen=True)
class DerivationContext:
    """Out-of-band fields not on SidebarPayload but needed for fallbacks.

    `page_title` and `first_utterance_text` are loaded once at finalize
    time from `vibecheck_scrapes` / `vibecheck_job_utterances` and passed
    in alongside the assembled payload.
    """

    page_title: str | None
    first_utterance_text: str | None


def _truncate(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    if len(text) <= PREVIEW_MAX_LEN:
        return text
    return text[: PREVIEW_MAX_LEN - 1].rstrip() + _ELLIPSIS


def _from_safety_recommendation(payload: SidebarPayload) -> str | None:
    rec = payload.safety.recommendation
    if rec is None or not rec.rationale.strip():
        return None
    level = rec.level.value.capitalize()
    return f"{level}: {rec.rationale}"


def _from_headline_summary(payload: SidebarPayload) -> str | None:
    headline = payload.headline
    if headline is None or not headline.text.strip():
        return None
    return headline.text


def _from_harmful_content(payload: SidebarPayload) -> str | None:
    matches = payload.safety.harmful_content_matches
    if not matches:
        return None
    top = max(matches, key=lambda m: m.max_score)
    category = (
        top.flagged_categories[0]
        if top.flagged_categories
        else (next(iter(top.categories), "harmful content"))
    )
    return f"Flagged {category} content (score {top.max_score:.2f})."


def _from_flashpoint(payload: SidebarPayload) -> str | None:
    matches = payload.tone_dynamics.flashpoint_matches
    if not matches:
        return None
    top = max(matches, key=lambda m: m.derailment_score)
    return f"{top.risk_level.value} conversation: {top.reasoning}".strip()


def _from_top_claim(payload: SidebarPayload) -> str | None:
    claims = payload.facts_claims.claims_report.deduped_claims
    if not claims:
        return None
    top = max(claims, key=lambda c: (c.occurrence_count, c.author_count))
    return (
        f"Top claim ({top.occurrence_count}x): {top.canonical_text}"
        if top.canonical_text.strip()
        else None
    )


def _from_sentiment(payload: SidebarPayload) -> str | None:
    stats = payload.opinions_sentiments.opinions_report.sentiment_stats
    pcts = {
        "positive": stats.positive_pct,
        "negative": stats.negative_pct,
        "neutral": stats.neutral_pct,
    }
    label, pct = max(pcts.items(), key=lambda kv: kv[1])
    if pct <= 0:
        return None
    return f"{round(pct)}% {label} sentiment overall."


def derive_preview_description(
    payload: SidebarPayload, ctx: DerivationContext
) -> str:
    """Derive the gallery preview blurb from an assembled payload.

    Pure function: deterministic, no I/O, no clock, no random. Same input
    always yields the same string. Always returns non-empty string with
    len <= PREVIEW_MAX_LEN.
    """
    candidates = (
        _from_headline_summary(payload),
        _from_safety_recommendation(payload),
        _from_harmful_content(payload),
        _from_flashpoint(payload),
        _from_top_claim(payload),
        _from_sentiment(payload),
        ctx.page_title,
        ctx.first_utterance_text,
        _FALLBACK_PLACEHOLDER,
    )
    for candidate in candidates:
        if candidate is not None and candidate.strip():
            return _truncate(candidate)
    return _FALLBACK_PLACEHOLDER


__all__ = ["PREVIEW_MAX_LEN", "DerivationContext", "derive_preview_description"]
