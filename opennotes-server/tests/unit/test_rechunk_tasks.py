"""
Unit tests for rechunk task service singletons and deprecated TaskIQ stubs.

Task: task-909.06 - Add test coverage for TaskIQ rechunk tasks
Task: task-1095.05 - Dead code cleanup (removed chunk_fact_check_item_task,
    process_fact_check_rechunk_task, deadlock retry helpers)

The actual rechunk logic has been migrated to DBOS workflows. Tests for DBOS
workflow behavior are in tests/unit/dbos_workflows/test_rechunk_workflow.py.
"""

import logging
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestTaskIQLabels:
    """Test TaskIQ labels are properly configured (task-909.07)."""

    def test_fact_check_task_registered_as_deprecated(self):
        """Verify fact check rechunk task is registered as deprecated no-op (TASK-1058.03).

        This task was migrated to DBOS in TASK-1056. A deprecated no-op handler
        exists to drain stale messages from JetStream that were enqueued before
        the migration.
        """
        import src.tasks.rechunk_tasks  # noqa: F401 - import triggers registration
        from src.tasks.broker import _all_registered_tasks

        assert "rechunk:fact_check" in _all_registered_tasks

        _, labels = _all_registered_tasks["rechunk:fact_check"]
        assert labels.get("component") == "rechunk"
        assert labels.get("task_type") == "deprecated"

    def test_chunk_fact_check_item_task_registered_as_deprecated(self):
        """Verify chunk fact check item task is registered as deprecated no-op (TASK-1058.03).

        This task was migrated to DBOS in TASK-1056. A deprecated no-op handler
        exists to drain stale messages from JetStream that were enqueued before
        the migration.
        """
        import src.tasks.rechunk_tasks  # noqa: F401 - import triggers registration
        from src.tasks.broker import _all_registered_tasks

        assert "chunk:fact_check_item" in _all_registered_tasks

        _, labels = _all_registered_tasks["chunk:fact_check_item"]
        assert labels.get("component") == "rechunk"
        assert labels.get("task_type") == "deprecated"

    def test_previously_seen_task_has_labels(self):
        """Verify previously seen rechunk task has component and task_type labels."""
        import src.tasks.rechunk_tasks  # noqa: F401 - import triggers registration
        from src.tasks.broker import _all_registered_tasks

        assert "rechunk:previously_seen" in _all_registered_tasks

        _, labels = _all_registered_tasks["rechunk:previously_seen"]
        assert labels.get("component") == "rechunk"
        assert labels.get("task_type") == "deprecated"


class TestDeprecatedNoOpHandlers:
    """Test deprecated no-op handlers drain legacy messages (TASK-1058.03)."""

    @pytest.mark.asyncio
    async def test_deprecated_fact_check_rechunk_task_logs_and_returns_none(self, caplog):
        """Verify deprecated handler logs warning and returns None."""
        from src.tasks.rechunk_tasks import deprecated_fact_check_rechunk_task

        with caplog.at_level(logging.INFO):
            result = await deprecated_fact_check_rechunk_task(
                "arg1", "arg2", key1="value1", key2="value2"
            )

        assert result is None
        assert "Received deprecated rechunk:fact_check message - discarding" in caplog.text

    @pytest.mark.asyncio
    async def test_deprecated_chunk_fact_check_item_task_logs_and_returns_none(self, caplog):
        """Verify deprecated handler logs warning and returns None."""
        from src.tasks.rechunk_tasks import deprecated_chunk_fact_check_item_task

        with caplog.at_level(logging.INFO):
            result = await deprecated_chunk_fact_check_item_task(
                "fact_check_id", community_server_id="community_id"
            )

        assert result is None
        assert "Received deprecated chunk:fact_check_item message - discarding" in caplog.text

    @pytest.mark.asyncio
    async def test_deprecated_handlers_accept_any_arguments(self):
        """Verify deprecated handlers accept any args/kwargs without error."""
        from src.tasks.rechunk_tasks import (
            deprecated_chunk_fact_check_item_task,
            deprecated_fact_check_rechunk_task,
        )

        result1 = await deprecated_fact_check_rechunk_task()
        assert result1 is None

        result2 = await deprecated_fact_check_rechunk_task("a", "b", "c", x=1, y=2, z=3)
        assert result2 is None

        result3 = await deprecated_chunk_fact_check_item_task()
        assert result3 is None

        result4 = await deprecated_chunk_fact_check_item_task(foo="bar", baz=123)
        assert result4 is None


