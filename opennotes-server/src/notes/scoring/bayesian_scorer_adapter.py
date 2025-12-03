"""
Adapter for BayesianAverageScorer to implement ScorerProtocol.

This adapter wraps the existing BayesianAverageScorer to provide
a unified interface for single-note scoring operations.
"""

from collections.abc import Sequence

from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
from src.notes.scoring.scorer_protocol import ScoringResult


class BayesianAverageScorerAdapter:
    """
    Adapter that wraps BayesianAverageScorer to implement ScorerProtocol.

    This allows the Bayesian average scoring algorithm to be used
    interchangeably with other scorers through the unified protocol.
    """

    def __init__(self, scorer: BayesianAverageScorer) -> None:
        """
        Initialize the adapter with a BayesianAverageScorer instance.

        Args:
            scorer: The underlying BayesianAverageScorer to wrap.
        """
        self._scorer = scorer

    def score_note(self, note_id: str, ratings: Sequence[float]) -> ScoringResult:
        """
        Calculate the score for a single note.

        Args:
            note_id: The unique identifier for the note being scored.
            ratings: Sequence of rating values for the note (0.0 to 1.0).

        Returns:
            ScoringResult containing the score, confidence level, and metadata.
        """
        ratings_list = list(ratings)

        score = self._scorer.calculate_score(ratings_list, note_id=note_id)

        metadata = self._scorer.get_score_metadata(ratings_list, score=score, note_id=note_id)

        confidence_level = metadata.get("confidence_level", "provisional")

        return ScoringResult(
            score=score,
            confidence_level=confidence_level,
            metadata=metadata,
        )
