"""Unit tests for ChunkEmbeddingService."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
from src.fact_checking.chunk_models import ChunkEmbedding, FactCheckChunk, PreviouslySeenChunk


def _create_mock_db_for_insert(
    *, chunk_exists_initially: bool, inserted: bool, returned_chunk: ChunkEmbedding
) -> AsyncMock:
    """
    Create a mock database session for get_or_create_chunk tests.

    The new implementation uses INSERT ON CONFLICT DO NOTHING, so we need to mock:
    1. First SELECT (check if chunk exists)
    2. INSERT with ON CONFLICT (if chunk doesn't exist initially)
    3. Second SELECT (to fetch the actual chunk after insert)

    Args:
        chunk_exists_initially: Whether the chunk exists on first SELECT
        inserted: Whether the INSERT actually inserted (rowcount > 0)
        returned_chunk: The chunk to return from the final SELECT
    """
    mock_db = AsyncMock()

    if chunk_exists_initially:
        mock_lookup_result = MagicMock()
        mock_lookup_result.scalar_one_or_none.return_value = returned_chunk
        mock_db.execute.return_value = mock_lookup_result
    else:
        mock_lookup_result = MagicMock()
        mock_lookup_result.scalar_one_or_none.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.rowcount = 1 if inserted else 0

        mock_final_lookup = MagicMock()
        mock_final_lookup.scalar_one.return_value = returned_chunk

        mock_db.execute.side_effect = [
            mock_lookup_result,
            mock_insert_result,
            mock_final_lookup,
        ]

    return mock_db


class TestGetOrCreateChunk:
    """Tests for ChunkEmbeddingService.get_or_create_chunk() method."""

    @pytest.mark.asyncio
    async def test_creates_new_chunk_when_not_exists(self):
        """Test that a new chunk is created when text doesn't exist in database."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_text = "This is a test chunk."
        expected_chunk = ChunkEmbedding(
            chunk_text=chunk_text,
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        expected_chunk.id = uuid4()

        mock_db = _create_mock_db_for_insert(
            chunk_exists_initially=False,
            inserted=True,
            returned_chunk=expected_chunk,
        )

        community_server_id = uuid4()

        chunk, is_created = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text=chunk_text,
            community_server_id=community_server_id,
        )

        assert is_created is True
        assert chunk.chunk_text == chunk_text
        mock_llm_service.generate_embedding.assert_called_once_with(
            mock_db, chunk_text, community_server_id
        )

    @pytest.mark.asyncio
    async def test_returns_existing_chunk_when_exists(self):
        """Test that existing chunk is returned without generating new embedding."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        existing_chunk = MagicMock(spec=ChunkEmbedding)
        existing_chunk.id = uuid4()
        existing_chunk.chunk_text = "This is a test chunk."
        existing_chunk.embedding = [0.1] * 1536

        mock_db = _create_mock_db_for_insert(
            chunk_exists_initially=True,
            inserted=False,
            returned_chunk=existing_chunk,
        )

        community_server_id = uuid4()

        chunk, is_created = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text="This is a test chunk.",
            community_server_id=community_server_id,
        )

        assert is_created is False
        assert chunk == existing_chunk
        mock_llm_service.generate_embedding.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_embedding_provider_and_model(self):
        """Test that embedding provider and model are stored with new chunk."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.2] * 1536, "anthropic", "voyage-2")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_text = "Test chunk"
        expected_chunk = ChunkEmbedding(
            chunk_text=chunk_text,
            embedding=[0.2] * 1536,
            embedding_provider="anthropic",
            embedding_model="voyage-2",
        )
        expected_chunk.id = uuid4()

        mock_db = _create_mock_db_for_insert(
            chunk_exists_initially=False,
            inserted=True,
            returned_chunk=expected_chunk,
        )

        chunk, _ = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text=chunk_text,
            community_server_id=uuid4(),
        )

        assert chunk.embedding_provider == "anthropic"
        assert chunk.embedding_model == "voyage-2"

    @pytest.mark.asyncio
    async def test_handles_race_condition_gracefully(self):
        """Test that concurrent chunk creation is handled via INSERT ON CONFLICT.

        Simulates the race condition where:
        1. First SELECT finds no existing chunk
        2. Embedding is generated
        3. INSERT ON CONFLICT DO NOTHING returns rowcount=0 (another request won)
        4. Final SELECT retrieves the winner's chunk
        """
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_text = "Concurrent chunk text"
        winner_chunk = ChunkEmbedding(
            chunk_text=chunk_text,
            embedding=[0.9] * 1536,
            embedding_provider="other-provider",
            embedding_model="other-model",
        )
        winner_chunk.id = uuid4()

        mock_db = _create_mock_db_for_insert(
            chunk_exists_initially=False,
            inserted=False,
            returned_chunk=winner_chunk,
        )

        community_server_id = uuid4()

        chunk, is_created = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text=chunk_text,
            community_server_id=community_server_id,
        )

        assert is_created is False
        assert chunk == winner_chunk
        assert chunk.embedding_provider == "other-provider"
        mock_llm_service.generate_embedding.assert_called_once()


