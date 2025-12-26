"""Unit tests for chunk embedding SQLAlchemy models."""

from uuid import UUID


class TestChunkEmbeddingModel:
    """Test ChunkEmbedding SQLAlchemy model."""

    def test_model_has_correct_tablename(self):
        """Test ChunkEmbedding uses correct table name."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        assert ChunkEmbedding.__tablename__ == "chunk_embeddings"

    def test_model_creates_with_required_fields(self):
        """Test ChunkEmbedding can be instantiated with required fields."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        chunk = ChunkEmbedding(
            chunk_text="This is a test chunk of text for embedding.",
        )

        assert chunk.chunk_text == "This is a test chunk of text for embedding."
        assert chunk.is_common is False  # Default value

    def test_model_accepts_embedding_vector(self):
        """Test ChunkEmbedding accepts embedding vector."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        embedding = [0.1] * 1536  # 1536 dimensions
        chunk = ChunkEmbedding(
            chunk_text="Test chunk text",
            embedding=embedding,
        )

        assert chunk.embedding is not None
        assert len(chunk.embedding) == 1536

    def test_model_accepts_embedding_provider_and_model(self):
        """Test ChunkEmbedding accepts embedding provider and model."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        chunk = ChunkEmbedding(
            chunk_text="Test chunk text",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
        )

        assert chunk.embedding_provider == "openai"
        assert chunk.embedding_model == "text-embedding-3-small"

    def test_model_is_common_defaults_to_false(self):
        """Test ChunkEmbedding is_common defaults to False."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        chunk = ChunkEmbedding(
            chunk_text="Test chunk text",
        )

        assert chunk.is_common is False

    def test_model_accepts_is_common_true(self):
        """Test ChunkEmbedding can set is_common to True."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        chunk = ChunkEmbedding(
            chunk_text="Common disclaimer text",
            is_common=True,
        )

        assert chunk.is_common is True

    def test_model_allows_null_embedding(self):
        """Test ChunkEmbedding allows NULL embedding field."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        chunk = ChunkEmbedding(
            chunk_text="Test chunk text",
            embedding=None,
        )

        assert chunk.embedding is None

    def test_model_repr_includes_key_fields(self):
        """Test ChunkEmbedding __repr__ includes key identifiers."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        chunk = ChunkEmbedding(
            chunk_text="This is a longer test chunk text for representation",
            is_common=True,
        )

        repr_str = repr(chunk)
        assert "ChunkEmbedding" in repr_str
        assert "This is a longer tes" in repr_str  # First 20 chars

    def test_model_has_hnsw_index_defined(self):
        """Test ChunkEmbedding has HNSW index configured in table args."""
        from src.fact_checking.chunk_models import ChunkEmbedding

        table_args = ChunkEmbedding.__table_args__
        assert table_args is not None

        # Find the HNSW index
        hnsw_index = None
        for arg in table_args:
            if hasattr(arg, "name") and "hnsw" in arg.name:
                hnsw_index = arg
                break

        assert hnsw_index is not None, "HNSW index not found in table args"


