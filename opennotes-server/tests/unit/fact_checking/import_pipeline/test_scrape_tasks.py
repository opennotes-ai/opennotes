"""Unit tests for scrape_tasks.py.

Tests the apply_predicted_rating_if_available function which handles
auto-applying high-confidence predicted ratings to candidates during
the scrape workflow.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.fact_checking.candidate_models import FactCheckedItemCandidate
from src.fact_checking.import_pipeline.scrape_tasks import (
    apply_predicted_rating_if_available,
)


@pytest.mark.unit
class TestApplyPredictedRatingIfAvailable:
    """Tests for apply_predicted_rating_if_available function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_candidate_has_rating(self):
        """Returns None when candidate already has a rating set.

        The function uses atomic UPDATE with WHERE rating IS NULL to prevent TOCTOU races.
        When a candidate already has a rating, the UPDATE returns rowcount=0 and the
        function returns None.
        """
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.rating = "false"
        mock_candidate.predicted_ratings = {"false": 1.0}

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await apply_predicted_rating_if_available(mock_session, mock_candidate)

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_predicted_ratings(self):
        """Returns None when candidate has no predicted_ratings."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.rating = None
        mock_candidate.predicted_ratings = None

        result = await apply_predicted_rating_if_available(mock_session, mock_candidate)

        assert result is None
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_predicted_ratings_empty(self):
        """Returns None when predicted_ratings is empty dict."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.rating = None
        mock_candidate.predicted_ratings = {}

        result = await apply_predicted_rating_if_available(mock_session, mock_candidate)

        assert result is None
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_high_confidence_rating(self):
        """Returns None when no predicted rating meets 1.0 threshold."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.rating = None
        mock_candidate.predicted_ratings = {"false": 0.85, "mostly_false": 0.10}

        result = await apply_predicted_rating_if_available(mock_session, mock_candidate)

        assert result is None
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_applies_rating_when_high_confidence_float(self):
        """Applies rating when predicted_ratings has value >= 1.0 (float)."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.rating = None
        mock_candidate.predicted_ratings = {"false": 1.0}

        result = await apply_predicted_rating_if_available(mock_session, mock_candidate)

        assert result == "false"
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_rating_when_high_confidence_int(self):
        """Applies rating when predicted_ratings has value >= 1.0 (integer from JSON)."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.rating = None
        mock_candidate.predicted_ratings = {"misleading": 1}

        result = await apply_predicted_rating_if_available(mock_session, mock_candidate)

        assert result == "misleading"
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_first_high_confidence_rating(self):
        """Returns first rating when multiple predicted ratings meet threshold."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.rating = None
        mock_candidate.predicted_ratings = {"false": 1.0, "misleading": 1.0}

        result = await apply_predicted_rating_if_available(mock_session, mock_candidate)

        assert result in ["false", "misleading"]
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
