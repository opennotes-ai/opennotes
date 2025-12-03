import asyncio
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.notes.models import Note
from src.notes.scoring.tier_config import (
    TIER_CONFIGURATIONS,
    ScoringTier,
    TierThresholds,
    get_tier_config,
    get_tier_for_note_count,
)

logger = logging.getLogger(__name__)


class ScorerTimeoutError(Exception):
    pass


class ScorerFailureError(Exception):
    pass


class AdaptiveScoringTierManager:
    def __init__(
        self,
        db_session: AsyncSession,
        tier_override: ScoringTier | None = None,
        scorer_timeout_seconds: int = 30,
    ):
        self._db_session = db_session
        self._tier_override = tier_override
        self._scorer_timeout_seconds = scorer_timeout_seconds
        self._current_tier: ScoringTier | None = None
        self._cached_note_count: int | None = None

    async def get_note_count(self, use_cache: bool = True) -> int:
        if use_cache and self._cached_note_count is not None:
            return self._cached_note_count

        result = await self._db_session.execute(select(func.count(Note.id)))
        count = result.scalar_one()
        self._cached_note_count = count
        logger.info(f"Database note count: {count}")
        return count

    async def detect_tier(self, force_refresh: bool = False) -> ScoringTier:
        if self._tier_override is not None:
            logger.info(
                f"Using tier override: {self._tier_override} (skipping automatic detection)"
            )
            self._current_tier = self._tier_override
            return self._tier_override

        note_count = await self.get_note_count(use_cache=not force_refresh)
        previous_tier = self._current_tier
        detected_tier = get_tier_for_note_count(note_count)
        self._current_tier = detected_tier

        if previous_tier is not None and previous_tier != detected_tier:
            logger.warning(
                f"Tier transition detected: {previous_tier} -> {detected_tier} "
                f"(note count: {note_count})"
            )
        else:
            logger.info(f"Detected scoring tier: {detected_tier} (note count: {note_count})")

        return detected_tier

    def get_tier_config(self, tier: ScoringTier | None = None) -> TierThresholds:
        target_tier = tier or self._current_tier
        if target_tier is None:
            raise ValueError("No tier specified and no current tier set. Call detect_tier() first.")
        return get_tier_config(target_tier)

    async def run_scorer_with_fallback(
        self,
        scorer_func: Any,
        tier: ScoringTier | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        target_tier = tier or self._current_tier
        if target_tier is None:
            target_tier = await self.detect_tier()

        tier_config = self.get_tier_config(target_tier)

        try:
            return await asyncio.wait_for(
                self._run_scorer(scorer_func, tier_config, *args, **kwargs),
                timeout=self._scorer_timeout_seconds,
            )
        except TimeoutError:
            logger.error(
                f"Scorer timeout after {self._scorer_timeout_seconds}s "
                f"at tier {target_tier}, attempting fallback"
            )
            return await self._handle_timeout_fallback(scorer_func, target_tier, *args, **kwargs)
        except Exception as e:
            logger.error(
                f"Scorer failed at tier {target_tier}: {e}, attempting fallback",
                exc_info=True,
            )
            return await self._handle_scorer_failure(scorer_func, target_tier, *args, **kwargs)

    async def _run_scorer(
        self,
        scorer_func: Any,
        tier_config: TierThresholds,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        logger.info(
            f"Running scorer with config: {tier_config.description}, scorers: {tier_config.scorers}"
        )

        if tier_config.confidence_warnings:
            logger.warning(
                f"CONFIDENCE WARNING: Current tier ({self._current_tier}) "
                f"has limited data. Scoring results may not be reliable."
            )

        if asyncio.iscoroutinefunction(scorer_func):
            return await scorer_func(*args, **kwargs)
        return scorer_func(*args, **kwargs)

    async def _handle_timeout_fallback(
        self,
        scorer_func: Any,
        failed_tier: ScoringTier,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        fallback_tier = self._get_fallback_tier(failed_tier)

        if fallback_tier is None:
            logger.error(f"No fallback available for tier {failed_tier}")
            raise ScorerTimeoutError(
                f"Scorer timeout at tier {failed_tier} with no fallback available"
            )

        logger.warning(f"Falling back from {failed_tier} to {fallback_tier}")
        kwargs_without_tier = {k: v for k, v in kwargs.items() if k != "tier"}
        return await self.run_scorer_with_fallback(
            scorer_func, fallback_tier, *args, **kwargs_without_tier
        )

    async def _handle_scorer_failure(
        self,
        scorer_func: Any,
        failed_tier: ScoringTier,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        fallback_tier = self._get_fallback_tier(failed_tier)

        if fallback_tier is None:
            logger.error(f"No fallback available for tier {failed_tier}")
            raise ScorerFailureError(f"No fallback available for tier {failed_tier}")

        logger.warning(f"Falling back from {failed_tier} to {fallback_tier} due to failure")
        kwargs_without_tier = {k: v for k, v in kwargs.items() if k != "tier"}
        return await self.run_scorer_with_fallback(
            scorer_func, fallback_tier, *args, **kwargs_without_tier
        )

    def _get_fallback_tier(self, current_tier: ScoringTier) -> ScoringTier | None:
        tier_hierarchy = [
            ScoringTier.MINIMAL,
            ScoringTier.LIMITED,
            ScoringTier.BASIC,
            ScoringTier.INTERMEDIATE,
            ScoringTier.ADVANCED,
            ScoringTier.FULL,
        ]

        try:
            current_index = tier_hierarchy.index(current_tier)
            if current_index > 0:
                return tier_hierarchy[current_index - 1]
        except ValueError:
            pass

        return None

    def get_current_tier(self) -> ScoringTier | None:
        return self._current_tier

    def get_tier_info(self, tier: ScoringTier | None = None) -> dict[str, Any]:
        target_tier = tier or self._current_tier
        if target_tier is None:
            return {
                "error": "No tier set. Call detect_tier() first.",
                "note_count": self._cached_note_count,
            }

        tier_config = self.get_tier_config(target_tier)
        return {
            "tier": target_tier.value,
            "description": tier_config.description,
            "min_notes": tier_config.min_notes,
            "max_notes": tier_config.max_notes,
            "scorers": tier_config.scorers,
            "requires_full_pipeline": tier_config.requires_full_pipeline,
            "enable_clustering": tier_config.enable_clustering,
            "confidence_warnings": tier_config.confidence_warnings,
            "current_note_count": self._cached_note_count,
            "is_override": self._tier_override is not None,
        }

    def clear_cache(self) -> None:
        self._cached_note_count = None
        logger.debug("Cleared note count cache")

    async def handle_edge_case(self, note_count: int) -> ScoringTier:
        if note_count == 200:
            logger.info(
                "Edge case: Exactly 200 notes. Assigning to LIMITED tier "
                "(inclusive lower bound per tier definition)."
            )
            return ScoringTier.LIMITED
        if note_count == 1000:
            logger.info(
                "Edge case: Exactly 1000 notes. Assigning to BASIC tier "
                "(inclusive lower bound per tier definition)."
            )
            return ScoringTier.BASIC
        if note_count == 5000:
            logger.info(
                "Edge case: Exactly 5000 notes. Assigning to INTERMEDIATE tier "
                "(inclusive lower bound per tier definition)."
            )
            return ScoringTier.INTERMEDIATE
        if note_count == 10000:
            logger.info(
                "Edge case: Exactly 10000 notes. Assigning to ADVANCED tier "
                "(inclusive lower bound per tier definition)."
            )
            return ScoringTier.ADVANCED
        if note_count == 50000:
            logger.info(
                "Edge case: Exactly 50000 notes. Assigning to FULL tier "
                "(inclusive lower bound per tier definition)."
            )
            return ScoringTier.FULL

        return get_tier_for_note_count(note_count)


def get_all_tier_configurations() -> dict[ScoringTier, TierThresholds]:
    return TIER_CONFIGURATIONS.copy()


def get_tier_warnings(note_count: int, tier: ScoringTier) -> list[str]:
    """
    Generate warnings for a given note count and tier.

    Args:
        note_count: Current number of notes
        tier: The scoring tier to check warnings for

    Returns:
        List of warning messages
    """
    warnings = []
    tier_config = get_tier_config(tier)

    if tier_config.confidence_warnings:
        warnings.append(
            f"Limited data confidence: Only {note_count} notes available. "
            f"Scoring quality improves significantly with more data."
        )

    if note_count < 200:
        warnings.append(
            "Below production threshold: Using simple fallback scorer. "
            "Matrix factorization requires at least 200 notes."
        )

    tier_hierarchy = [
        ScoringTier.MINIMAL,
        ScoringTier.LIMITED,
        ScoringTier.BASIC,
        ScoringTier.INTERMEDIATE,
        ScoringTier.ADVANCED,
        ScoringTier.FULL,
    ]

    try:
        current_index = tier_hierarchy.index(tier)

        if tier == ScoringTier.FULL:
            warnings.append(
                f"At maximum tier ({tier.value}): {note_count} notes. Using full scoring pipeline."
            )
        elif (
            tier_config.max_notes
            and note_count > tier_config.max_notes * 0.9
            and current_index + 1 < len(tier_hierarchy)
        ):
            next_tier = tier_hierarchy[current_index + 1]
            next_tier_notes = tier_config.max_notes
            warnings.append(
                f"Approaching next tier: {note_count}/{next_tier_notes} notes. "
                f"Will upgrade to {next_tier.value} tier soon."
            )
    except ValueError:
        pass

    return warnings
