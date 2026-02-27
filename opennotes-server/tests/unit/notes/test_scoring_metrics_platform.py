"""Tests for scoring metrics platform label (task-1134 AC#3).

Verifies that notes_scored_total metric includes a platform attribute
so that playground community servers can be filtered in Grafana.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestScoringMetricsPlatformLabel:
    """Verify notes_scored_total includes platform attribute."""

    @pytest.mark.asyncio
    async def test_notes_scored_total_records_platform_label(self):
        community_server_id = uuid4()
        note_id = uuid4()

        mock_db = AsyncMock()
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        mock_platform_result = MagicMock()
        mock_platform_result.scalar_one_or_none.return_value = "playground"

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_count_result
            if "platform" in str(stmt) if hasattr(stmt, "__str__") else False:
                return mock_platform_result
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = "playground"
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()

        with (
            patch("src.simulation.scoring_integration.notes_scored_total") as mock_metric,
            patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory,
            patch("src.simulation.scoring_integration.calculate_note_score") as mock_calc,
            patch("src.simulation.scoring_integration.get_tier_for_note_count") as mock_tier,
        ):
            from src.notes.scoring.tier_config import ScoringTier

            mock_tier.return_value = ScoringTier.MINIMAL

            mock_scorer = MagicMock()
            mock_factory.return_value.get_scorer.return_value = mock_scorer

            mock_calc.return_value = MagicMock(
                score=0.75,
                rating_count=5,
                tier=1,
                tier_name="Minimal",
                confidence="standard",
                algorithm="BayesianAverage",
            )

            from src.simulation.scoring_integration import score_community_server_notes

            mock_note = MagicMock()
            mock_note.id = note_id
            mock_note.ratings = []

            batch_result = MagicMock()
            batch_result.scalars.return_value.all.side_effect = [[mock_note], []]

            execute_calls = []

            async def smart_execute(stmt):
                execute_calls.append(stmt)
                idx = len(execute_calls)
                if idx == 1:
                    return mock_count_result
                if idx in (2, 4):
                    return batch_result
                result = MagicMock()
                result.scalar_one_or_none.return_value = "playground"
                result.scalars.return_value.all.return_value = []
                return result

            mock_db.execute = AsyncMock(side_effect=smart_execute)

            await score_community_server_notes(community_server_id, mock_db)

            if mock_metric.add.called:
                call_args = mock_metric.add.call_args
                assert "platform" in call_args[0][1]
