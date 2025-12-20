"""Scoring utility functions.

This module contains helper functions for scoring operations that are used
by multiple routers and services.
"""

from src.notes.models import Note, Rating
from src.notes.schemas import HelpfulnessLevel
from src.notes.scoring import (
    ScorerProtocol,
    ScoringTier,
    get_tier_config,
    get_tier_for_note_count,
)
from src.notes.scoring_schemas import (
    DataConfidence,
    NoteScoreResponse,
    ScoreConfidence,
)

# Tier ordering for iteration
TIER_ORDER = [
    ScoringTier.MINIMAL,
    ScoringTier.LIMITED,
    ScoringTier.BASIC,
    ScoringTier.INTERMEDIATE,
    ScoringTier.ADVANCED,
    ScoringTier.FULL,
]


def get_tier_level(tier: ScoringTier) -> int:
    """Get numeric level (0-5) for a tier."""
    return TIER_ORDER.index(tier)


def get_tier_by_level(level: int) -> ScoringTier | None:
    """Get tier enum by numeric level."""
    if 0 <= level < len(TIER_ORDER):
        return TIER_ORDER[level]
    return None


def get_next_tier(tier: ScoringTier) -> ScoringTier | None:
    """Get the next tier in the hierarchy, or None if at maximum."""
    try:
        current_index = TIER_ORDER.index(tier)
        if current_index + 1 < len(TIER_ORDER):
            return TIER_ORDER[current_index + 1]
    except ValueError:
        pass
    return None


def get_tier_data_confidence(tier: ScoringTier) -> DataConfidence:
    """Map tier to DataConfidence enum."""
    tier_config = get_tier_config(tier)
    if tier_config.confidence_warnings:
        if tier == ScoringTier.MINIMAL:
            return DataConfidence.NONE
        return DataConfidence.LOW
    if tier in (ScoringTier.BASIC,):
        return DataConfidence.MEDIUM
    if tier in (ScoringTier.INTERMEDIATE, ScoringTier.ADVANCED):
        return DataConfidence.HIGH
    return DataConfidence.VERY_HIGH


def convert_ratings_to_floats(ratings: list[Rating]) -> list[float]:
    """
    Convert Rating objects to float values (0.0-1.0) for scoring.

    Uses the centralized to_score_value() method from HelpfulnessLevel enum
    to ensure consistent scoring across the application.
    """
    result = []
    for rating in ratings:
        # Rating.helpfulness_level is Mapped[str], convert to enum for scoring
        helpfulness_enum = HelpfulnessLevel(rating.helpfulness_level)
        result.append(helpfulness_enum.to_score_value())
    return result


async def calculate_note_score(
    note: Note, note_count: int, scorer: ScorerProtocol
) -> NoteScoreResponse:
    """Calculate score for a single note with metadata."""
    active_tier_enum = get_tier_for_note_count(note_count)
    active_tier_level = get_tier_level(active_tier_enum)

    rating_values = convert_ratings_to_floats(note.ratings)
    rating_count = len(rating_values)

    result = scorer.score_note(str(note.id), rating_values)

    if rating_count == 0 or result.metadata.get("no_data"):
        confidence = ScoreConfidence.NO_DATA
    elif result.confidence_level == "provisional":
        confidence = ScoreConfidence.PROVISIONAL
    else:
        confidence = ScoreConfidence.STANDARD

    calculated_at = note.updated_at if note.updated_at else note.created_at

    content = None
    if note.request and note.request.message_archive:
        content = note.request.message_archive.get_content()

    return NoteScoreResponse(
        note_id=note.id,
        score=result.score,
        confidence=confidence,
        algorithm=result.metadata.get("algorithm", "bayesian_average_tier0"),
        rating_count=rating_count,
        tier=active_tier_level,
        tier_name=active_tier_enum.value.capitalize(),
        calculated_at=calculated_at,
        content=content,
    )
