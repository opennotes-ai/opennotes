"""
Factory for creating tier-appropriate scorers.

This factory uses the tier configuration to select the appropriate scorer
based on community note count, with caching to avoid repeated instantiation.
"""

import logging
from typing import Any

from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
from src.notes.scoring.bayesian_scorer_adapter import BayesianAverageScorerAdapter
from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
from src.notes.scoring.scorer_protocol import ScorerProtocol
from src.notes.scoring.tier_config import ScoringTier, get_tier_for_note_count

logger = logging.getLogger(__name__)


class ScorerFactory:
    """
    Factory for creating tier-appropriate scorers.

    Uses tier configuration to select BayesianAverageScorerAdapter for MINIMAL tier
    and MFCoreScorerAdapter for LIMITED+ tiers. Caches scorers per community and tier
    to avoid repeated instantiation.

    Thread Safety:
        This factory is NOT thread-safe. If used in a concurrent environment,
        external synchronization is required to prevent race conditions during
        cache operations.
    """

    def __init__(self) -> None:
        """Initialize the factory with an empty cache."""
        self._cache: dict[tuple[str, ScoringTier], ScorerProtocol] = {}

    def get_scorer(
        self,
        community_server_id: str,
        note_count: int,
        tier_override: ScoringTier | None = None,
    ) -> ScorerProtocol:
        """
        Get the appropriate scorer for a community based on note count.

        Args:
            community_server_id: Unique identifier for the community.
            note_count: Current number of notes in the community.
            tier_override: Optional tier to force, ignoring note_count.

        Returns:
            ScorerProtocol implementation appropriate for the tier.
        """
        if tier_override is not None:
            tier = tier_override
            logger.debug(
                "Using tier override",
                extra={
                    "community_server_id": community_server_id,
                    "tier_override": tier.value,
                    "note_count": note_count,
                },
            )
        else:
            tier = get_tier_for_note_count(note_count)
            logger.debug(
                "Determined tier from note count",
                extra={
                    "community_server_id": community_server_id,
                    "tier": tier.value,
                    "note_count": note_count,
                },
            )

        cache_key = (community_server_id, tier)

        if cache_key in self._cache:
            logger.debug(
                "Returning cached scorer",
                extra={
                    "community_server_id": community_server_id,
                    "tier": tier.value,
                },
            )
            return self._cache[cache_key]

        scorer = self._create_scorer_for_tier(tier)

        self._cache[cache_key] = scorer

        logger.info(
            "Created new scorer for community",
            extra={
                "community_server_id": community_server_id,
                "tier": tier.value,
                "scorer_type": type(scorer).__name__,
                "cache_size": len(self._cache),
            },
        )

        return scorer

    def _create_scorer_for_tier(self, tier: ScoringTier) -> ScorerProtocol:
        """
        Create the appropriate scorer for a given tier.

        Args:
            tier: The scoring tier to create a scorer for.

        Returns:
            ScorerProtocol implementation for the tier.
        """
        if tier == ScoringTier.MINIMAL:
            bayesian_scorer = BayesianAverageScorer()
            return BayesianAverageScorerAdapter(bayesian_scorer)

        return MFCoreScorerAdapter()

    def get_cache_info(self) -> dict[str, Any]:
        """
        Get information about the current cache state.

        Returns:
            Dictionary with cache statistics.
        """
        return {
            "cache_size": len(self._cache),
            "cached_entries": [
                {"community_server_id": k[0], "tier": k[1].value} for k in self._cache
            ],
        }

    def clear_cache(self) -> None:
        """Clear all cached scorers."""
        self._cache.clear()
        logger.info("Scorer factory cache cleared")

    def invalidate_community(self, community_server_id: str) -> int:
        """
        Invalidate all cached scorers for a specific community.

        Args:
            community_server_id: The community to invalidate cache for.

        Returns:
            Number of cache entries removed.
        """
        keys_to_remove = [k for k in self._cache if k[0] == community_server_id]
        for key in keys_to_remove:
            del self._cache[key]

        if keys_to_remove:
            logger.info(
                "Invalidated scorer cache for community",
                extra={
                    "community_server_id": community_server_id,
                    "entries_removed": len(keys_to_remove),
                },
            )

        return len(keys_to_remove)