class TestUpdateIsCommonFlag:
    """Tests for ChunkEmbeddingService.update_is_common_flag() method."""

    @pytest.mark.asyncio
    async def test_sets_is_common_true_when_multiple_references(self):
        """Test is_common is True when chunk appears in multiple documents."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        chunk_id = uuid4()

        fact_check_count_result = MagicMock()
        fact_check_count_result.scalar_one.return_value = 2

        previously_seen_count_result = MagicMock()
        previously_seen_count_result.scalar_one.return_value = 1

        mock_db.execute.side_effect = [
            fact_check_count_result,
            previously_seen_count_result,
            MagicMock(),
        ]

        is_common = await service.update_is_common_flag(db=mock_db, chunk_id=chunk_id)

        assert is_common is True
        assert mock_db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_sets_is_common_false_when_single_reference(self):
        """Test is_common is False when chunk appears only once."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        chunk_id = uuid4()

        fact_check_count_result = MagicMock()
        fact_check_count_result.scalar_one.return_value = 1

        previously_seen_count_result = MagicMock()
        previously_seen_count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [
            fact_check_count_result,
            previously_seen_count_result,
            MagicMock(),
        ]

        is_common = await service.update_is_common_flag(db=mock_db, chunk_id=chunk_id)

        assert is_common is False

    @pytest.mark.asyncio
    async def test_counts_both_join_tables(self):
        """Test that update_is_common_flag counts both FactCheckChunk and PreviouslySeenChunk.

        With IS_COMMON_THRESHOLD=2, a chunk needs total_count > 2 to be common.
        """
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        chunk_id = uuid4()

        fact_check_count_result = MagicMock()
        fact_check_count_result.scalar_one.return_value = 2

        previously_seen_count_result = MagicMock()
        previously_seen_count_result.scalar_one.return_value = 1

        mock_db.execute.side_effect = [
            fact_check_count_result,
            previously_seen_count_result,
            MagicMock(),
        ]

        is_common = await service.update_is_common_flag(db=mock_db, chunk_id=chunk_id)

        assert is_common is True

    @pytest.mark.asyncio
    async def test_zero_references_sets_is_common_false(self):
        """Test is_common is False when chunk has no references."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        chunk_id = uuid4()

        fact_check_count_result = MagicMock()
        fact_check_count_result.scalar_one.return_value = 0

        previously_seen_count_result = MagicMock()
        previously_seen_count_result.scalar_one.return_value = 0

        mock_db.execute.side_effect = [
            fact_check_count_result,
            previously_seen_count_result,
            MagicMock(),
        ]

        is_common = await service.update_is_common_flag(db=mock_db, chunk_id=chunk_id)

        assert is_common is False


def _build_chunk_embed_mock_sequence(
    chunk_texts: list[str],
    *,
    chunks_exist: list[bool] | None = None,
) -> tuple[list[MagicMock], list[ChunkEmbedding]]:
    """
    Build mock execute side effects for chunk_and_embed tests.

    For each chunk, we need get_or_create_chunk:
    - SELECT (lookup) -> returns chunk if exists, None otherwise
    - If not exists: INSERT (with rowcount=1), then SELECT (final lookup)

    Note: batch_update_is_common_flags is called once at the end (not per-chunk)
    and should be mocked separately via service method patching.

    Returns:
        Tuple of (execute side effects list, created chunks list)
    """
    if chunks_exist is None:
        chunks_exist = [False] * len(chunk_texts)

    side_effects = []
    created_chunks = []

    for i, chunk_text in enumerate(chunk_texts):
        chunk = ChunkEmbedding(
            chunk_text=chunk_text,
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        chunk.id = uuid4()
        created_chunks.append(chunk)

        if chunks_exist[i]:
            mock_lookup_result = MagicMock()
            mock_lookup_result.scalar_one_or_none.return_value = chunk
            side_effects.append(mock_lookup_result)
        else:
            mock_lookup_result = MagicMock()
            mock_lookup_result.scalar_one_or_none.return_value = None
            side_effects.append(mock_lookup_result)

            mock_insert_result = MagicMock()
            mock_insert_result.rowcount = 1
            side_effects.append(mock_insert_result)

            mock_final_lookup = MagicMock()
            mock_final_lookup.scalar_one.return_value = chunk
            side_effects.append(mock_final_lookup)

    return side_effects, created_chunks


def _create_batch_mock_result(
    chunk_texts: list[str],
    *,
    chunks_exist: list[bool] | None = None,
) -> tuple[list[tuple[ChunkEmbedding, bool]], list[ChunkEmbedding]]:
    """
    Create mock return value for get_or_create_chunks_batch.

    Args:
        chunk_texts: List of chunk text contents
        chunks_exist: Which chunks already existed (default: all new)

    Returns:
        Tuple of (batch result list, created chunks list)
    """
    if chunks_exist is None:
        chunks_exist = [False] * len(chunk_texts)

    created_chunks = []
    batch_result = []

    for i, chunk_text in enumerate(chunk_texts):
        chunk = ChunkEmbedding(
            chunk_text=chunk_text,
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        chunk.id = uuid4()
        created_chunks.append(chunk)
        batch_result.append((chunk, not chunks_exist[i]))

    return batch_result, created_chunks


class TestChunkAndEmbedFactCheck:
    """Tests for ChunkEmbeddingService.chunk_and_embed_fact_check() method."""

    @pytest.mark.asyncio
    async def test_chunks_text_and_creates_embeddings(self):
        """Test that text is chunked and embeddings are created for each chunk."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Chunk one.", "Chunk two."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, _ = _create_batch_mock_result(chunk_texts)
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        added_objects: list[object] = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        fact_check_id = uuid4()
        community_server_id = uuid4()

        chunks = await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=fact_check_id,
            text="Chunk one. Chunk two.",
            community_server_id=community_server_id,
        )

        mock_chunking_service.chunk_text.assert_called_once_with("Chunk one. Chunk two.")
        service.get_or_create_chunks_batch.assert_called_once_with(
            db=mock_db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )
        assert len(chunks) == 2
        assert all(isinstance(c, ChunkEmbedding) for c in chunks)

        join_entries = [o for o in added_objects if isinstance(o, FactCheckChunk)]
        assert len(join_entries) == 2
        for entry in join_entries:
            assert entry.fact_check_id == fact_check_id

        service.batch_update_is_common_flags.assert_called_once()
        call_args = service.batch_update_is_common_flags.call_args
        assert len(call_args[0][1]) == 2

    @pytest.mark.asyncio
    async def test_creates_join_entries_for_fact_check(self):
        """Test that FactCheckChunk join entries are created with correct IDs."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Single chunk."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, _ = _create_batch_mock_result(chunk_texts)
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        added_objects: list[object] = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        fact_check_id = uuid4()
        community_server_id = uuid4()

        chunks = await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=fact_check_id,
            text="Single chunk.",
            community_server_id=community_server_id,
        )

        join_entries = [o for o in added_objects if isinstance(o, FactCheckChunk)]
        assert len(join_entries) == 1
        assert join_entries[0].chunk_id == chunks[0].id
        assert join_entries[0].fact_check_id == fact_check_id

    @pytest.mark.asyncio
    async def test_reuses_existing_chunks(self):
        """Test that existing chunks are reused without generating new embeddings."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Existing chunk."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embeddings_batch = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, expected_chunks = _create_batch_mock_result(chunk_texts, chunks_exist=[True])
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        added_objects: list[object] = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        chunks = await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=uuid4(),
            text="Existing chunk.",
            community_server_id=uuid4(),
        )

        assert len(chunks) == 1
        assert chunks[0] == expected_chunks[0]

        chunk_embeddings_added = [o for o in added_objects if isinstance(o, ChunkEmbedding)]
        assert len(chunk_embeddings_added) == 0


