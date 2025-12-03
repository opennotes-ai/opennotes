"""
Scorer abstraction layer defining the ScorerProtocol interface.

This module provides a unified interface for different scoring algorithms,
allowing BayesianAverageScorer and MFCoreScorer to be used interchangeably
for single-note scoring operations.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ScoringResult:
    """
    Result of scoring a single note.

    Attributes:
        score: The calculated score for the note (0.0 to 1.0 range typically).
        confidence_level: Confidence in the score ("provisional", "standard", etc.).
        metadata: Additional algorithm-specific metadata about the scoring.
    """

    score: float
    confidence_level: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ScorerProtocol(Protocol):
    """
    Protocol defining the interface for note scorers.

    Any scorer implementing this protocol can be used interchangeably
    for single-note scoring operations.
    """

    def score_note(self, note_id: str, ratings: Sequence[float]) -> ScoringResult:
        """
        Calculate the score for a single note.

        Args:
            note_id: The unique identifier for the note being scored.
            ratings: Sequence of rating values for the note.

        Returns:
            ScoringResult containing the score, confidence level, and metadata.
        """
        ...
