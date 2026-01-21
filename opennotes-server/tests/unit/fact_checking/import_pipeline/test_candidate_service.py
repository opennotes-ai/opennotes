"""Unit tests for candidate_service.py.

Tests the service layer functions for candidate listing, rating, and bulk approval.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.fact_checking.candidate_models import FactCheckedItemCandidate
from src.fact_checking.import_pipeline.candidate_service import (
    _build_filters,
    bulk_approve_from_predictions,
    extract_high_confidence_rating,
    get_candidate_by_id,
    list_candidates,
    set_candidate_rating,
)


class TestExtractHighConfidenceRating:
    """Tests for extract_high_confidence_rating helper function."""

    def test_with_float_1_0(self):
        """Returns rating key when value is exactly 1.0 (float)."""
        predicted_ratings = {"false": 1.0}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result == "false"

    def test_with_int_1(self):
        """Returns rating key when value is 1 (integer from JSON)."""
        predicted_ratings = {"false": 1}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result == "false"

    def test_below_threshold(self):
        """Returns None when all values are below threshold."""
        predicted_ratings = {"false": 0.85, "mostly_false": 0.10}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result is None

    def test_empty_dict(self):
        """Returns None for empty dict."""
        predicted_ratings: dict[str, float] = {}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result is None

    def test_none_input(self):
        """Returns None for None input."""
        result = extract_high_confidence_rating(None, threshold=1.0)
        assert result is None

    def test_custom_threshold(self):
        """Returns rating when value meets custom threshold."""
        predicted_ratings = {"false": 0.85, "mostly_false": 0.10}
        result = extract_high_confidence_rating(predicted_ratings, threshold=0.8)
        assert result == "false"

    def test_multiple_matches_returns_first(self):
        """Returns first matching rating when multiple meet threshold."""
        predicted_ratings = {"false": 1.0, "misleading": 1.0}
        result = extract_high_confidence_rating(predicted_ratings, threshold=1.0)
        assert result in ["false", "misleading"]

    def test_exact_threshold_boundary(self):
        """Returns rating when value equals threshold exactly."""
        predicted_ratings = {"false": 0.9}
        result = extract_high_confidence_rating(predicted_ratings, threshold=0.9)
        assert result == "false"

    def test_just_below_threshold(self):
        """Returns None when value is just below threshold."""
        predicted_ratings = {"false": 0.899999}
        result = extract_high_confidence_rating(predicted_ratings, threshold=0.9)
        assert result is None


@pytest.mark.unit
class TestBuildFilters:
    """Tests for _build_filters helper function."""

    def test_no_filters(self):
        """Returns empty list when no filters provided."""
        result = _build_filters()
        assert result == []

    def test_status_filter(self):
        """Adds status filter when provided."""
        result = _build_filters(status="scraped")
        assert len(result) == 1

    def test_dataset_name_filter(self):
        """Adds dataset_name filter when provided."""
        result = _build_filters(dataset_name="test_dataset")
        assert len(result) == 1

    def test_dataset_tags_filter(self):
        """Adds dataset_tags array overlap filter when provided."""
        result = _build_filters(dataset_tags=["tag1", "tag2"])
        assert len(result) == 1

    def test_rating_null_filter(self):
        """Adds IS NULL filter for rating=null."""
        result = _build_filters(rating_filter="null")
        assert len(result) == 1

    def test_rating_not_null_filter(self):
        """Adds IS NOT NULL filter for rating=not_null."""
        result = _build_filters(rating_filter="not_null")
        assert len(result) == 1

    def test_rating_exact_filter(self):
        """Adds exact match filter for specific rating value."""
        result = _build_filters(rating_filter="false")
        assert len(result) == 1

    def test_has_content_true_filter(self):
        """Adds content IS NOT NULL AND content != '' filters when has_content=True."""
        result = _build_filters(has_content=True)
        assert len(result) == 2

    def test_has_content_false_filter(self):
        """Adds content IS NULL OR content == '' filter when has_content=False."""
        result = _build_filters(has_content=False)
        assert len(result) == 1

    def test_published_date_from_filter(self):
        """Adds >= filter for published_date_from."""
        date_from = datetime.now(UTC) - timedelta(days=30)
        result = _build_filters(published_date_from=date_from)
        assert len(result) == 1

    def test_published_date_to_filter(self):
        """Adds <= filter for published_date_to."""
        date_to = datetime.now(UTC)
        result = _build_filters(published_date_to=date_to)
        assert len(result) == 1

    def test_combined_filters(self):
        """Multiple filters can be combined."""
        result = _build_filters(
            status="scraped",
            dataset_name="test",
            rating_filter="null",
            has_content=True,
        )
        assert len(result) == 5


@pytest.mark.unit
class TestListCandidatesUnit:
    """Unit tests for list_candidates function using mocked session."""

    @pytest.mark.asyncio
    async def test_list_candidates_executes_queries(self):
        """list_candidates executes count and select queries."""
        mock_session = AsyncMock()

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars

        mock_session.execute.side_effect = [mock_count_result, mock_result]

        candidates, total = await list_candidates(mock_session, page=1, page_size=20)

        assert total == 5
        assert candidates == []
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_candidates_with_filters(self):
        """list_candidates applies filters correctly."""
        mock_session = AsyncMock()

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars

        mock_session.execute.side_effect = [mock_count_result, mock_result]

        candidates, total = await list_candidates(
            mock_session,
            page=1,
            page_size=10,
            status="scraped",
            dataset_name="test_dataset",
        )

        assert total == 2
        assert candidates == []


@pytest.mark.unit
class TestGetCandidateByIdUnit:
    """Unit tests for get_candidate_by_id function."""

    @pytest.mark.asyncio
    async def test_returns_candidate_when_found(self):
        """Returns candidate when it exists."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate
        mock_session.execute.return_value = mock_result

        result = await get_candidate_by_id(mock_session, mock_candidate.id)

        assert result == mock_candidate

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Returns None when candidate does not exist."""
        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await get_candidate_by_id(mock_session, uuid4())

        assert result is None


@pytest.mark.unit
class TestSetCandidateRatingUnit:
    """Unit tests for set_candidate_rating function.

    Note: set_candidate_rating uses UPDATE...RETURNING for atomic updates.
    Tests mock the database session to simulate this behavior.
    """

    @pytest.mark.asyncio
    async def test_returns_none_when_candidate_not_found(self):
        """Returns (None, False) when UPDATE...RETURNING finds no matching row."""
        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result, promoted = await set_candidate_rating(mock_session, uuid4(), rating="false")

        assert result is None
        assert promoted is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_rating_without_promotion(self):
        """Updates rating and returns candidate without promotion when auto_promote=False."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.rating = "false"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate
        mock_session.execute.return_value = mock_result

        result, promoted = await set_candidate_rating(
            mock_session, mock_candidate.id, rating="false", auto_promote=False
        )

        assert result == mock_candidate
        assert promoted is False
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_rating_with_promotion(self):
        """Updates rating and triggers promotion when auto_promote=True."""
        mock_session = AsyncMock()
        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate
        mock_session.execute.return_value = mock_result

        with patch(
            "src.fact_checking.import_pipeline.candidate_service.promote_candidate",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_promote:
            result, promoted = await set_candidate_rating(
                mock_session, mock_candidate.id, rating="false", auto_promote=True
            )

        assert result == mock_candidate
        assert promoted is True
        mock_promote.assert_called_once_with(mock_session, mock_candidate.id)


@pytest.mark.unit
class TestBulkApproveFromPredictionsUnit:
    """Unit tests for bulk_approve_from_predictions function.

    Note: bulk_approve_from_predictions uses async iteration with batching.
    Tests mock _iter_candidates_for_bulk_approval to provide test data.
    """

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_candidates_match(self):
        """Returns (0, None) when no candidates have high-confidence predictions."""
        mock_session = AsyncMock()

        async def empty_iter(_session, _filters, _batch_size=100):  # pyright: ignore[reportUnusedParameter]
            return
            yield []  # pyright: ignore[reportUnreachable] - makes this an async generator

        with patch(
            "src.fact_checking.import_pipeline.candidate_service._iter_candidates_for_bulk_approval",
            side_effect=empty_iter,
        ):
            updated, promoted = await bulk_approve_from_predictions(
                mock_session, threshold=1.0, auto_promote=False
            )

        assert updated == 0
        assert promoted is None

    @pytest.mark.asyncio
    async def test_updates_candidates_with_high_confidence_predictions(self):
        """Updates candidates whose predicted_ratings meet threshold."""
        mock_session = AsyncMock()

        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.predicted_ratings = {"false": 1.0}

        async def mock_iter(_session, _filters, _batch_size=100):  # pyright: ignore[reportUnusedParameter]
            yield [mock_candidate]

        with patch(
            "src.fact_checking.import_pipeline.candidate_service._iter_candidates_for_bulk_approval",
            side_effect=mock_iter,
        ):
            updated, promoted = await bulk_approve_from_predictions(
                mock_session, threshold=1.0, auto_promote=False
            )

        assert updated == 1
        assert promoted is None
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_promote_triggers_promotion(self):
        """auto_promote=True triggers promotion for updated candidates."""
        mock_session = AsyncMock()

        mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
        mock_candidate.id = uuid4()
        mock_candidate.predicted_ratings = {"false": 1.0}

        async def mock_iter(_session, _filters, _batch_size=100):  # pyright: ignore[reportUnusedParameter]
            yield [mock_candidate]

        with (
            patch(
                "src.fact_checking.import_pipeline.candidate_service._iter_candidates_for_bulk_approval",
                side_effect=mock_iter,
            ),
            patch(
                "src.fact_checking.import_pipeline.candidate_service.promote_candidate",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_promote,
        ):
            updated, promoted = await bulk_approve_from_predictions(
                mock_session, threshold=1.0, auto_promote=True
            )

        assert updated == 1
        assert promoted == 1
        mock_promote.assert_called_once_with(mock_session, mock_candidate.id)

    @pytest.mark.asyncio
    async def test_limit_restricts_number_of_approvals(self):
        """limit parameter restricts how many candidates are approved."""
        mock_session = AsyncMock()

        mock_candidates = []
        for _ in range(5):
            mock_candidate = MagicMock(spec=FactCheckedItemCandidate)
            mock_candidate.id = uuid4()
            mock_candidate.predicted_ratings = {"false": 1.0}
            mock_candidates.append(mock_candidate)

        async def mock_iter(_session, _filters, _batch_size=100):  # pyright: ignore[reportUnusedParameter]
            yield mock_candidates

        with patch(
            "src.fact_checking.import_pipeline.candidate_service._iter_candidates_for_bulk_approval",
            side_effect=mock_iter,
        ):
            updated, promoted = await bulk_approve_from_predictions(
                mock_session, threshold=1.0, auto_promote=False, limit=2
            )

        assert updated == 2
        assert promoted is None
        assert mock_session.execute.call_count == 2
