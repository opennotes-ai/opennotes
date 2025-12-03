from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.notes.scoring.adaptive_tier_manager import AdaptiveScoringTierManager
from src.notes.scoring.bayesian_average_scorer import BayesianAverageScorer
from src.notes.scoring.tier_config import ScoringTier, get_tier_for_note_count

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db_session():
    """Mock database session for testing."""
    return AsyncMock(spec=AsyncSession)


class TestTier0Activation:
    """
    Integration tests for Tier 0 (MINIMAL) activation with BayesianAverageScorer (AC #12).

    Tests that:
    1. BayesianAverageScorer is used for tier 0 (0-199 notes)
    2. Smooth transition to tier 0.5 (LIMITED) at exactly 200 notes
    3. Deactivation at 200+ notes (should use different scorer)
    4. Boundary cases: 0, 1, 199, 200, 201 notes
    """

    @pytest.mark.asyncio
    async def test_tier0_activated_for_zero_notes(self, mock_db_session):
        """Test that MINIMAL tier is selected when there are 0 notes in the system."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db_session.execute.return_value = mock_result

        manager = AdaptiveScoringTierManager(mock_db_session)
        tier = await manager.detect_tier()

        assert tier == ScoringTier.MINIMAL
        tier_config = manager.get_tier_config()
        assert tier_config.min_notes == 0
        assert tier_config.max_notes == 200
        assert tier_config.confidence_warnings is True

    @pytest.mark.asyncio
    async def test_tier0_activated_for_one_note(self, mock_db_session):
        """Test that MINIMAL tier is selected when there is exactly 1 note."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_db_session.execute.return_value = mock_result

        manager = AdaptiveScoringTierManager(mock_db_session)
        tier = await manager.detect_tier(force_refresh=True)

        assert tier == ScoringTier.MINIMAL

    @pytest.mark.asyncio
    async def test_tier0_activated_for_199_notes(self, mock_db_session):
        """Test that MINIMAL tier is selected for 199 notes (just below boundary)."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 199
        mock_db_session.execute.return_value = mock_result

        manager = AdaptiveScoringTierManager(mock_db_session)
        tier = await manager.detect_tier(force_refresh=True)

        assert tier == ScoringTier.MINIMAL
        note_count = await manager.get_note_count(use_cache=False)
        assert note_count == 199

    @pytest.mark.asyncio
    async def test_tier05_activated_at_exactly_200_notes(self, mock_db_session):
        """
        Test smooth transition to LIMITED tier at exactly 200 notes.
        This is the boundary case - tier changes from MINIMAL to LIMITED.
        """
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 200
        mock_db_session.execute.return_value = mock_result

        manager = AdaptiveScoringTierManager(mock_db_session)
        tier = await manager.detect_tier(force_refresh=True)

        assert tier == ScoringTier.LIMITED
        note_count = await manager.get_note_count(use_cache=False)
        assert note_count == 200

        tier_config = manager.get_tier_config()
        assert tier_config.min_notes == 200
        assert tier_config.max_notes == 1000

    @pytest.mark.asyncio
    async def test_tier05_activated_for_201_notes(self, mock_db_session):
        """Test that LIMITED tier is selected for 201 notes (just above boundary)."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 201
        mock_db_session.execute.return_value = mock_result

        manager = AdaptiveScoringTierManager(mock_db_session)
        tier = await manager.detect_tier(force_refresh=True)

        assert tier == ScoringTier.LIMITED
        note_count = await manager.get_note_count(use_cache=False)
        assert note_count == 201

    @pytest.mark.asyncio
    async def test_tier_transition_detection(self, mock_db_session):
        """
        Test that tier transitions are detected correctly when note count changes.
        Simulates system growth from 0 to 200+ notes.
        """
        mock_result_0 = MagicMock()
        mock_result_0.scalar_one.return_value = 0
        mock_result_100 = MagicMock()
        mock_result_100.scalar_one.return_value = 100
        mock_result_200 = MagicMock()
        mock_result_200.scalar_one.return_value = 200

        mock_db_session.execute.side_effect = [
            mock_result_0,
            mock_result_100,
            mock_result_200,
        ]

        manager = AdaptiveScoringTierManager(mock_db_session)

        tier_0 = await manager.detect_tier()
        assert tier_0 == ScoringTier.MINIMAL

        tier_100 = await manager.detect_tier(force_refresh=True)
        assert tier_100 == ScoringTier.MINIMAL

        tier_200 = await manager.detect_tier(force_refresh=True)
        assert tier_200 == ScoringTier.LIMITED


