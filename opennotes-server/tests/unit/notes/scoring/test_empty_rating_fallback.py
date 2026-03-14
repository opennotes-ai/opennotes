from unittest.mock import AsyncMock

import pytest

from src.notes.scoring.adaptive_tier_manager import (
    AdaptiveScoringTierManager,
    ScorerFailureError,
)
from src.notes.scoring.tier_config import ScoringTier


@pytest.fixture(autouse=True)
def setup_database():
    return


@pytest.fixture(autouse=True)
def mock_external_services():
    return


class TestAssertionErrorFallback:
    @pytest.mark.asyncio
    async def test_assertion_error_triggers_fallback(self):
        """When scorer raises AssertionError (e.g. empty ratingsForTraining), tier manager should fall back."""
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
                raise AssertionError("MFCoreScorer: empty ratingsForTraining")
            return {"status": "scored_with_fallback"}

        result = await manager.run_scorer_with_fallback(
            scorer_that_fails_then_succeeds,
        )

        assert result == {"status": "scored_with_fallback"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_assertion_error_at_minimal_tier_raises(self):
        """AssertionError at MINIMAL tier should raise ScorerFailureError (no lower tier)."""
        mock_session = AsyncMock()
        manager = AdaptiveScoringTierManager(
            db_session=mock_session,
            tier_override=ScoringTier.MINIMAL,
        )

        async def scorer_always_asserts(*args, **kwargs):
            raise AssertionError("empty ratingsForTraining")

        with pytest.raises(ScorerFailureError):
            await manager.run_scorer_with_fallback(scorer_always_asserts)

    @pytest.mark.asyncio
    async def test_assertion_error_cascades_through_tiers(self):
        """AssertionError should cascade through tiers until one succeeds."""
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
                raise AssertionError("empty ratings")
            return {"tier": "minimal"}

        result = await manager.run_scorer_with_fallback(scorer_fails_twice)

        assert result == {"tier": "minimal"}
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_generic_exception_also_triggers_fallback(self):
        """Generic exceptions should also trigger the same fallback behavior."""
        mock_session = AsyncMock()
        manager = AdaptiveScoringTierManager(
            db_session=mock_session,
            tier_override=ScoringTier.LIMITED,
        )

        call_count = 0

        async def scorer_generic_then_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("unexpected scoring failure")
            return "ok"

        result = await manager.run_scorer_with_fallback(scorer_generic_then_ok)
        assert result == "ok"
