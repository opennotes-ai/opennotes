import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

scoring_path = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    / "communitynotes"
    / "scoring"
    / "src"
)
if scoring_path not in sys.path:
    sys.path.insert(0, scoring_path)

from scoring.scorer import EmptyRatingException  # noqa: E402

from src.notes.scoring.adaptive_tier_manager import (  # noqa: E402
    AdaptiveScoringTierManager,
    ScorerFailureError,
)
from src.notes.scoring.tier_config import ScoringTier  # noqa: E402


@pytest.fixture(autouse=True)
def setup_database():
    return


@pytest.fixture(autouse=True)
def mock_external_services():
    return


class TestEmptyRatingFallback:
    @pytest.mark.asyncio
    async def test_empty_rating_exception_triggers_fallback(self):
        """When scorer raises EmptyRatingException, tier manager should fall back to lower tier."""
        mock_session = AsyncMock()
        manager = AdaptiveScoringTierManager(
            db_session=mock_session,
            tier_override=ScoringTier.LIMITED,
        )

        call_count = 0

        async def scorer_that_fails_then_succeeds(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise EmptyRatingException("MFCoreScorer has empty ratings")
            return {"status": "scored_with_fallback"}

        result = await manager.run_scorer_with_fallback(
            scorer_that_fails_then_succeeds,
        )

        assert result == {"status": "scored_with_fallback"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_empty_rating_exception_at_minimal_tier_raises(self):
        """EmptyRatingException at MINIMAL tier should raise ScorerFailureError (no lower tier)."""
        mock_session = AsyncMock()
        manager = AdaptiveScoringTierManager(
            db_session=mock_session,
            tier_override=ScoringTier.MINIMAL,
        )

        async def scorer_always_empty(*args, **kwargs):
            raise EmptyRatingException("No ratings available")

        with pytest.raises(ScorerFailureError):
            await manager.run_scorer_with_fallback(scorer_always_empty)

    @pytest.mark.asyncio
    async def test_empty_rating_falls_back_from_basic_to_limited_to_minimal(self):
        """EmptyRatingException should cascade through tiers until one succeeds."""
        mock_session = AsyncMock()
        manager = AdaptiveScoringTierManager(
            db_session=mock_session,
            tier_override=ScoringTier.BASIC,
        )

        call_count = 0

        async def scorer_fails_twice(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise EmptyRatingException("Empty ratings")
            return {"tier": "minimal"}

        result = await manager.run_scorer_with_fallback(scorer_fails_twice)

        assert result == {"tier": "minimal"}
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_empty_rating_exception_is_distinct_from_generic_exception(self):
        """EmptyRatingException should be handled the same as generic exceptions (fallback)."""
        mock_session = AsyncMock()
        manager = AdaptiveScoringTierManager(
            db_session=mock_session,
            tier_override=ScoringTier.LIMITED,
        )

        call_count = 0

        async def scorer_empty_then_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise EmptyRatingException("Empty")
            return "ok"

        result = await manager.run_scorer_with_fallback(scorer_empty_then_ok)
        assert result == "ok"
