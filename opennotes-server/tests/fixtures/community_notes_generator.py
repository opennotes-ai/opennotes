"""
Generate synthetic Community Notes datasets for testing adaptive scoring tiers.

This module creates realistic test datasets of varying sizes to test the adaptive
scoring system across all tiers.
"""

import random
from typing import Any


class CommunityNotesGenerator:
    """Generate synthetic Community Notes data for testing."""

    def __init__(self, seed: int = 42):
        """Initialize generator with optional seed for reproducibility."""
        self.seed = seed
        random.seed(seed)

    def generate_dataset(
        self,
        num_notes: int,
        ratings_per_note: int = 5,
        raters_per_rating: int = 1,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Generate a complete Community Notes dataset.

        Args:
            num_notes: Number of notes to generate
            ratings_per_note: Average number of ratings per note
            raters_per_rating: Number of unique raters per rating

        Returns:
            Tuple of (notes, ratings, enrollment) lists
        """
        notes = self._generate_notes(num_notes)
        enrollment = self._generate_enrollment(num_notes, ratings_per_note)
        ratings = self._generate_ratings(notes, enrollment, ratings_per_note)

        return notes, ratings, enrollment

    def _generate_notes(self, count: int) -> list[dict[str, Any]]:
        """Generate synthetic notes."""
        classifications = [
            "MISINFORMED_OR_POTENTIALLY_MISLEADING",
            "NOT_MISLEADING",
            "DISAGREE_WITH_CONSENSUS",
        ]

        notes = []
        base_time = 1700000000000  # Nov 2023

        for i in range(count):
            note_id = i + 1
            author_id = f"author_{(i % 100) + 1}"  # Reuse authors

            notes.append(
                {
                    "noteId": note_id,
                    "noteAuthorParticipantId": author_id,
                    "createdAtMillis": base_time + (i * 60000),  # 1 minute apart
                    "tweetId": str(1000 + i),
                    "summary": f"Test note {note_id}: This is a synthetic note for testing",
                    "classification": random.choice(classifications),
                }
            )

        return notes

    def _generate_enrollment(
        self,
        num_notes: int,
        ratings_per_note: int,
    ) -> list[dict[str, Any]]:
        """Generate enrollment data for authors and raters."""
        enrollment = []
        base_time = 1700000000000

        # Authors (one per note, reused across notes)
        num_authors = min(100, num_notes)
        for i in range(num_authors):
            enrollment.append(
                {
                    "participantId": f"author_{i + 1}",
                    "enrollmentState": "EARNED_IN",
                    "successfulRatingNeededToEarnIn": 0,
                    "timestampOfLastStateChange": base_time + (i * 60000),
                }
            )

        # Raters (enough for ratings)
        num_raters = min(200, max(20, num_notes * ratings_per_note // 3))
        for i in range(num_raters):
            enrollment.append(
                {
                    "participantId": f"rater_{i + 1}",
                    "enrollmentState": "EARNED_IN",
                    "successfulRatingNeededToEarnIn": 0,
                    "timestampOfLastStateChange": base_time + (i * 60000),
                }
            )

        return enrollment

    def _generate_ratings(
        self,
        notes: list[dict[str, Any]],
        enrollment: list[dict[str, Any]],
        ratings_per_note: int,
    ) -> list[dict[str, Any]]:
        """Generate ratings for notes."""
        helpfulness_levels = [
            "HELPFUL",
            "SOMEWHAT_HELPFUL",
            "NOT_HELPFUL",
        ]

        ratings = []
        rater_ids = [
            e["participantId"] for e in enrollment if e["participantId"].startswith("rater_")
        ]

        if not rater_ids:
            # Fallback: create some rater IDs if none exist
            rater_ids = [f"rater_{i}" for i in range(1, ratings_per_note + 1)]

        for note in notes:
            note_id = note["noteId"]
            note_time = note["createdAtMillis"]

            # Generate ratings for this note
            num_ratings = max(ratings_per_note, 2)  # At least 2 ratings
            num_ratings = min(num_ratings, len(rater_ids))  # Don't exceed available raters

            for j in range(num_ratings):
                # Use different raters for each rating
                rater_id = rater_ids[j % len(rater_ids)]

                ratings.append(
                    {
                        "raterParticipantId": rater_id,
                        "noteId": note_id,
                        "createdAtMillis": note_time + ((j + 1) * 10000),  # 10 seconds apart
                        "helpfulnessLevel": random.choice(helpfulness_levels),
                    }
                )

        return ratings


def generate_tier_datasets() -> dict[str, tuple]:
    """
    Generate datasets for each adaptive scoring tier.

    Returns:
        Dictionary mapping tier names to (notes, ratings, enrollment) tuples
    """
    generator = CommunityNotesGenerator(seed=42)

    return {
        "tier_0_150": generator.generate_dataset(150, ratings_per_note=5),
        "tier_0.5_500": generator.generate_dataset(500, ratings_per_note=5),
        "tier_1_2000": generator.generate_dataset(2000, ratings_per_note=6),
        "tier_2_7500": generator.generate_dataset(7500, ratings_per_note=6),
        "tier_3_25000": generator.generate_dataset(25000, ratings_per_note=7),
        "tier_4_75000": generator.generate_dataset(75000, ratings_per_note=8),
    }


def generate_boundary_datasets() -> dict[str, tuple]:
    """
    Generate datasets for boundary testing.

    Returns:
        Dictionary mapping boundary descriptions to (notes, ratings, enrollment) tuples
    """
    generator = CommunityNotesGenerator(seed=42)

    return {
        "boundary_199": generator.generate_dataset(199, ratings_per_note=5),
        "boundary_200": generator.generate_dataset(200, ratings_per_note=5),
        "boundary_201": generator.generate_dataset(201, ratings_per_note=5),
        "boundary_999": generator.generate_dataset(999, ratings_per_note=5),
        "boundary_1000": generator.generate_dataset(1000, ratings_per_note=5),
        "boundary_1001": generator.generate_dataset(1001, ratings_per_note=5),
        "boundary_4999": generator.generate_dataset(4999, ratings_per_note=6),
        "boundary_5000": generator.generate_dataset(5000, ratings_per_note=6),
        "boundary_5001": generator.generate_dataset(5001, ratings_per_note=6),
        "boundary_9999": generator.generate_dataset(9999, ratings_per_note=6),
        "boundary_10000": generator.generate_dataset(10000, ratings_per_note=7),
        "boundary_10001": generator.generate_dataset(10001, ratings_per_note=7),
        "boundary_49999": generator.generate_dataset(49999, ratings_per_note=7),
        "boundary_50000": generator.generate_dataset(50000, ratings_per_note=8),
        "boundary_50001": generator.generate_dataset(50001, ratings_per_note=8),
    }
