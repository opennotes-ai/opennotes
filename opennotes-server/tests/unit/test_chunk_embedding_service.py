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
        """Test that update_is_common_flag counts both FactCheckChunk and PreviouslySeenChunk."""
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


class TestChunkAndEmbedFactCheck:
    """Tests for ChunkEmbeddingService.chunk_and_embed_fact_check() method."""

    @pytest.mark.asyncio
    async def test_chunks_text_and_creates_embeddings(self):
        """Test that text is chunked and embeddings are created for each chunk."""
        mock_chunking_service = MagicMock()
        chunk_texts = ["Chunk one.", "Chunk two."]
        mock_chunking_service.chunk_text.return_value = chunk_texts

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        side_effects, _ = _build_chunk_embed_mock_sequence(chunk_texts)
        mock_db.execute.side_effect = side_effects

        added_objects = []
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
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        side_effects, _ = _build_chunk_embed_mock_sequence(chunk_texts)
        mock_db.execute.side_effect = side_effects

        added_objects = []
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
        mock_llm_service.generate_embedding = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        side_effects, expected_chunks = _build_chunk_embed_mock_sequence(
            chunk_texts, chunks_exist=[True]
        )
        mock_db.execute.side_effect = side_effects

        added_objects = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        chunks = await service.chunk_and_embed_fact_check(
            db=mock_db,
            fact_check_id=uuid4(),
            text="Existing chunk.",
            community_server_id=uuid4(),
        )

        mock_llm_service.generate_embedding.assert_not_called()
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
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        side_effects, _ = _build_chunk_embed_mock_sequence(chunk_texts)
        mock_db.execute.side_effect = side_effects

        added_objects = []
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
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        side_effects, _ = _build_chunk_embed_mock_sequence(chunk_texts)
        mock_db.execute.side_effect = side_effects

        added_objects = []
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
        mock_llm_service.generate_embedding = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )
        service.batch_update_is_common_flags = AsyncMock(return_value={})

        mock_db = AsyncMock()
        side_effects, expected_chunks = _build_chunk_embed_mock_sequence(
            chunk_texts, chunks_exist=[True]
        )
        mock_db.execute.side_effect = side_effects

        added_objects = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        chunks = await service.chunk_and_embed_previously_seen(
            db=mock_db,
            previously_seen_id=uuid4(),
            text="Shared chunk.",
            community_server_id=uuid4(),
        )

        mock_llm_service.generate_embedding.assert_not_called()
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
        """Test that duplicate chunk IDs are deduplicated."""
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
        mock_row.total = 2

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
