"""
Data provider protocol for MFCoreScorerAdapter.

This module defines the CommunityDataProvider protocol that abstracts the
data access layer, enabling the adapter to be decoupled from specific
database implementations and facilitating testing with mock providers.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CommunityDataProvider(Protocol):
    """
    Protocol defining the interface for community data providers.

    This protocol abstracts the data access layer for MFCoreScorerAdapter,
    enabling it to fetch the community data needed for batch scoring without
    being coupled to a specific database implementation.

    Implementations should provide data for a specific community identified
    by community_id.
    """

    def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
        """
        Get all ratings for a community.

        Args:
            community_id: The unique identifier for the community.

        Returns:
            List of rating data dicts with keys:
                - id: UUID of the rating
                - note_id: UUID of the note being rated
                - rater_id: UUID of the rater's user profile
                - helpfulness_level: HELPFUL, SOMEWHAT_HELPFUL, or NOT_HELPFUL
                - created_at: datetime when the rating was created
        """
        ...

    def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
        """
        Get all notes for a community.

        Args:
            community_id: The unique identifier for the community.

        Returns:
            List of note data dicts with keys:
                - id: UUID of the note
                - author_id: UUID of the author (user profile ID)
                - classification: NOT_MISLEADING or MISINFORMED_OR_POTENTIALLY_MISLEADING
                - status: NEEDS_MORE_RATINGS, CURRENTLY_RATED_HELPFUL, or CURRENTLY_RATED_NOT_HELPFUL
                - created_at: datetime when the note was created
        """
        ...

    def get_all_participants(self, community_id: str) -> list[str]:
        """
        Get all participant IDs for a community.

        Args:
            community_id: The unique identifier for the community.

        Returns:
            List of participant ID strings (e.g., Discord user IDs) for all
            participants who have created notes or ratings in the community.
        """
        ...