class TestFactCheckChunkModel:
    """Test FactCheckChunk join table model."""

    def test_model_has_correct_tablename(self):
        """Test FactCheckChunk uses correct table name."""
        from src.fact_checking.chunk_models import FactCheckChunk

        assert FactCheckChunk.__tablename__ == "fact_check_chunks"

    def test_model_creates_with_required_fields(self):
        """Test FactCheckChunk can be instantiated with FK fields."""
        from src.fact_checking.chunk_models import FactCheckChunk

        chunk_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        fact_check_id = UUID("018f5e6e-5678-7890-abcd-ef1234567890")

        join = FactCheckChunk(
            chunk_id=chunk_id,
            fact_check_id=fact_check_id,
        )

        assert join.chunk_id == chunk_id
        assert join.fact_check_id == fact_check_id
        assert join.chunk_index == 0  # Default value

    def test_model_stores_chunk_index(self):
        """Test FactCheckChunk stores chunk_index for document position."""
        from src.fact_checking.chunk_models import FactCheckChunk

        chunk_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        fact_check_id = UUID("018f5e6e-5678-7890-abcd-ef1234567890")

        join = FactCheckChunk(
            chunk_id=chunk_id,
            fact_check_id=fact_check_id,
            chunk_index=5,
        )

        assert join.chunk_index == 5

    def test_model_has_composite_unique_constraint(self):
        """Test FactCheckChunk has unique constraint on (chunk_id, fact_check_id)."""
        from src.fact_checking.chunk_models import FactCheckChunk

        table_args = FactCheckChunk.__table_args__

        # Find unique constraint
        unique_found = False
        for arg in table_args:
            if hasattr(arg, "name") and "unique" in arg.name.lower():
                unique_found = True
                break
            # Also check for UniqueConstraint type
            if hasattr(arg, "columns"):
                cols = [c.name for c in arg.columns]
                if "chunk_id" in cols and "fact_check_id" in cols:
                    unique_found = True
                    break

        assert unique_found, "Composite unique constraint not found"

    def test_model_repr_includes_key_fields(self):
        """Test FactCheckChunk __repr__ includes key identifiers."""
        from src.fact_checking.chunk_models import FactCheckChunk

        chunk_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        fact_check_id = UUID("018f5e6e-5678-7890-abcd-ef1234567890")

        join = FactCheckChunk(
            chunk_id=chunk_id,
            fact_check_id=fact_check_id,
        )

        repr_str = repr(join)
        assert "FactCheckChunk" in repr_str


class TestPreviouslySeenChunkModel:
    """Test PreviouslySeenChunk join table model."""

    def test_model_has_correct_tablename(self):
        """Test PreviouslySeenChunk uses correct table name."""
        from src.fact_checking.chunk_models import PreviouslySeenChunk

        assert PreviouslySeenChunk.__tablename__ == "previously_seen_chunks"

    def test_model_creates_with_required_fields(self):
        """Test PreviouslySeenChunk can be instantiated with FK fields."""
        from src.fact_checking.chunk_models import PreviouslySeenChunk

        chunk_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        previously_seen_id = UUID("018f5e6e-5678-7890-abcd-ef1234567890")

        join = PreviouslySeenChunk(
            chunk_id=chunk_id,
            previously_seen_id=previously_seen_id,
        )

        assert join.chunk_id == chunk_id
        assert join.previously_seen_id == previously_seen_id
        assert join.chunk_index == 0  # Default value

    def test_model_stores_chunk_index(self):
        """Test PreviouslySeenChunk stores chunk_index for message position."""
        from src.fact_checking.chunk_models import PreviouslySeenChunk

        chunk_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        previously_seen_id = UUID("018f5e6e-5678-7890-abcd-ef1234567890")

        join = PreviouslySeenChunk(
            chunk_id=chunk_id,
            previously_seen_id=previously_seen_id,
            chunk_index=3,
        )

        assert join.chunk_index == 3

    def test_model_has_composite_unique_constraint(self):
        """Test PreviouslySeenChunk has unique constraint on (chunk_id, previously_seen_id)."""
        from src.fact_checking.chunk_models import PreviouslySeenChunk

        table_args = PreviouslySeenChunk.__table_args__

        # Find unique constraint
        unique_found = False
        for arg in table_args:
            if hasattr(arg, "name") and "unique" in arg.name.lower():
                unique_found = True
                break
            # Also check for UniqueConstraint type
            if hasattr(arg, "columns"):
                cols = [c.name for c in arg.columns]
                if "chunk_id" in cols and "previously_seen_id" in cols:
                    unique_found = True
                    break

        assert unique_found, "Composite unique constraint not found"

    def test_model_repr_includes_key_fields(self):
        """Test PreviouslySeenChunk __repr__ includes key identifiers."""
        from src.fact_checking.chunk_models import PreviouslySeenChunk

        chunk_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        previously_seen_id = UUID("018f5e6e-5678-7890-abcd-ef1234567890")

        join = PreviouslySeenChunk(
            chunk_id=chunk_id,
            previously_seen_id=previously_seen_id,
        )

        repr_str = repr(join)
        assert "PreviouslySeenChunk" in repr_str