class TestChunkAndEmbedPreviouslySeen:
    """Tests for ChunkEmbeddingService.chunk_and_embed_previously_seen() method."""

    @pytest.mark.asyncio
    async def test_chunks_text_and_creates_embeddings(self):
        """Test that text is chunked and embeddings are created."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Chunk A.", "Chunk B."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, _ = _create_batch_mock_result(chunk_texts)
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        added_objects: list[object] = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        previously_seen_id = uuid4()
        community_server_id = uuid4()

        chunks = await service.chunk_and_embed_previously_seen(
            db=mock_db,
            previously_seen_id=previously_seen_id,
            text="Chunk A. Chunk B.",
            community_server_id=community_server_id,
        )

        mock_chunking_service.chunk_text.assert_called_once()
        service.get_or_create_chunks_batch.assert_called_once_with(
            db=mock_db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )
        assert len(chunks) == 2
        assert all(isinstance(c, ChunkEmbedding) for c in chunks)

        service.batch_update_is_common_flags.assert_called_once()
        call_args = service.batch_update_is_common_flags.call_args
        assert len(call_args[0][1]) == 2

    @pytest.mark.asyncio
    async def test_creates_join_entries_for_previously_seen(self):
        """Test that PreviouslySeenChunk join entries are created."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Single chunk."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, _ = _create_batch_mock_result(chunk_texts)
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        added_objects: list[object] = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        previously_seen_id = uuid4()
        community_server_id = uuid4()

        chunks = await service.chunk_and_embed_previously_seen(
            db=mock_db,
            previously_seen_id=previously_seen_id,
            text="Single chunk.",
            community_server_id=community_server_id,
        )

        join_entries = [o for o in added_objects if isinstance(o, PreviouslySeenChunk)]
        assert len(join_entries) == 1
        assert join_entries[0].chunk_id == chunks[0].id
        assert join_entries[0].previously_seen_id == previously_seen_id

    @pytest.mark.asyncio
    async def test_reuses_existing_chunks(self):
        """Test that existing chunks are reused."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Shared chunk."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embeddings_batch = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, expected_chunks = _create_batch_mock_result(chunk_texts, chunks_exist=[True])
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        added_objects: list[object] = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        chunks = await service.chunk_and_embed_previously_seen(
            db=mock_db,
            previously_seen_id=uuid4(),
            text="Shared chunk.",
            community_server_id=uuid4(),
        )

        assert len(chunks) == 1
        assert chunks[0] == expected_chunks[0]


class TestChunkEmbeddingServiceInit:
    """Tests for ChunkEmbeddingService initialization."""

    def test_init_with_dependencies(self):
        """Test that service initializes with required dependencies."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        assert service.chunking_service == mock_chunking_service
        assert service.llm_service == mock_llm_service