class TestBayesianScorerIntegration:
    """
    Integration tests for BayesianAverageScorer with the tier system.
    """

    @pytest.mark.asyncio
    async def test_bayesian_scorer_usage_in_tier0(self, mock_db_session):
        """
        Test that BayesianAverageScorer can be used within tier 0 context.
        Verifies that the scorer produces consistent results.
        """
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db_session.execute.return_value = mock_result

        manager = AdaptiveScoringTierManager(mock_db_session)
        tier = await manager.detect_tier()

        assert tier == ScoringTier.MINIMAL

        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)
        score = scorer.calculate_score([0.6, 0.7, 0.8])

        assert 0.0 <= score <= 1.0
        assert score > 0.5

    @pytest.mark.asyncio
    async def test_bayesian_scorer_with_system_prior_update(self, mock_db_session):
        """
        Test BayesianAverageScorer prior update based on system data.
        Simulates updating the prior when system reaches 50+ rated notes.
        """
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 50
        mock_db_session.execute.return_value = mock_result

        scorer = BayesianAverageScorer(confidence_param=2.0, prior_mean=0.5)

        system_average = 0.65
        scorer.update_prior_from_system_average(system_average)

        assert scorer.m == system_average

        score = scorer.calculate_score([0.6, 0.7])
        expected = (2.0 * 0.65 + 1.3) / (2.0 + 2)
        assert abs(score - expected) < 1e-9

    @pytest.mark.asyncio
    async def test_tier_override_forces_minimal(self, mock_db_session):
        """
        Test that tier override can force MINIMAL tier even with many notes.
        Useful for testing BayesianAverageScorer behavior.
        """
        manager = AdaptiveScoringTierManager(
            mock_db_session,
            tier_override=ScoringTier.MINIMAL,
        )

        tier = await manager.detect_tier()

        assert tier == ScoringTier.MINIMAL
        tier_info = manager.get_tier_info()
        assert tier_info["is_override"] is True


class TestTierBoundaryEdgeCases:
    """
    Edge case tests for tier boundaries.
    """

    def test_tier_selection_for_boundary_values(self):
        """Test tier selection for exact boundary values."""
        assert get_tier_for_note_count(0) == ScoringTier.MINIMAL
        assert get_tier_for_note_count(1) == ScoringTier.MINIMAL
        assert get_tier_for_note_count(199) == ScoringTier.MINIMAL

        assert get_tier_for_note_count(200) == ScoringTier.LIMITED
        assert get_tier_for_note_count(201) == ScoringTier.LIMITED
        assert get_tier_for_note_count(999) == ScoringTier.LIMITED

        assert get_tier_for_note_count(1000) == ScoringTier.BASIC

    @pytest.mark.asyncio
    async def test_edge_case_handler_for_200_notes(self, mock_db_session):
        """Test the explicit edge case handler for exactly 200 notes."""
        manager = AdaptiveScoringTierManager(mock_db_session)

        tier = await manager.handle_edge_case(200)

        assert tier == ScoringTier.LIMITED

    @pytest.mark.asyncio
    async def test_tier_config_warnings_for_minimal_tier(self, mock_db_session):
        """Test that MINIMAL tier has confidence warnings enabled."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db_session.execute.return_value = mock_result

        manager = AdaptiveScoringTierManager(mock_db_session)
        await manager.detect_tier()

        tier_config = manager.get_tier_config(ScoringTier.MINIMAL)

        assert tier_config.confidence_warnings is True
        assert tier_config.requires_full_pipeline is False
        assert tier_config.enable_clustering is False


class TestTierCacheInvalidation:
    """
    Tests for tier cache invalidation when note count changes.
    """

    @pytest.mark.asyncio
    async def test_cache_refresh_on_note_addition(self, mock_db_session):
        """
        Test that cache is refreshed when notes are added.
        Ensures tier detection reflects current state.
        """
        mock_result_0 = MagicMock()
        mock_result_0.scalar_one.return_value = 0
        mock_result_200 = MagicMock()
        mock_result_200.scalar_one.return_value = 200

        mock_db_session.execute.side_effect = [mock_result_0, mock_result_200]

        manager = AdaptiveScoringTierManager(mock_db_session)

        tier_initial = await manager.detect_tier()
        assert tier_initial == ScoringTier.MINIMAL

        tier_without_refresh = await manager.detect_tier(force_refresh=False)
        assert tier_without_refresh == ScoringTier.MINIMAL

        tier_with_refresh = await manager.detect_tier(force_refresh=True)
        assert tier_with_refresh == ScoringTier.LIMITED

    @pytest.mark.asyncio
    async def test_manual_cache_clear(self, mock_db_session):
        """Test manual cache clearing."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db_session.execute.return_value = mock_result

        manager = AdaptiveScoringTierManager(mock_db_session)

        await manager.detect_tier()
        assert manager._cached_note_count is not None

        manager.clear_cache()
        assert manager._cached_note_count is None
