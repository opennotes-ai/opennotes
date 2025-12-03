import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.notes.scoring import AdaptiveScoringTierManager, ScorerTimeoutError, ScoringTier

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def tier_manager(mock_db_session):
    return AdaptiveScoringTierManager(db_session=mock_db_session)


@pytest.fixture
def tier_manager_with_override(mock_db_session):
    return AdaptiveScoringTierManager(db_session=mock_db_session, tier_override=ScoringTier.BASIC)


class TestNoteCountQuery:
    @pytest.mark.asyncio
    async def test_get_note_count_queries_database(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 500
        mock_db_session.execute.return_value = mock_result

        count = await tier_manager.get_note_count()

        assert count == 500
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_note_count_caches_result(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 500
        mock_db_session.execute.return_value = mock_result

        count1 = await tier_manager.get_note_count()
        count2 = await tier_manager.get_note_count(use_cache=True)

        assert count1 == count2 == 500
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_note_count_bypasses_cache_when_requested(
        self, tier_manager, mock_db_session
    ):
        mock_result1 = MagicMock()
        mock_result1.scalar_one.return_value = 500
        mock_result2 = MagicMock()
        mock_result2.scalar_one.return_value = 1000

        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        count1 = await tier_manager.get_note_count()
        count2 = await tier_manager.get_note_count(use_cache=False)

        assert count1 == 500
        assert count2 == 1000
        assert mock_db_session.execute.call_count == 2


class TestTierDetection:
    @pytest.mark.asyncio
    async def test_detect_tier_minimal(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 150
        mock_db_session.execute.return_value = mock_result

        tier = await tier_manager.detect_tier()

        assert tier == ScoringTier.MINIMAL

    @pytest.mark.asyncio
    async def test_detect_tier_limited(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 500
        mock_db_session.execute.return_value = mock_result

        tier = await tier_manager.detect_tier()

        assert tier == ScoringTier.LIMITED

    @pytest.mark.asyncio
    async def test_detect_tier_basic(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 2500
        mock_db_session.execute.return_value = mock_result

        tier = await tier_manager.detect_tier()

        assert tier == ScoringTier.BASIC

    @pytest.mark.asyncio
    async def test_detect_tier_intermediate(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 7500
        mock_db_session.execute.return_value = mock_result

        tier = await tier_manager.detect_tier()

        assert tier == ScoringTier.INTERMEDIATE

    @pytest.mark.asyncio
    async def test_detect_tier_advanced(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 25000
        mock_db_session.execute.return_value = mock_result

        tier = await tier_manager.detect_tier()

        assert tier == ScoringTier.ADVANCED

    @pytest.mark.asyncio
    async def test_detect_tier_full(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 75000
        mock_db_session.execute.return_value = mock_result

        tier = await tier_manager.detect_tier()

        assert tier == ScoringTier.FULL


class TestTierOverride:
    @pytest.mark.asyncio
    async def test_override_skips_detection(self, tier_manager_with_override, mock_db_session):
        tier = await tier_manager_with_override.detect_tier()

        assert tier == ScoringTier.BASIC
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_tier_info_shows_override(self, tier_manager_with_override):
        await tier_manager_with_override.detect_tier()
        info = tier_manager_with_override.get_tier_info()

        assert info["is_override"] is True
        assert info["tier"] == "basic"


class TestFallbackMechanism:
    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 25000
        mock_db_session.execute.return_value = mock_result

        tier_manager._scorer_timeout_seconds = 1

        await tier_manager.detect_tier()

        async def slow_scorer():
            await asyncio.sleep(5)
            return "result"

        with pytest.raises(ScorerTimeoutError):
            await tier_manager.run_scorer_with_fallback(slow_scorer, tier=ScoringTier.MINIMAL)

    @pytest.mark.asyncio
    async def test_exception_triggers_fallback(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5000
        mock_db_session.execute.return_value = mock_result

        await tier_manager.detect_tier()

        call_count = {"count": 0}

        async def failing_scorer():
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise ValueError("Scorer failed")
            return "fallback_result"

        result = await tier_manager.run_scorer_with_fallback(
            failing_scorer, tier=ScoringTier.INTERMEDIATE
        )

        assert result == "fallback_result"
        assert call_count["count"] == 2

    def test_get_fallback_tier_returns_previous_tier(self, tier_manager):
        assert tier_manager._get_fallback_tier(ScoringTier.FULL) == ScoringTier.ADVANCED
        assert tier_manager._get_fallback_tier(ScoringTier.ADVANCED) == ScoringTier.INTERMEDIATE
        assert tier_manager._get_fallback_tier(ScoringTier.INTERMEDIATE) == ScoringTier.BASIC
        assert tier_manager._get_fallback_tier(ScoringTier.BASIC) == ScoringTier.LIMITED
        assert tier_manager._get_fallback_tier(ScoringTier.LIMITED) == ScoringTier.MINIMAL
        assert tier_manager._get_fallback_tier(ScoringTier.MINIMAL) is None


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_edge_case_200_notes(self, tier_manager):
        tier = await tier_manager.handle_edge_case(200)
        assert tier == ScoringTier.LIMITED

    @pytest.mark.asyncio
    async def test_edge_case_1000_notes(self, tier_manager):
        tier = await tier_manager.handle_edge_case(1000)
        assert tier == ScoringTier.BASIC

    @pytest.mark.asyncio
    async def test_edge_case_5000_notes(self, tier_manager):
        tier = await tier_manager.handle_edge_case(5000)
        assert tier == ScoringTier.INTERMEDIATE

    @pytest.mark.asyncio
    async def test_edge_case_10000_notes(self, tier_manager):
        tier = await tier_manager.handle_edge_case(10000)
        assert tier == ScoringTier.ADVANCED

    @pytest.mark.asyncio
    async def test_edge_case_50000_notes(self, tier_manager):
        tier = await tier_manager.handle_edge_case(50000)
        assert tier == ScoringTier.FULL


class TestTierTransitions:
    @pytest.mark.asyncio
    async def test_tier_transition_logging(self, tier_manager, mock_db_session, caplog):
        mock_result1 = MagicMock()
        mock_result1.scalar_one.return_value = 500
        mock_result2 = MagicMock()
        mock_result2.scalar_one.return_value = 1500

        mock_db_session.execute.side_effect = [mock_result1, mock_result2]

        tier1 = await tier_manager.detect_tier()
        tier2 = await tier_manager.detect_tier(force_refresh=True)

        assert tier1 == ScoringTier.LIMITED
        assert tier2 == ScoringTier.BASIC

    @pytest.mark.asyncio
    async def test_clear_cache(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 500
        mock_db_session.execute.return_value = mock_result

        await tier_manager.get_note_count()
        assert tier_manager._cached_note_count == 500

        tier_manager.clear_cache()
        assert tier_manager._cached_note_count is None


class TestTierInfo:
    @pytest.mark.asyncio
    async def test_get_tier_info_returns_complete_data(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 2500
        mock_db_session.execute.return_value = mock_result

        await tier_manager.detect_tier()
        info = tier_manager.get_tier_info()

        assert info["tier"] == "basic"
        assert info["min_notes"] == 1000
        assert info["max_notes"] == 5000
        assert info["current_note_count"] == 2500
        assert "scorers" in info
        assert "MFCoreScorer" in info["scorers"]

    def test_get_tier_info_before_detection_returns_error(self, tier_manager):
        info = tier_manager.get_tier_info()
        assert "error" in info

    @pytest.mark.asyncio
    async def test_get_current_tier(self, tier_manager, mock_db_session):
        assert tier_manager.get_current_tier() is None

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 2500
        mock_db_session.execute.return_value = mock_result

        await tier_manager.detect_tier()
        assert tier_manager.get_current_tier() == ScoringTier.BASIC


class TestScorerExecution:
    @pytest.mark.asyncio
    async def test_run_scorer_with_async_function(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 2500
        mock_db_session.execute.return_value = mock_result

        await tier_manager.detect_tier()

        async def async_scorer(value):
            return value * 2

        result = await tier_manager.run_scorer_with_fallback(async_scorer, value=5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_run_scorer_with_sync_function(self, tier_manager, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 2500
        mock_db_session.execute.return_value = mock_result

        await tier_manager.detect_tier()

        def sync_scorer(value):
            return value * 3

        result = await tier_manager.run_scorer_with_fallback(sync_scorer, value=5)
        assert result == 15
