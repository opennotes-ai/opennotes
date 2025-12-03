import logging
from typing import Any

logger = logging.getLogger(__name__)


class ScoringAdapter:
    """Mock scoring adapter for testing without external dependencies"""

    async def score_notes(
        self,
        notes: list[dict[str, Any]],
        ratings: list[dict[str, Any]],
        enrollment: list[dict[str, Any]],
        status: list[dict[str, Any]] | None = None,  # noqa: ARG002 - required for adapter interface
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        if not notes:
            raise ValueError("Notes list cannot be empty")
        if not ratings:
            raise ValueError("Ratings list cannot be empty")
        if not enrollment:
            raise ValueError("Enrollment list cannot be empty")

        logger.info(
            f"Mock scoring {len(notes)} notes, {len(ratings)} ratings, {len(enrollment)} users"
        )

        # Return mock scored data
        scored_notes = [
            {
                "noteId": note["noteId"],
                "score": 0.75,
                "status": "CURRENTLY_RATED_HELPFUL",
                "helpfulnessScore": 15,
            }
            for note in notes
        ]

        helpful_scores = [
            {
                "participantId": user["participantId"],
                "helpfulnessScore": 0.8,
                "contributorScore": 0.7,
            }
            for user in enrollment
        ]

        aux_info = [
            {
                "type": "scoring_metadata",
                "version": "1.0.0",
                "timestamp": "2025-10-20T21:00:00Z",
                "notes_scored": len(notes),
                "ratings_processed": len(ratings),
            }
        ]

        return scored_notes, helpful_scores, aux_info
