"""
Scoring Data Validator for MFCoreScorer integration.

Validates that rating data meets minimum requirements for reliable
Community Notes matrix factorization scoring.
"""

from dataclasses import dataclass, field

import pandas as pd

DEFAULT_MIN_RATERS_PER_NOTE = 5
DEFAULT_MIN_RATINGS_PER_RATER = 10


@dataclass
class ValidationResult:
    """
    Result of validating scoring data.

    Attributes:
        is_valid: True if all validation checks pass
        notes_with_insufficient_ratings: List of note IDs with too few ratings
        raters_with_insufficient_ratings: List of rater IDs with too few ratings
        total_notes: Total number of unique notes
        total_raters: Total number of unique raters
        total_ratings: Total number of ratings
    """

    is_valid: bool
    notes_with_insufficient_ratings: list[str] = field(default_factory=list)
    raters_with_insufficient_ratings: list[str] = field(default_factory=list)
    total_notes: int = 0
    total_raters: int = 0
    total_ratings: int = 0

    def summary(self) -> dict:
        """
        Get a summary of the validation result.

        Returns:
            Dictionary with validation summary information
        """
        return {
            "is_valid": self.is_valid,
            "total_notes": self.total_notes,
            "total_raters": self.total_raters,
            "total_ratings": self.total_ratings,
            "notes_below_threshold": len(self.notes_with_insufficient_ratings),
            "raters_below_threshold": len(self.raters_with_insufficient_ratings),
        }


class ScoringDataValidator:
    """
    Validator for checking if rating data meets MFCoreScorer requirements.

    The Community Notes MFCoreScorer requires minimum amounts of data to
    produce reliable scores:
    - Each note needs at least min_raters_per_note ratings (default: 5)
    - Each rater needs at least min_ratings_per_rater ratings (default: 10)
    """

    def __init__(
        self,
        min_raters_per_note: int = DEFAULT_MIN_RATERS_PER_NOTE,
        min_ratings_per_rater: int = DEFAULT_MIN_RATINGS_PER_RATER,
    ):
        """
        Initialize the validator with threshold requirements.

        Args:
            min_raters_per_note: Minimum number of raters required per note
            min_ratings_per_rater: Minimum number of ratings required per rater
        """
        self.min_raters_per_note = min_raters_per_note
        self.min_ratings_per_rater = min_ratings_per_rater

    def validate(self, ratings_df: pd.DataFrame) -> ValidationResult:
        """
        Validate the ratings DataFrame against minimum requirements.

        Args:
            ratings_df: DataFrame with columns:
                - noteId: The note identifier
                - raterParticipantId: The rater identifier
                - helpfulNum: The helpfulness rating
                - createdAtMillis: The timestamp

        Returns:
            ValidationResult with validation status and details
        """
        if ratings_df.empty:
            return ValidationResult(
                is_valid=False,
                notes_with_insufficient_ratings=[],
                raters_with_insufficient_ratings=[],
                total_notes=0,
                total_raters=0,
                total_ratings=0,
            )

        notes_insufficient = self._find_notes_with_insufficient_ratings(ratings_df)
        raters_insufficient = self._find_raters_with_insufficient_ratings(ratings_df)

        is_valid = len(notes_insufficient) == 0 and len(raters_insufficient) == 0

        return ValidationResult(
            is_valid=is_valid,
            notes_with_insufficient_ratings=notes_insufficient,
            raters_with_insufficient_ratings=raters_insufficient,
            total_notes=ratings_df["noteId"].nunique(),
            total_raters=ratings_df["raterParticipantId"].nunique(),
            total_ratings=len(ratings_df),
        )

    def _find_notes_with_insufficient_ratings(self, ratings_df: pd.DataFrame) -> list[str]:
        """Find notes that don't have enough ratings."""
        rating_counts = ratings_df.groupby("noteId").size()
        insufficient = rating_counts[rating_counts < self.min_raters_per_note]
        return list(insufficient.index)

    def _find_raters_with_insufficient_ratings(self, ratings_df: pd.DataFrame) -> list[str]:
        """Find raters that haven't made enough ratings."""
        rating_counts = ratings_df.groupby("raterParticipantId").size()
        insufficient = rating_counts[rating_counts < self.min_ratings_per_rater]
        return list(insufficient.index)