class TestPromotionEnqueuesChunkingTask:
    """Test that promotion enqueues chunking task via routing function (task-1030, task-1056.01)."""

    @pytest.mark.asyncio
    async def test_promotion_enqueues_chunking_task(self):
        """Successful promotion enqueues a chunking task via enqueue_single_fact_check_chunk."""
        candidate_id = uuid4()
        fact_check_item_id = uuid4()

        mock_candidate = MagicMock()
        mock_candidate.id = candidate_id
        mock_candidate.status = "scraped"
        mock_candidate.content = "Test content"
        mock_candidate.rating = "Mixed"
        mock_candidate.dataset_name = "test"
        mock_candidate.dataset_tags = ["test"]
        mock_candidate.title = "Test Title"
        mock_candidate.summary = "Test summary"
        mock_candidate.source_url = "https://example.com"
        mock_candidate.original_id = "test-123"
        mock_candidate.published_date = None
        mock_candidate.rating_details = None
        mock_candidate.extracted_data = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        with (
            patch("src.batch_jobs.rechunk_service.enqueue_single_fact_check_chunk") as mock_enqueue,
            patch(
                "src.fact_checking.import_pipeline.promotion.FactCheckItem"
            ) as mock_fact_check_class,
        ):
            mock_enqueue.return_value = True
            mock_fact_check_item = MagicMock()
            mock_fact_check_item.id = fact_check_item_id
            mock_fact_check_class.return_value = mock_fact_check_item

            from src.fact_checking.import_pipeline.promotion import promote_candidate

            result = await promote_candidate(mock_session, candidate_id)

            assert result is True
            mock_enqueue.assert_called_once_with(
                fact_check_id=fact_check_item_id,
                community_server_id=None,
            )

    @pytest.mark.asyncio
    async def test_promotion_succeeds_even_if_chunk_enqueue_fails(self):
        """Promotion still succeeds if chunking task enqueue fails."""
        candidate_id = uuid4()
        fact_check_item_id = uuid4()

        mock_candidate = MagicMock()
        mock_candidate.id = candidate_id
        mock_candidate.status = "scraped"
        mock_candidate.content = "Test content"
        mock_candidate.rating = "Mixed"
        mock_candidate.dataset_name = "test"
        mock_candidate.dataset_tags = ["test"]
        mock_candidate.title = "Test Title"
        mock_candidate.summary = "Test summary"
        mock_candidate.source_url = "https://example.com"
        mock_candidate.original_id = "test-123"
        mock_candidate.published_date = None
        mock_candidate.rating_details = None
        mock_candidate.extracted_data = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_candidate

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        with (
            patch("src.batch_jobs.rechunk_service.enqueue_single_fact_check_chunk") as mock_enqueue,
            patch(
                "src.fact_checking.import_pipeline.promotion.FactCheckItem"
            ) as mock_fact_check_class,
        ):
            mock_enqueue.side_effect = Exception("NATS connection failed")
            mock_fact_check_item = MagicMock()
            mock_fact_check_item.id = fact_check_item_id
            mock_fact_check_class.return_value = mock_fact_check_item

            from src.fact_checking.import_pipeline.promotion import promote_candidate

            result = await promote_candidate(mock_session, candidate_id)

            assert result is True
            mock_enqueue.assert_called_once()