class TestOptionalCommunityServerId:
    """Tests for optional community_server_id (global fallback) behavior."""

    @pytest.mark.asyncio
    async def test_get_or_create_chunk_with_none_community_server_id(self):
        """Test that get_or_create_chunk works with None community_server_id (global fallback)."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_text = "Test chunk with global fallback."
        expected_chunk = ChunkEmbedding(
            chunk_text=chunk_text,
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        expected_chunk.id = uuid4()

        mock_db = _create_mock_db_for_insert(
            chunk_exists_initially=False,
            inserted=True,
            returned_chunk=expected_chunk,
        )

        chunk, is_created = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text=chunk_text,
            community_server_id=None,
        )

        assert is_created is True
        assert chunk.chunk_text == chunk_text
        mock_llm_service.generate_embedding.assert_called_once_with(mock_db, chunk_text, None)

    @pytest.mark.asyncio
    async def test_chunk_and_embed_fact_check_with_none_community_server_id(self):
        """Test that chunk_and_embed_fact_check works with None community_server_id."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Chunk one."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, _ = _create_batch_mock_result(chunk_texts)
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        fact_check_id = uuid4()

        chunks = await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=fact_check_id,
            text="Chunk one.",
            community_server_id=None,
        )

        service.get_or_create_chunks_batch.assert_called_once_with(
            db=mock_db,
            chunk_texts=chunk_texts,
            community_server_id=None,
        )
        assert len(chunks) == 1


