import threading
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


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
        from src.services.chunk_embedding import (
            get_chunk_embedding_service,
            reset_chunk_embedding_services,
        )

        reset_chunk_embedding_services()

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
            patch("src.services.chunk_embedding.get_settings", return_value=mock_settings),
            patch(
                "src.services.chunk_embedding.use_chunking_service_sync",
                side_effect=mock_use_chunking_service_sync,
            ),
            patch("src.services.chunk_embedding.LLMService", return_value=mock_llm_service),
            patch(
                "src.services.chunk_embedding.LLMClientManager",
                return_value=mock_llm_client_manager,
            ),
            patch(
                "src.services.chunk_embedding.EncryptionService",
                return_value=mock_encryption_service,
            ),
        ):
            service1 = get_chunk_embedding_service()
            service2 = get_chunk_embedding_service()

            assert service1 is service2

        reset_chunk_embedding_services()

    def test_reset_chunk_embedding_services_clears_singletons(self):
        """Verify reset_chunk_embedding_services clears all singleton instances including ChunkingService."""
        from src.services.chunk_embedding import (
            get_chunk_embedding_service,
            reset_chunk_embedding_services,
        )

        reset_chunk_embedding_services()

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
            patch("src.services.chunk_embedding.get_settings", return_value=mock_settings),
            patch(
                "src.services.chunk_embedding.use_chunking_service_sync",
                side_effect=mock_use_chunking_service_sync,
            ),
            patch("src.services.chunk_embedding.LLMService", return_value=mock_llm_service),
            patch(
                "src.services.chunk_embedding.LLMClientManager",
                return_value=mock_llm_client_manager,
            ),
            patch(
                "src.services.chunk_embedding.EncryptionService",
                return_value=mock_encryption_service,
            ),
            patch("src.services.chunk_embedding.reset_chunking_service") as mock_reset_chunking,
        ):
            service_before = get_chunk_embedding_service()
            assert service_before is not None

            reset_chunk_embedding_services()

            import src.services.chunk_embedding as module

            assert module._chunk_embedding_service is None
            assert module._encryption_service is None
            assert module._llm_client_manager is None
            assert module._llm_service is None
            mock_reset_chunking.assert_called_once()

    def test_singleton_pattern_is_thread_safe(self):
        """Verify singleton pattern uses proper locking for thread safety."""
        from src.services.chunk_embedding import (
            get_chunk_embedding_service,
            reset_chunk_embedding_services,
        )

        reset_chunk_embedding_services()

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
            patch("src.services.chunk_embedding.get_settings", return_value=mock_settings),
            patch(
                "src.services.chunk_embedding.use_chunking_service_sync",
                side_effect=mock_use_chunking_service_sync,
            ),
            patch("src.services.chunk_embedding.LLMService", return_value=mock_llm_service),
            patch(
                "src.services.chunk_embedding.LLMClientManager",
                return_value=mock_llm_client_manager,
            ),
            patch(
                "src.services.chunk_embedding.EncryptionService",
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

        reset_chunk_embedding_services()