class TestServiceSingletons:
    """Test service singleton pattern for get_chunk_embedding_service (TASK-1058.27)."""

    def test_get_chunk_embedding_service_returns_singleton(self):
        """Verify get_chunk_embedding_service returns the same instance on multiple calls."""
        from src.tasks.rechunk_tasks import (
            get_chunk_embedding_service,
            reset_task_services,
        )

        reset_task_services()

        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_client_manager = MagicMock()
        mock_encryption_service = MagicMock()

        mock_settings = MagicMock()
        mock_settings.ENCRYPTION_MASTER_KEY = "test-key"

        @contextmanager
        def mock_use_chunking_service_sync():
            yield mock_chunking_service

        with (
            patch("src.tasks.rechunk_tasks.get_settings", return_value=mock_settings),
            patch(
                "src.tasks.rechunk_tasks.use_chunking_service_sync",
                side_effect=mock_use_chunking_service_sync,
            ),
            patch("src.tasks.rechunk_tasks.LLMService", return_value=mock_llm_service),
            patch("src.tasks.rechunk_tasks.LLMClientManager", return_value=mock_llm_client_manager),
            patch(
                "src.tasks.rechunk_tasks.EncryptionService", return_value=mock_encryption_service
            ),
        ):
            service1 = get_chunk_embedding_service()
            service2 = get_chunk_embedding_service()

            assert service1 is service2

        reset_task_services()

    def test_reset_task_services_clears_singletons(self):
        """Verify reset_task_services clears all singleton instances including ChunkingService."""
        from src.tasks.rechunk_tasks import (
            get_chunk_embedding_service,
            reset_task_services,
        )

        reset_task_services()

        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_client_manager = MagicMock()
        mock_encryption_service = MagicMock()

        mock_settings = MagicMock()
        mock_settings.ENCRYPTION_MASTER_KEY = "test-key"

        @contextmanager
        def mock_use_chunking_service_sync():
            yield mock_chunking_service

        with (
            patch("src.tasks.rechunk_tasks.get_settings", return_value=mock_settings),
            patch(
                "src.tasks.rechunk_tasks.use_chunking_service_sync",
                side_effect=mock_use_chunking_service_sync,
            ),
            patch("src.tasks.rechunk_tasks.LLMService", return_value=mock_llm_service),
            patch("src.tasks.rechunk_tasks.LLMClientManager", return_value=mock_llm_client_manager),
            patch(
                "src.tasks.rechunk_tasks.EncryptionService", return_value=mock_encryption_service
            ),
            patch("src.tasks.rechunk_tasks.reset_chunking_service") as mock_reset_chunking,
        ):
            service_before = get_chunk_embedding_service()
            assert service_before is not None

            reset_task_services()

            import src.tasks.rechunk_tasks as module

            assert module._chunk_embedding_service is None
            assert module._encryption_service is None
            assert module._llm_client_manager is None
            assert module._llm_service is None
            mock_reset_chunking.assert_called_once()

    def test_singleton_pattern_is_thread_safe(self):
        """Verify singleton pattern uses proper locking for thread safety."""
        import threading

        from src.tasks.rechunk_tasks import (
            get_chunk_embedding_service,
            reset_task_services,
        )

        reset_task_services()

        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_client_manager = MagicMock()
        mock_encryption_service = MagicMock()

        mock_settings = MagicMock()
        mock_settings.ENCRYPTION_MASTER_KEY = "test-key"

        @contextmanager
        def mock_use_chunking_service_sync():
            yield mock_chunking_service

        services = []
        errors = []
        num_threads = 10
        barrier = threading.Barrier(num_threads)

        def get_service():
            try:
                barrier.wait()
                service = get_chunk_embedding_service()
                services.append(service)
            except Exception as e:
                errors.append(e)

        with (
            patch("src.tasks.rechunk_tasks.get_settings", return_value=mock_settings),
            patch(
                "src.tasks.rechunk_tasks.use_chunking_service_sync",
                side_effect=mock_use_chunking_service_sync,
            ),
            patch("src.tasks.rechunk_tasks.LLMService", return_value=mock_llm_service),
            patch(
                "src.tasks.rechunk_tasks.LLMClientManager",
                return_value=mock_llm_client_manager,
            ),
            patch(
                "src.tasks.rechunk_tasks.EncryptionService",
                return_value=mock_encryption_service,
            ),
        ):
            threads = [threading.Thread(target=get_service) for _ in range(num_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors
        assert len(services) == num_threads
        assert all(s is services[0] for s in services)

        reset_task_services()
