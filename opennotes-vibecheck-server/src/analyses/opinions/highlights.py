from __future__ import annotations

from collections.abc import Sequence
from math import ceil, log2, sqrt

from src.analyses.claims._claims_schemas import ClaimCategory, DedupedClaim
from src.analyses.opinions._highlights_schemas import (
    HighlightsThresholdInfo,
    OpinionsHighlight,
    OpinionsHighlightsReport,
)
from src.config import Settings

_INDEXABLE_CATEGORIES: set[ClaimCategory] = {
    ClaimCategory.SUBJECTIVE,
    ClaimCategory.SELF_CLAIMS,
}

_CATEGORY_ORDER = {
    ClaimCategory.SUBJECTIVE: 0,
    ClaimCategory.SELF_CLAIMS: 1,
}

_HARD_FLOOR_AUTHORS = 2
_HARD_FLOOR_OCCURRENCES = 3


def _calc_thresholds(
    total_authors: int,
    total_utterances: int,
    settings: Settings,
) -> tuple[int, int]:
    scaled_author_threshold = ceil(
        sqrt(max(total_authors, 0)) / settings.VIBECHECK_OPINIONS_HIGHLIGHTS_AUTHOR_DIVISOR
    )
    scaled_occurrence_threshold = ceil(
        log2(max(total_utterances, 2))
        * settings.VIBECHECK_OPINIONS_HIGHLIGHTS_OCCURRENCE_MULTIPLIER
    )

    min_authors_required = max(_HARD_FLOOR_AUTHORS, scaled_author_threshold)
    min_occurrences_required = max(_HARD_FLOOR_OCCURRENCES, scaled_occurrence_threshold)
    return min_authors_required, min_occurrences_required


def _sort_highlights(clusters: list[DedupedClaim]) -> list[DedupedClaim]:
    return sorted(
        clusters,
        key=lambda cluster: (
            _CATEGORY_ORDER[cluster.category],
            -cluster.occurrence_count,
            -cluster.author_count,
        ),
    )


def compute_highlights(
    clusters: Sequence[DedupedClaim],
    *,
    total_authors: int,
    total_utterances: int,
    settings: Settings,
) -> OpinionsHighlightsReport:
    """
    Filter opinion clusters into highlights.

    Rules:
    1) consider only subjective or self-claims;
    2) apply hard floor first (author_count >= 2 and occurrence_count >= 3);
    3) apply sublinear scaling above the floor to choose final survivors;
    4) if no scaled survivors but floor-eligible exists, return all floor-eligible
       clusters as a fallback.
    """
    selected_for_analysis = [
        cluster for cluster in clusters if cluster.category in _INDEXABLE_CATEGORIES
    ]

    floor_eligible = [
        cluster
        for cluster in selected_for_analysis
        if cluster.author_count >= _HARD_FLOOR_AUTHORS
        and cluster.occurrence_count >= _HARD_FLOOR_OCCURRENCES
    ]

    min_authors_required, min_occurrences_required = _calc_thresholds(
        total_authors=total_authors,
        total_utterances=total_utterances,
        settings=settings,
    )
    threshold = HighlightsThresholdInfo(
        total_authors=total_authors,
        total_utterances=total_utterances,
        min_authors_required=min_authors_required,
        min_occurrences_required=min_occurrences_required,
    )

    scaled_survivors = [
        cluster
        for cluster in floor_eligible
        if cluster.author_count >= min_authors_required
        and cluster.occurrence_count >= min_occurrences_required
    ]

    if scaled_survivors:
        survivors = _sort_highlights(scaled_survivors)
        fallback_engaged = False
        crossed_scaled_threshold = True
    elif floor_eligible:
        survivors = _sort_highlights(floor_eligible)
        fallback_engaged = True
        crossed_scaled_threshold = False
    else:
        survivors = []
        fallback_engaged = False
        crossed_scaled_threshold = False

    highlights = [
        OpinionsHighlight(
            cluster=cluster,
            crossed_scaled_threshold=crossed_scaled_threshold,
        )
        for cluster in survivors
    ]

    return OpinionsHighlightsReport(
        highlights=highlights,
        threshold=threshold,
        fallback_engaged=fallback_engaged,
        floor_eligible_count=len(floor_eligible),
        total_input_count=len(selected_for_analysis),
    )