class TestEmptyTextHandling:
    """Tests for edge cases with empty or minimal text."""

    @pytest.mark.asyncio
    async def test_empty_chunk_list_returns_empty(self):
        """Test that an empty chunk list returns empty results."""
        mock_chunking_service = MagicMock()
        mock_chunking_service.chunk_text.return_value = []

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )
        service.get_or_create_chunks_batch = AsyncMock(return_value=[])
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        chunks = await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=uuid4(),
            text="",
            community_server_id=uuid4(),
        )

        assert len(chunks) == 0
        mock_db.add.assert_not_called()
        service.batch_update_is_common_flags.assert_called_once_with(mock_db, [])


class TestBatchUpdateIsCommonFlags:
    """Tests for ChunkEmbeddingService.batch_update_is_common_flags() method."""

    @pytest.mark.asyncio
    async def test_empty_chunk_ids_returns_empty_dict(self):
        """Test that empty chunk_ids list returns empty dict without queries."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()

        result = await service.batch_update_is_common_flags(db=mock_db, chunk_ids=[])

        assert result == {}
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_marks_common_when_multiple_references(self):
        """Test chunks with count > 1 are marked as common."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_id = uuid4()
        mock_db = AsyncMock()

        mock_row = MagicMock()
        mock_row.chunk_id = chunk_id
        mock_row.total = 3

        mock_count_result = MagicMock()
        mock_count_result.all.return_value = [mock_row]

        mock_db.execute.side_effect = [
            mock_count_result,
            MagicMock(),
        ]

        result = await service.batch_update_is_common_flags(db=mock_db, chunk_ids=[chunk_id])

        assert result == {chunk_id: True}
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_marks_not_common_when_single_reference(self):
        """Test chunks with count <= 1 are marked as not common."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_id = uuid4()
        mock_db = AsyncMock()

        mock_row = MagicMock()
        mock_row.chunk_id = chunk_id
        mock_row.total = 1

        mock_count_result = MagicMock()
        mock_count_result.all.return_value = [mock_row]

        mock_db.execute.side_effect = [
            mock_count_result,
            MagicMock(),
        ]

        result = await service.batch_update_is_common_flags(db=mock_db, chunk_ids=[chunk_id])

        assert result == {chunk_id: False}
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_mixed_common_and_not_common(self):
        """Test batch correctly separates common and not-common chunks."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        common_chunk_id = uuid4()
        not_common_chunk_id = uuid4()

        mock_db = AsyncMock()

        mock_common_row = MagicMock()
        mock_common_row.chunk_id = common_chunk_id
        mock_common_row.total = 5

        mock_not_common_row = MagicMock()
        mock_not_common_row.chunk_id = not_common_chunk_id
        mock_not_common_row.total = 1

        mock_count_result = MagicMock()
        mock_count_result.all.return_value = [mock_common_row, mock_not_common_row]

        mock_db.execute.side_effect = [
            mock_count_result,
            MagicMock(),
            MagicMock(),
        ]

        result = await service.batch_update_is_common_flags(
            db=mock_db, chunk_ids=[common_chunk_id, not_common_chunk_id]
        )

        assert result == {common_chunk_id: True, not_common_chunk_id: False}
        assert mock_db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_deduplicates_chunk_ids(self):
        """Test that duplicate chunk IDs are deduplicated.

        With IS_COMMON_THRESHOLD=2, a chunk needs total_count > 2 to be common.
        """
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_id = uuid4()
        mock_db = AsyncMock()

        mock_row = MagicMock()
        mock_row.chunk_id = chunk_id
        mock_row.total = 3

        mock_count_result = MagicMock()
        mock_count_result.all.return_value = [mock_row]

        mock_db.execute.side_effect = [
            mock_count_result,
            MagicMock(),
        ]

        result = await service.batch_update_is_common_flags(
            db=mock_db, chunk_ids=[chunk_id, chunk_id, chunk_id]
        )

        assert result == {chunk_id: True}

    @pytest.mark.asyncio
    async def test_handles_chunk_with_zero_references(self):
        """Test chunks with no references in join tables are marked not common."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_id = uuid4()
        mock_db = AsyncMock()

        mock_count_result = MagicMock()
        mock_count_result.all.return_value = []

        mock_db.execute.side_effect = [
            mock_count_result,
            MagicMock(),
        ]

        result = await service.batch_update_is_common_flags(db=mock_db, chunk_ids=[chunk_id])

        assert result == {chunk_id: False}
        assert mock_db.execute.call_count == 2


class TestRechunkingIdempotency:
    """Tests for re-chunking the same entity multiple times."""

    @pytest.mark.asyncio
    async def test_rechunk_fact_check_deletes_existing_entries(self):
        """Test that re-chunking a fact check deletes existing join entries first."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Chunk one."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, _ = _create_batch_mock_result(chunk_texts)
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        added_objects: list[object] = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        fact_check_id = uuid4()
        community_server_id = uuid4()

        await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=fact_check_id,
            text="Chunk one.",
            community_server_id=community_server_id,
        )

        assert mock_db.execute.call_count >= 1
        first_call = mock_db.execute.call_args_list[0]
        assert "DELETE" in str(first_call).upper() or "delete" in str(first_call)

    @pytest.mark.asyncio
    async def test_rechunk_previously_seen_deletes_existing_entries(self):
        """Test that re-chunking a previously seen message deletes existing join entries first."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Chunk one."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        batch_result, _ = _create_batch_mock_result(chunk_texts)
        service.get_or_create_chunks_batch = AsyncMock(return_value=batch_result)
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        added_objects: list[object] = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        previously_seen_id = uuid4()
        community_server_id = uuid4()

        await service.chunk_and_embed_previously_seen(
            db=mock_db,
            previously_seen_id=previously_seen_id,
            text="Chunk one.",
            community_server_id=community_server_id,
        )

        assert mock_db.execute.call_count >= 1
        first_call = mock_db.execute.call_args_list[0]
        assert "DELETE" in str(first_call).upper() or "delete" in str(first_call)

    @pytest.mark.asyncio
    async def test_rechunk_fact_check_twice_succeeds(self):
        """Test that calling chunk_and_embed_fact_check twice doesn't raise errors."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Same chunk."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk = ChunkEmbedding(
            chunk_text="Same chunk.",
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        chunk.id = uuid4()

        service.get_or_create_chunks_batch = AsyncMock(return_value=[(chunk, False)])
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        fact_check_id = uuid4()
        community_server_id = uuid4()

        chunks1 = await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=fact_check_id,
            text="Same chunk.",
            community_server_id=community_server_id,
        )

        mock_db.add.reset_mock()

        chunks2 = await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=fact_check_id,
            text="Same chunk.",
            community_server_id=community_server_id,
        )

        assert len(chunks1) == 1
        assert len(chunks2) == 1
        assert chunks1[0] is chunk
        assert chunks2[0] is chunk

    @pytest.mark.asyncio
    async def test_rechunk_previously_seen_twice_succeeds(self):
        """Test that calling chunk_and_embed_previously_seen twice doesn't raise errors."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Same chunk."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk = ChunkEmbedding(
            chunk_text="Same chunk.",
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        chunk.id = uuid4()

        service.get_or_create_chunks_batch = AsyncMock(return_value=[(chunk, False)])
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        previously_seen_id = uuid4()
        community_server_id = uuid4()

        chunks1 = await service.chunk_and_embed_previously_seen(
            db=mock_db,
            previously_seen_id=previously_seen_id,
            text="Same chunk.",
            community_server_id=community_server_id,
        )

        mock_db.add.reset_mock()

        chunks2 = await service.chunk_and_embed_previously_seen(
            db=mock_db,
            previously_seen_id=previously_seen_id,
            text="Same chunk.",
            community_server_id=community_server_id,
        )

        assert len(chunks1) == 1
        assert len(chunks2) == 1
        assert chunks1[0] is chunk
        assert chunks2[0] is chunk


class TestGetOrCreateChunksBatch:
    """Tests for ChunkEmbeddingService.get_or_create_chunks_batch() method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_input(self):
        """Test that empty input returns empty list without any DB/API calls."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embeddings_batch = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()

        result = await service.get_or_create_chunks_batch(
            db=mock_db,
            chunk_texts=[],
            community_server_id=uuid4(),
        )

        assert result == []
        mock_db.execute.assert_not_called()
        mock_llm_service.generate_embeddings_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_new_chunks_when_none_exist(self):
        """Test batch creation of new chunks when none exist in database."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embeddings_batch = AsyncMock(
            return_value=[
                ([0.1] * 1536, "litellm", "text-embedding-3-small"),
                ([0.2] * 1536, "litellm", "text-embedding-3-small"),
            ]
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_texts = ["Chunk one.", "Chunk two."]
        community_server_id = uuid4()

        from src.fact_checking.chunk_models import compute_chunk_text_hash

        created_chunks = []
        for text in chunk_texts:
            chunk = ChunkEmbedding(
                chunk_text=text,
                chunk_text_hash=compute_chunk_text_hash(text),
                embedding=[0.1] * 1536,
                embedding_provider="litellm",
                embedding_model="text-embedding-3-small",
            )
            chunk.id = uuid4()
            created_chunks.append(chunk)

        mock_db = AsyncMock()

        mock_lookup_result = MagicMock()
        mock_lookup_result.scalars.return_value.all.return_value = []

        mock_fetch_result = MagicMock()
        mock_fetch_result.scalars.return_value.all.return_value = created_chunks

        mock_db.execute.side_effect = [
            mock_lookup_result,
            MagicMock(),
            MagicMock(),
            mock_fetch_result,
        ]

        result = await service.get_or_create_chunks_batch(
            db=mock_db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )

        mock_llm_service.generate_embeddings_batch.assert_called_once_with(
            mock_db, chunk_texts, community_server_id
        )
        assert len(result) == 2
        assert all(is_created for _, is_created in result)

    @pytest.mark.asyncio
    async def test_returns_existing_chunks_without_api_call(self):
        """Test that existing chunks are returned without making embedding API calls."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embeddings_batch = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_texts = ["Existing chunk."]
        community_server_id = uuid4()

        from src.fact_checking.chunk_models import compute_chunk_text_hash

        existing_chunk = ChunkEmbedding(
            chunk_text="Existing chunk.",
            chunk_text_hash=compute_chunk_text_hash("Existing chunk."),
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        existing_chunk.id = uuid4()

        mock_db = AsyncMock()

        mock_lookup_result = MagicMock()
        mock_lookup_result.scalars.return_value.all.return_value = [existing_chunk]

        mock_db.execute.return_value = mock_lookup_result

        result = await service.get_or_create_chunks_batch(
            db=mock_db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )

        mock_llm_service.generate_embeddings_batch.assert_not_called()
        assert len(result) == 1
        chunk, is_created = result[0]
        assert chunk == existing_chunk
        assert is_created is False

    @pytest.mark.asyncio
    async def test_handles_mixed_existing_and_new_chunks(self):
        """Test batch with some existing and some new chunks."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embeddings_batch = AsyncMock(
            return_value=[
                ([0.2] * 1536, "litellm", "text-embedding-3-small"),
            ]
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_texts = ["Existing chunk.", "New chunk."]
        community_server_id = uuid4()

        from src.fact_checking.chunk_models import compute_chunk_text_hash

        existing_chunk = ChunkEmbedding(
            chunk_text="Existing chunk.",
            chunk_text_hash=compute_chunk_text_hash("Existing chunk."),
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        existing_chunk.id = uuid4()

        new_chunk = ChunkEmbedding(
            chunk_text="New chunk.",
            chunk_text_hash=compute_chunk_text_hash("New chunk."),
            embedding=[0.2] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        new_chunk.id = uuid4()

        mock_db = AsyncMock()

        mock_lookup_result = MagicMock()
        mock_lookup_result.scalars.return_value.all.return_value = [existing_chunk]

        mock_fetch_result = MagicMock()
        mock_fetch_result.scalars.return_value.all.return_value = [new_chunk]

        mock_db.execute.side_effect = [
            mock_lookup_result,
            MagicMock(),
            mock_fetch_result,
        ]

        result = await service.get_or_create_chunks_batch(
            db=mock_db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )

        mock_llm_service.generate_embeddings_batch.assert_called_once_with(
            mock_db, ["New chunk."], community_server_id
        )
        assert len(result) == 2

        chunk1, is_created1 = result[0]
        assert chunk1 == existing_chunk
        assert is_created1 is False

        chunk2, is_created2 = result[1]
        assert chunk2 == new_chunk
        assert is_created2 is True

    @pytest.mark.asyncio
    async def test_deduplicates_input_texts(self):
        """Test that duplicate texts in input are deduplicated before processing."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embeddings_batch = AsyncMock(
            return_value=[
                ([0.1] * 1536, "litellm", "text-embedding-3-small"),
            ]
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_texts = ["Same chunk.", "Same chunk.", "Same chunk."]
        community_server_id = uuid4()

        from src.fact_checking.chunk_models import compute_chunk_text_hash

        created_chunk = ChunkEmbedding(
            chunk_text="Same chunk.",
            chunk_text_hash=compute_chunk_text_hash("Same chunk."),
            embedding=[0.1] * 1536,
            embedding_provider="litellm",
            embedding_model="text-embedding-3-small",
        )
        created_chunk.id = uuid4()

        mock_db = AsyncMock()

        mock_lookup_result = MagicMock()
        mock_lookup_result.scalars.return_value.all.return_value = []

        mock_fetch_result = MagicMock()
        mock_fetch_result.scalars.return_value.all.return_value = [created_chunk]

        mock_db.execute.side_effect = [
            mock_lookup_result,
            MagicMock(),
            mock_fetch_result,
        ]

        result = await service.get_or_create_chunks_batch(
            db=mock_db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )

        mock_llm_service.generate_embeddings_batch.assert_called_once_with(
            mock_db, ["Same chunk."], community_server_id
        )
        assert len(result) == 3
        for chunk, is_created in result:
            assert chunk == created_chunk
            assert is_created is True

    @pytest.mark.asyncio
    async def test_preserves_input_order(self):
        """Test that results are returned in the same order as input texts."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embeddings_batch = AsyncMock(
            return_value=[
                ([0.1] * 1536, "litellm", "text-embedding-3-small"),
                ([0.2] * 1536, "litellm", "text-embedding-3-small"),
                ([0.3] * 1536, "litellm", "text-embedding-3-small"),
            ]
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        chunk_texts = ["First.", "Second.", "Third."]
        community_server_id = uuid4()

        from src.fact_checking.chunk_models import compute_chunk_text_hash

        created_chunks = []
        for text in chunk_texts:
            chunk = ChunkEmbedding(
                chunk_text=text,
                chunk_text_hash=compute_chunk_text_hash(text),
                embedding=[0.1] * 1536,
                embedding_provider="litellm",
                embedding_model="text-embedding-3-small",
            )
            chunk.id = uuid4()
            created_chunks.append(chunk)

        mock_db = AsyncMock()

        mock_lookup_result = MagicMock()
        mock_lookup_result.scalars.return_value.all.return_value = []

        mock_fetch_result = MagicMock()
        mock_fetch_result.scalars.return_value.all.return_value = created_chunks

        mock_db.execute.side_effect = [
            mock_lookup_result,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            mock_fetch_result,
        ]

        result = await service.get_or_create_chunks_batch(
            db=mock_db,
            chunk_texts=chunk_texts,
            community_server_id=community_server_id,
        )

        assert len(result) == 3
        for i, (chunk, _) in enumerate(result):
            assert chunk.chunk_text == chunk_texts[i]
