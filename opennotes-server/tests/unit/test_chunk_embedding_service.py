"""Unit tests for ChunkEmbeddingService."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
from src.fact_checking.chunk_models import ChunkEmbedding, FactCheckChunk, PreviouslySeenChunk


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

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        added_objects = []
        mock_db.add = MagicMock(side_effect=lambda x: added_objects.append(x))

        community_server_id = uuid4()
        chunk_text = "This is a test chunk."

        chunk, is_created = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text=chunk_text,
            community_server_id=community_server_id,
        )

        assert is_created is True
        assert isinstance(chunk, ChunkEmbedding)
        assert chunk.chunk_text == chunk_text
        assert chunk.embedding == [0.1] * 1536
        assert chunk.embedding_provider == "litellm"
        assert chunk.embedding_model == "text-embedding-3-small"
        mock_llm_service.generate_embedding.assert_called_once_with(
            mock_db, chunk_text, community_server_id
        )
        assert len(added_objects) == 1
        assert added_objects[0] == chunk

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

        mock_db = AsyncMock()
        existing_chunk = MagicMock(spec=ChunkEmbedding)
        existing_chunk.id = uuid4()
        existing_chunk.chunk_text = "This is a test chunk."
        existing_chunk.embedding = [0.1] * 1536

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_chunk
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()

        community_server_id = uuid4()

        chunk, is_created = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text="This is a test chunk.",
            community_server_id=community_server_id,
        )

        assert is_created is False
        assert chunk == existing_chunk
        mock_llm_service.generate_embedding.assert_not_called()
        mock_db.add.assert_not_called()

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

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()

        community_server_id = uuid4()

        chunk, _ = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text="Test chunk",
            community_server_id=community_server_id,
        )

        assert chunk.embedding_provider == "anthropic"
        assert chunk.embedding_model == "voyage-2"

    @pytest.mark.asyncio
    async def test_stores_chunk_index(self):
        """Test that chunk_index is stored correctly."""
        mock_chunking_service = MagicMock()
        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()

        chunk, _ = await service.get_or_create_chunk(
            db=mock_db,
            chunk_text="Test chunk",
            community_server_id=uuid4(),
            chunk_index=5,
        )

        assert chunk.chunk_index == 5


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


class TestChunkAndEmbedFactCheck:
    """Tests for ChunkEmbeddingService.chunk_and_embed_fact_check() method."""

    @pytest.mark.asyncio
    async def test_chunks_text_and_creates_embeddings(self):
        """Test that text is chunked and embeddings are created for each chunk."""
        mock_chunking_service = MagicMock()
        mock_chunking_service.chunk_text.return_value = ["Chunk one.", "Chunk two."]

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        mock_lookup_result = MagicMock()
        mock_lookup_result.scalar_one_or_none.return_value = None

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        mock_db.execute.side_effect = [
            mock_lookup_result,
            mock_count_result,
            mock_count_result,
            MagicMock(),
            mock_lookup_result,
            mock_count_result,
            mock_count_result,
            MagicMock(),
        ]

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

    @pytest.mark.asyncio
    async def test_creates_join_entries_for_fact_check(self):
        """Test that FactCheckChunk join entries are created with correct IDs."""
        mock_chunking_service = MagicMock()
        mock_chunking_service.chunk_text.return_value = ["Single chunk."]

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        mock_lookup_result = MagicMock()
        mock_lookup_result.scalar_one_or_none.return_value = None

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        mock_db.execute.side_effect = [
            mock_lookup_result,
            mock_count_result,
            mock_count_result,
            MagicMock(),
        ]

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
        mock_chunking_service.chunk_text.return_value = ["Existing chunk."]

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        existing_chunk = MagicMock(spec=ChunkEmbedding)
        existing_chunk.id = uuid4()
        existing_chunk.chunk_text = "Existing chunk."

        mock_lookup_result = MagicMock()
        mock_lookup_result.scalar_one_or_none.return_value = existing_chunk

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 2

        mock_db.execute.side_effect = [
            mock_lookup_result,
            mock_count_result,
            mock_count_result,
            MagicMock(),
        ]

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
        assert chunks[0] == existing_chunk

        chunk_embeddings_added = [o for o in added_objects if isinstance(o, ChunkEmbedding)]
        assert len(chunk_embeddings_added) == 0


class TestChunkAndEmbedPreviouslySeen:
    """Tests for ChunkEmbeddingService.chunk_and_embed_previously_seen() method."""

    @pytest.mark.asyncio
    async def test_chunks_text_and_creates_embeddings(self):
        """Test that text is chunked and embeddings are created."""
        mock_chunking_service = MagicMock()
        mock_chunking_service.chunk_text.return_value = ["Chunk A.", "Chunk B."]

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        mock_lookup_result = MagicMock()
        mock_lookup_result.scalar_one_or_none.return_value = None

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        mock_db.execute.side_effect = [
            mock_lookup_result,
            mock_count_result,
            mock_count_result,
            MagicMock(),
            mock_lookup_result,
            mock_count_result,
            mock_count_result,
            MagicMock(),
        ]

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

    @pytest.mark.asyncio
    async def test_creates_join_entries_for_previously_seen(self):
        """Test that PreviouslySeenChunk join entries are created."""
        mock_chunking_service = MagicMock()
        mock_chunking_service.chunk_text.return_value = ["Single chunk."]

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock(
            return_value=([0.1] * 1536, "litellm", "text-embedding-3-small")
        )

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        mock_lookup_result = MagicMock()
        mock_lookup_result.scalar_one_or_none.return_value = None

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        mock_db.execute.side_effect = [
            mock_lookup_result,
            mock_count_result,
            mock_count_result,
            MagicMock(),
        ]

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
        mock_chunking_service.chunk_text.return_value = ["Shared chunk."]

        mock_llm_service = MagicMock()
        mock_llm_service.generate_embedding = AsyncMock()

        service = ChunkEmbeddingService(
            chunking_service=mock_chunking_service,
            llm_service=mock_llm_service,
        )

        mock_db = AsyncMock()
        existing_chunk = MagicMock(spec=ChunkEmbedding)
        existing_chunk.id = uuid4()

        mock_lookup_result = MagicMock()
        mock_lookup_result.scalar_one_or_none.return_value = existing_chunk

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 2

        mock_db.execute.side_effect = [
            mock_lookup_result,
            mock_count_result,
            mock_count_result,
            MagicMock(),
        ]

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
        assert chunks[0] == existing_chunk


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
