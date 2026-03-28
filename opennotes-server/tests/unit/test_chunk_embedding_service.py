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


@pytest.mark.asyncio
class TestChunkEmbeddingServiceLLMCalls:
    """Test that ChunkEmbeddingService passes correct args to LLMService (TASK-1368.03)."""

    async def test_get_or_create_chunks_batch_passes_input_type_document(self):
        """generate_embeddings_batch should receive input_type='document', not db/community_server_id."""
        from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService

        mock_chunking = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_embeddings_batch = AsyncMock(
            return_value=[
                ([0.1] * 1536, "openai", "text-embedding-3-small"),
                ([0.2] * 1536, "openai", "text-embedding-3-small"),
            ]
        )
        service = ChunkEmbeddingService(mock_chunking, mock_llm)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.fact_checking.chunk_embedding_service.pg_insert") as mock_pg_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_pg_insert.return_value.values.return_value = mock_stmt

            post_insert_result = MagicMock()
            chunk1 = MagicMock()
            chunk1.chunk_text_hash = "hash1"
            chunk1.id = uuid4()
            chunk2 = MagicMock()
            chunk2.chunk_text_hash = "hash2"
            chunk2.id = uuid4()
            post_insert_result.scalars.return_value.all.return_value = [chunk1, chunk2]

            call_count = 0

            async def execute_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 1:
                    return mock_result
                return post_insert_result

            mock_db.execute = AsyncMock(side_effect=execute_side_effect)

            with patch(
                "src.fact_checking.chunk_embedding_service.compute_chunk_text_hash",
                side_effect=lambda t: f"hash{['text1', 'text2'].index(t) + 1}",
            ):
                await service.get_or_create_chunks_batch(
                    db=mock_db,
                    chunk_texts=["text1", "text2"],
                    community_server_id=uuid4(),
                )

            mock_llm.generate_embeddings_batch.assert_awaited_once_with(
                ["text1", "text2"], input_type="document"
            )

    async def test_get_or_create_chunk_passes_input_type_document(self):
        """generate_embedding should receive input_type='document', not db/community_server_id."""
        from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService

        mock_chunking = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "openai", "text-embedding-3-small")
        )
        service = ChunkEmbeddingService(mock_chunking, mock_llm)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        chunk_mock = MagicMock()
        chunk_mock.id = uuid4()

        insert_result = MagicMock()
        insert_result.rowcount = 1

        call_count = 0

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result
            if call_count == 2:
                return insert_result
            flush_result = MagicMock()
            flush_result.scalar_one.return_value = chunk_mock
            return flush_result

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.flush = AsyncMock()

        with patch("src.fact_checking.chunk_embedding_service.pg_insert") as mock_pg_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_pg_insert.return_value.values.return_value = mock_stmt

            await service.get_or_create_chunk(
                db=mock_db,
                chunk_text="test chunk text",
                community_server_id=uuid4(),
            )

        mock_llm.generate_embedding.assert_awaited_once_with(
            "test chunk text", input_type="document"
        )
