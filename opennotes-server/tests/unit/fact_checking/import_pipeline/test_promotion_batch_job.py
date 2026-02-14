"""
Unit tests for promotion batch job TaskIQ task labels and promotion helpers.

Task: task-1093 - Migrate import pipeline tasks to DBOS durable workflows

NOTE: End-to-end tests for the promotion batch pipeline have been moved to
tests/unit/dbos_workflows/test_import_workflow.py. The TaskIQ task stubs
in import_tasks.py are deprecated no-ops (TASK-1093).

Remaining tests verify:
- TaskIQ task label configuration for deprecated stubs
- _validate_candidate_for_promotion helper behavior
- promote_candidate function with chunking routing (DBOS enqueue)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.batch_jobs import PROMOTION_JOB_TYPE

pytestmark = pytest.mark.unit


class TestPromotionBatchTaskLabels:
    """Test TaskIQ task labels are properly configured for deprecated stub."""

    def test_promotion_batch_task_has_deprecated_labels(self):
        """Verify promotion batch task has component and deprecated task_type labels."""
        import src.tasks.import_tasks  # noqa: F401
        from src.tasks.broker import get_registered_tasks

        registered_tasks = get_registered_tasks()
        assert PROMOTION_JOB_TYPE in registered_tasks

        _, labels = registered_tasks[PROMOTION_JOB_TYPE]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "deprecated"


class TestPromotionBatchEmptyContentHandling:
    """Test handling of candidates with empty string content.

    Task: task-1008.07 - Add empty content validation in promotion query

    The promotion queries filter on content.is_not(None) but empty strings ('')
    would still pass. This test class verifies that empty content candidates
    are excluded at the query level to avoid wasted processing.
    """

    @pytest.mark.asyncio
    async def test_candidate_with_empty_content_is_not_promoted(self):
        """Verify candidates with empty string content are not promoted."""
        from src.fact_checking.import_pipeline.promotion import (
            _validate_candidate_for_promotion,
        )

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.content = ""
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"

        result = _validate_candidate_for_promotion(mock_candidate, candidate_id)

        assert result is not None
        assert "without content" in result

    @pytest.mark.asyncio
    async def test_candidate_with_none_content_is_not_promoted(self):
        """Verify candidates with None content are not promoted."""
        from src.fact_checking.import_pipeline.promotion import (
            _validate_candidate_for_promotion,
        )

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.content = None
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"

        result = _validate_candidate_for_promotion(mock_candidate, candidate_id)

        assert result is not None
        assert "without content" in result

    @pytest.mark.asyncio
    async def test_candidate_with_valid_content_passes_validation(self):
        """Verify candidates with valid content pass validation."""
        from src.fact_checking.import_pipeline.promotion import (
            _validate_candidate_for_promotion,
        )

        candidate_id = uuid4()
        mock_candidate = MagicMock()
        mock_candidate.content = "Valid scraped content"
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"

        result = _validate_candidate_for_promotion(mock_candidate, candidate_id)

        assert result is None


class TestPromotionChunkingRouting:
    """Test chunking routing through DBOS for single items (task-1056.01)."""

    @pytest.mark.asyncio
    async def test_promote_candidate_calls_enqueue_single_fact_check_chunk(self):
        """Verify promote_candidate calls enqueue_single_fact_check_chunk after promotion."""
        from unittest.mock import PropertyMock

        from src.fact_checking.import_pipeline.promotion import promote_candidate

        candidate_id = uuid4()
        fact_check_item_id = uuid4()

        mock_candidate = MagicMock()
        mock_candidate.id = candidate_id
        mock_candidate.content = "Valid content for promotion"
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"
        mock_candidate.dataset_name = "test_dataset"
        mock_candidate.dataset_tags = ["tag1"]
        mock_candidate.title = "Test Title"
        mock_candidate.summary = "Test summary"
        mock_candidate.source_url = "https://example.com"
        mock_candidate.original_id = "orig123"
        mock_candidate.published_date = None
        mock_candidate.rating_details = {}
        mock_candidate.extracted_data = {}

        mock_session = AsyncMock()

        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = mock_candidate
        mock_update_result = MagicMock()
        mock_session.execute = AsyncMock(side_effect=[mock_select_result, mock_update_result])
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.add = MagicMock()

        with patch(
            "src.batch_jobs.rechunk_service.enqueue_single_fact_check_chunk"
        ) as mock_enqueue:
            mock_enqueue.return_value = True

            with patch(
                "src.fact_checking.import_pipeline.promotion.FactCheckItem"
            ) as mock_fact_check_class:
                mock_fact_check_item = MagicMock()
                type(mock_fact_check_item).id = PropertyMock(return_value=fact_check_item_id)
                mock_fact_check_class.return_value = mock_fact_check_item

                result = await promote_candidate(mock_session, candidate_id)

            assert result is True
            mock_enqueue.assert_called_once_with(
                fact_check_id=fact_check_item_id,
                community_server_id=None,
            )

    @pytest.mark.asyncio
    async def test_promote_candidate_handles_enqueue_failure_gracefully(self):
        """Verify promote_candidate succeeds even if chunking enqueue fails."""
        from unittest.mock import PropertyMock

        from src.fact_checking.import_pipeline.promotion import promote_candidate

        candidate_id = uuid4()
        fact_check_item_id = uuid4()

        mock_candidate = MagicMock()
        mock_candidate.id = candidate_id
        mock_candidate.content = "Valid content for promotion"
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"
        mock_candidate.dataset_name = "test_dataset"
        mock_candidate.dataset_tags = ["tag1"]
        mock_candidate.title = "Test Title"
        mock_candidate.summary = "Test summary"
        mock_candidate.source_url = "https://example.com"
        mock_candidate.original_id = "orig123"
        mock_candidate.published_date = None
        mock_candidate.rating_details = {}
        mock_candidate.extracted_data = {}

        mock_session = AsyncMock()

        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = mock_candidate
        mock_update_result = MagicMock()
        mock_session.execute = AsyncMock(side_effect=[mock_select_result, mock_update_result])
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.add = MagicMock()

        with patch(
            "src.batch_jobs.rechunk_service.enqueue_single_fact_check_chunk"
        ) as mock_enqueue:
            mock_enqueue.return_value = False

            with patch(
                "src.fact_checking.import_pipeline.promotion.FactCheckItem"
            ) as mock_fact_check_class:
                mock_fact_check_item = MagicMock()
                type(mock_fact_check_item).id = PropertyMock(return_value=fact_check_item_id)
                mock_fact_check_class.return_value = mock_fact_check_item

                result = await promote_candidate(mock_session, candidate_id)

            assert result is True
            mock_enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_promote_candidate_handles_enqueue_exception_gracefully(self):
        """Verify promote_candidate succeeds even if chunking enqueue raises exception."""
        from unittest.mock import PropertyMock

        from src.fact_checking.import_pipeline.promotion import promote_candidate

        candidate_id = uuid4()
        fact_check_item_id = uuid4()

        mock_candidate = MagicMock()
        mock_candidate.id = candidate_id
        mock_candidate.content = "Valid content for promotion"
        mock_candidate.rating = "Mixed"
        mock_candidate.status = "scraped"
        mock_candidate.dataset_name = "test_dataset"
        mock_candidate.dataset_tags = ["tag1"]
        mock_candidate.title = "Test Title"
        mock_candidate.summary = "Test summary"
        mock_candidate.source_url = "https://example.com"
        mock_candidate.original_id = "orig123"
        mock_candidate.published_date = None
        mock_candidate.rating_details = {}
        mock_candidate.extracted_data = {}

        mock_session = AsyncMock()

        mock_select_result = MagicMock()
        mock_select_result.scalar_one_or_none.return_value = mock_candidate
        mock_update_result = MagicMock()
        mock_session.execute = AsyncMock(side_effect=[mock_select_result, mock_update_result])
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.add = MagicMock()

        with patch(
            "src.batch_jobs.rechunk_service.enqueue_single_fact_check_chunk"
        ) as mock_enqueue:
            mock_enqueue.side_effect = Exception("Unexpected error")

            with patch(
                "src.fact_checking.import_pipeline.promotion.FactCheckItem"
            ) as mock_fact_check_class:
                mock_fact_check_item = MagicMock()
                type(mock_fact_check_item).id = PropertyMock(return_value=fact_check_item_id)
                mock_fact_check_class.return_value = mock_fact_check_item

                result = await promote_candidate(mock_session, candidate_id)

            assert result is True
            mock_enqueue.assert_called_once()
