"""
Factory for creating tier-appropriate scorers.

This factory uses the tier configuration to select the appropriate scorer
based on community note count, with caching to avoid repeated instantiation.
"""

import logging
from typing import TYPE_CHECKING, Any

from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
from src.notes.scoring.bayesian_scorer_adapter import BayesianAverageScorerAdapter
from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter
from src.notes.scoring.rater_diversity_scorer import RaterDiversityScorerAdapter
from src.notes.scoring.scorer_protocol import ScorerProtocol
from src.notes.scoring.tier_config import (
    MINIMAL_DIVERSITY_THRESHOLD,
    ScoringTier,
    get_tier_for_note_count,
)

if TYPE_CHECKING:
    from src.notes.scoring.data_provider import CommunityDataProvider

logger = logging.getLogger(__name__)

MIN_AVG_RATERS_PER_NOTE = 5
MIN_AVG_RATINGS_PER_RATER = 10

_TIER_HIERARCHY = [
    ScoringTier.MINIMAL,
    ScoringTier.LIMITED,
    ScoringTier.BASIC,
    ScoringTier.INTERMEDIATE,
    ScoringTier.ADVANCED,
    ScoringTier.FULL,
]

_tier_failures: dict[str, ScoringTier] = {}


def record_tier_failure(
    community_server_id: str,
    failed_tier: ScoringTier,
    reason: str = "",
) -> None:
    failed_idx = _TIER_HIERARCHY.index(failed_tier)
    max_viable = _TIER_HIERARCHY[max(0, failed_idx - 1)]

    existing = _tier_failures.get(community_server_id)
    if existing is not None:
        existing_idx = _TIER_HIERARCHY.index(existing)
        max_viable_idx = _TIER_HIERARCHY.index(max_viable)
        if max_viable_idx < existing_idx:
            max_viable = _TIER_HIERARCHY[max_viable_idx]

    _tier_failures[community_server_id] = max_viable
    logger.warning(
        "Downgrading max viable tier for community",
        extra={
            "community_server_id": community_server_id,
            "failed_tier": failed_tier.value,
            "max_viable_tier": max_viable.value,
            "reason": reason,
        },
    )


def clear_tier_failures(community_server_id: str | None = None) -> None:
    if community_server_id is None:
        _tier_failures.clear()
    else:
        _tier_failures.pop(community_server_id, None)


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
        self._cache: dict[tuple[str, ScoringTier, bool], ScorerProtocol] = {}

    def get_scorer(
        self,
        community_server_id: str,
        note_count: int,
        tier_override: ScoringTier | None = None,
        data_provider: "CommunityDataProvider | None" = None,
        community_id: str | None = None,
        ratings_density: dict[str, float] | None = None,
    ) -> ScorerProtocol:
        """
        Get the appropriate scorer for a community based on note count.

        Args:
            community_server_id: Unique identifier for the community.
            note_count: Current number of notes in the community.
            tier_override: Optional tier to force, ignoring note_count.
            data_provider: Optional data provider for MFCoreScorerAdapter.
            community_id: Optional community ID passed to MFCoreScorerAdapter.

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

            if tier != ScoringTier.MINIMAL and ratings_density is not None:
                avg_raters = ratings_density.get("avg_raters_per_note", 0)
                avg_ratings = ratings_density.get("avg_ratings_per_rater", 0)
                density_sufficient = (
                    avg_raters >= MIN_AVG_RATERS_PER_NOTE
                    and avg_ratings >= MIN_AVG_RATINGS_PER_RATER
                )
                if not density_sufficient:
                    logger.warning(
                        "Insufficient ratings density for tier %s, downgrading to MINIMAL",
                        tier.value,
                        extra={
                            "community_server_id": community_server_id,
                            "avg_raters_per_note": avg_raters,
                            "avg_ratings_per_rater": avg_ratings,
                            "required_raters_per_note": MIN_AVG_RATERS_PER_NOTE,
                            "required_ratings_per_rater": MIN_AVG_RATINGS_PER_RATER,
                            "original_tier": tier.value,
                        },
                    )
                    tier = ScoringTier.MINIMAL
                elif community_server_id in _tier_failures:
                    clear_tier_failures(community_server_id)
                    logger.info(
                        "Ratings density recovered, clearing tier failure cap",
                        extra={"community_server_id": community_server_id},
                    )

            max_viable = _tier_failures.get(community_server_id)
            if max_viable is not None and tier != ScoringTier.MINIMAL:
                max_idx = _TIER_HIERARCHY.index(max_viable)
                tier_idx = _TIER_HIERARCHY.index(tier)
                if tier_idx > max_idx:
                    logger.warning(
                        "Capping tier to max_viable_tier due to prior failure",
                        extra={
                            "community_server_id": community_server_id,
                            "detected_tier": tier.value,
                            "max_viable_tier": max_viable.value,
                        },
                    )
                    tier = max_viable

        uses_diversity = (
            tier == ScoringTier.MINIMAL
            and note_count >= MINIMAL_DIVERSITY_THRESHOLD
            and data_provider is not None
        )
        cache_key = (community_server_id, tier, uses_diversity)

        if cache_key in self._cache:
            logger.debug(
                "Returning cached scorer",
                extra={
                    "community_server_id": community_server_id,
                    "tier": tier.value,
                },
            )
            return self._cache[cache_key]

        scorer = self._create_scorer_for_tier(tier, data_provider, community_id, note_count)

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

    def _create_scorer_for_tier(
        self,
        tier: ScoringTier,
        data_provider: "CommunityDataProvider | None" = None,
        community_id: str | None = None,
        note_count: int = 0,
    ) -> ScorerProtocol:
        if tier == ScoringTier.MINIMAL:
            if note_count >= MINIMAL_DIVERSITY_THRESHOLD and data_provider is not None:
                return RaterDiversityScorerAdapter(data_provider, community_id or "")
            bayesian_scorer = BayesianAverageScorer()
            return BayesianAverageScorerAdapter(bayesian_scorer)

        return MFCoreScorerAdapter(data_provider=data_provider, community_id=community_id)

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
