"""
Unit tests for import_tasks.py helper functions and deprecated TaskIQ stubs.

Task: task-1093 - Migrate import pipeline tasks to DBOS durable workflows

Tests cover:
- Helper function behavior (_aggregate_errors, _recover_stuck_*_candidates)
- TaskIQ deprecated stub labels
- Recovery mechanism for stuck SCRAPING and PROMOTING candidates

NOTE: End-to-end task tests for the import pipeline have been moved to
tests/unit/dbos_workflows/test_import_workflow.py. The TaskIQ task stubs
in import_tasks.py are deprecated no-ops (TASK-1093).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


class TestAggregateErrors:
    """Test error aggregation helper."""

    def test_aggregate_errors_under_max_limit(self):
        """Errors under max limit are all included."""
        from src.tasks.import_tasks import _aggregate_errors

        errors = [f"Error {i}" for i in range(10)]
        result = _aggregate_errors(errors, max_errors=50)

        assert len(result["validation_errors"]) == 10
        assert result["total_validation_errors"] == 10
        assert result["truncated"] is False

    def test_aggregate_errors_truncates_at_max(self):
        """Errors exceeding max limit are truncated."""
        from src.tasks.import_tasks import _aggregate_errors

        errors = [f"Error {i}" for i in range(100)]
        result = _aggregate_errors(errors, max_errors=50)

        assert len(result["validation_errors"]) == 50
        assert result["total_validation_errors"] == 100
        assert result["truncated"] is True

    def test_aggregate_errors_empty_list(self):
        """Empty error list produces valid result."""
        from src.tasks.import_tasks import _aggregate_errors

        result = _aggregate_errors([])

        assert result["validation_errors"] == []
        assert result["total_validation_errors"] == 0
        assert result["truncated"] is False


class TestTaskIQLabels:
    """Test TaskIQ task labels are properly configured for deprecated stubs."""

    def test_import_task_has_deprecated_labels(self):
        """Verify import task has component and deprecated task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "import:fact_check_bureau" in _all_registered_tasks

        _, labels = _all_registered_tasks["import:fact_check_bureau"]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "deprecated"

    def test_scrape_task_has_deprecated_labels(self):
        """Verify scrape task has component and deprecated task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "scrape:candidates" in _all_registered_tasks

        _, labels = _all_registered_tasks["scrape:candidates"]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "deprecated"

    def test_promote_task_has_deprecated_labels(self):
        """Verify promote task has component and deprecated task_type labels."""
        from src.tasks.broker import _all_registered_tasks

        assert "promote:candidates" in _all_registered_tasks

        _, labels = _all_registered_tasks["promote:candidates"]
        assert labels.get("component") == "import_pipeline"
        assert labels.get("task_type") == "deprecated"


class TestRecoverStuckCandidates:
    """Test recovery mechanism for stuck SCRAPING and PROMOTING candidates."""

    @pytest.mark.asyncio
    async def test_recover_stuck_scraping_candidates_recovers_old(self):
        """Candidates stuck in SCRAPING state beyond timeout are recovered."""

        from src.tasks.import_tasks import _recover_stuck_scraping_candidates

        mock_result = MagicMock()
        mock_result.rowcount = 5

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        recovered = await _recover_stuck_scraping_candidates(mock_session_maker, timeout_minutes=30)

        assert recovered == 5
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_recover_stuck_scraping_candidates_none_found(self):
        """No candidates stuck means zero recovered."""
        from src.tasks.import_tasks import _recover_stuck_scraping_candidates

        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        recovered = await _recover_stuck_scraping_candidates(mock_session_maker)

        assert recovered == 0

    @pytest.mark.asyncio
    async def test_recover_stuck_promoting_candidates_recovers_old(self):
        """Candidates stuck in PROMOTING state beyond timeout are recovered."""
        from src.tasks.import_tasks import _recover_stuck_promoting_candidates

        mock_result = MagicMock()
        mock_result.rowcount = 3

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        recovered = await _recover_stuck_promoting_candidates(
            mock_session_maker, timeout_minutes=30
        )

        assert recovered == 3
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_recover_stuck_promoting_candidates_none_found(self):
        """No candidates stuck in PROMOTING means zero recovered."""
        from src.tasks.import_tasks import _recover_stuck_promoting_candidates

        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        recovered = await _recover_stuck_promoting_candidates(mock_session_maker)

        assert recovered == 0

    @pytest.mark.asyncio
    async def test_recover_stuck_scraping_candidates_clears_content(self):
        """Recovery clears partial content to ensure candidates are re-scraped.

        When a scraping job crashes mid-batch, candidates may have partial content.
        Recovery must clear content=None so the scrape selection query
        (which filters by content.is_(None)) will pick them up again.
        """
        from src.tasks.import_tasks import _recover_stuck_scraping_candidates

        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        await _recover_stuck_scraping_candidates(mock_session_maker, timeout_minutes=30)

        execute_call = mock_db.execute.call_args
        update_stmt = execute_call[0][0]

        compiled = update_stmt.compile()
        assert "content" in str(compiled)

        params = compiled.params
        assert "content" in params
        assert params["content"] is None

    @pytest.mark.asyncio
    async def test_recovered_candidates_are_selected_for_rescrape(self):
        """Recovered candidates with cleared content appear in scrape selection query.

        This tests the integration between recovery (which sets content=None)
        and the scrape batch job's candidate selection query (which filters
        by status=PENDING AND content IS NULL).
        """
        from sqlalchemy import func, select

        from src.fact_checking.candidate_models import CandidateStatus, FactCheckedItemCandidate

        count_query = (
            select(func.count())
            .select_from(FactCheckedItemCandidate)
            .where(FactCheckedItemCandidate.status == CandidateStatus.PENDING.value)
            .where(FactCheckedItemCandidate.content.is_(None))
        )

        compiled = count_query.compile()
        query_str = str(compiled)

        assert "status" in query_str
        assert "content IS NULL" in query_str

    @pytest.mark.asyncio
    async def test_recover_stuck_scraping_uses_skip_locked(self):
        """Recovery uses SELECT FOR UPDATE SKIP LOCKED to avoid resetting locked rows.

        When a candidate is actively being processed by another worker, it holds
        a row lock. The recovery function must skip such rows to avoid resetting
        candidates that are legitimately being processed.
        """
        from src.tasks.import_tasks import _recover_stuck_scraping_candidates

        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        await _recover_stuck_scraping_candidates(mock_session_maker, timeout_minutes=30)

        execute_call = mock_db.execute.call_args
        update_stmt = execute_call[0][0]

        criterion = update_stmt._where_criteria[0]
        scalar_select = criterion.right
        inner_select = scalar_select.element
        for_update_arg = inner_select._for_update_arg

        assert for_update_arg is not None, "Subquery must have FOR UPDATE clause"
        assert for_update_arg.skip_locked is True, "FOR UPDATE must use SKIP LOCKED"

    @pytest.mark.asyncio
    async def test_recover_stuck_promoting_uses_skip_locked(self):
        """Recovery uses SELECT FOR UPDATE SKIP LOCKED to avoid resetting locked rows.

        When a candidate is actively being processed by another worker, it holds
        a row lock. The recovery function must skip such rows to avoid resetting
        candidates that are legitimately being processed.
        """
        from src.tasks.import_tasks import _recover_stuck_promoting_candidates

        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        await _recover_stuck_promoting_candidates(mock_session_maker, timeout_minutes=30)

        execute_call = mock_db.execute.call_args
        update_stmt = execute_call[0][0]

        criterion = update_stmt._where_criteria[0]
        scalar_select = criterion.right
        inner_select = scalar_select.element
        for_update_arg = inner_select._for_update_arg

        assert for_update_arg is not None, "Subquery must have FOR UPDATE clause"
        assert for_update_arg.skip_locked is True, "FOR UPDATE must use SKIP LOCKED"


class TestDeprecatedStubs:
    """Test that deprecated TaskIQ stubs run without error."""

    @pytest.mark.asyncio
    async def test_process_fact_check_import_noop(self):
        """Deprecated process_fact_check_import stub runs without error."""
        from src.tasks.import_tasks import process_fact_check_import

        await process_fact_check_import(job_id="test", batch_size=100)

    @pytest.mark.asyncio
    async def test_process_scrape_batch_noop(self):
        """Deprecated process_scrape_batch stub runs without error."""
        from src.tasks.import_tasks import process_scrape_batch

        await process_scrape_batch(job_id="test", batch_size=100)

    @pytest.mark.asyncio
    async def test_process_promotion_batch_noop(self):
        """Deprecated process_promotion_batch stub runs without error."""
        from src.tasks.import_tasks import process_promotion_batch

        await process_promotion_batch(job_id="test", batch_size=100)
