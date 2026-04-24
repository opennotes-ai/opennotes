"""Neutral per-section payloads used when a section has no successful data."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.analyses.schemas import SectionSlug

_EMPTY_SECTION_DATA: dict[SectionSlug, dict[str, Any]] = {
    SectionSlug.SAFETY_MODERATION: {"harmful_content_matches": []},
    SectionSlug.SAFETY_WEB_RISK: {"findings": []},
    SectionSlug.SAFETY_IMAGE_MODERATION: {"matches": []},
    SectionSlug.SAFETY_VIDEO_MODERATION: {"matches": []},
    SectionSlug.TONE_DYNAMICS_FLASHPOINT: {"flashpoint_matches": []},
    SectionSlug.TONE_DYNAMICS_SCD: {
        "scd": {
            "summary": "",
            "tone_labels": [],
            "per_speaker_notes": {},
            "insufficient_conversation": True,
        }
    },
    SectionSlug.FACTS_CLAIMS_DEDUP: {
        "claims_report": {
            "deduped_claims": [],
            "total_claims": 0,
            "total_unique": 0,
        }
    },
    SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO: {"known_misinformation": []},
    SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT: {
        "sentiment_stats": {
            "per_utterance": [],
            "positive_pct": 0.0,
            "negative_pct": 0.0,
            "neutral_pct": 0.0,
            "mean_valence": 0.0,
        }
    },
    SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE: {"subjective_claims": []},
}


def empty_section_data(slug: SectionSlug) -> dict[str, Any]:
    """Return a fresh empty/neutral payload for a section slug."""
    return deepcopy(_EMPTY_SECTION_DATA.get(slug, {}))


__all__ = ["empty_section_data"]
