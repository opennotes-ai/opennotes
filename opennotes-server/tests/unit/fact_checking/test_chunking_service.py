"""Unit tests for ChunkingService with NeuralChunker integration."""

from unittest.mock import MagicMock, patch


class TestChunkingServiceInitialization:
    """Test ChunkingService initialization."""

    def test_default_model_constant(self):
        """Test ChunkingService has correct default model."""
        from src.fact_checking.chunking_service import ChunkingService

        assert ChunkingService.DEFAULT_MODEL == "mirth/chonky_modernbert_base_1"

    def test_initialization_with_defaults(self):
        """Test ChunkingService can be initialized with default parameters."""
        from src.fact_checking.chunking_service import ChunkingService

        service = ChunkingService()

        assert service._model == ChunkingService.DEFAULT_MODEL
        assert service._device_map == "cpu"
        assert service._min_characters_per_chunk == 50
        assert service._chunker is None

    def test_initialization_with_custom_parameters(self):
        """Test ChunkingService can be initialized with custom parameters."""
        from src.fact_checking.chunking_service import ChunkingService

        service = ChunkingService(
            model="custom/model",
            device_map="cuda:0",
            min_characters_per_chunk=100,
        )

        assert service._model == "custom/model"
        assert service._device_map == "cuda:0"
        assert service._min_characters_per_chunk == 100

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunker_property_lazy_initialization(self, mock_neural_chunker):
        """Test chunker property initializes NeuralChunker lazily."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()

        assert service._chunker is None

        chunker = service.chunker

        mock_neural_chunker.assert_called_once_with(
            model="mirth/chonky_modernbert_base_1",
            device_map="cpu",
            min_characters_per_chunk=50,
        )
        assert chunker is mock_instance

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunker_property_returns_same_instance(self, mock_neural_chunker):
        """Test chunker property returns same instance on subsequent calls."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_instance = MagicMock()
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()

        chunker1 = service.chunker
        chunker2 = service.chunker

        mock_neural_chunker.assert_called_once()
        assert chunker1 is chunker2


class TestChunkResult:
    """Test ChunkResult dataclass."""

    def test_chunk_result_creation(self):
        """Test ChunkResult can be created with required fields."""
        from src.fact_checking.chunking_service import ChunkResult

        result = ChunkResult(
            text="This is a chunk of text.",
            start_index=0,
            end_index=24,
            chunk_index=0,
        )

        assert result.text == "This is a chunk of text."
        assert result.start_index == 0
        assert result.end_index == 24
        assert result.chunk_index == 0

    def test_chunk_result_with_token_count(self):
        """Test ChunkResult can include optional token_count."""
        from src.fact_checking.chunking_service import ChunkResult

        result = ChunkResult(
            text="This is a chunk.",
            start_index=0,
            end_index=16,
            chunk_index=0,
            token_count=5,
        )

        assert result.token_count == 5

    def test_chunk_result_token_count_defaults_none(self):
        """Test ChunkResult token_count defaults to None."""
        from src.fact_checking.chunking_service import ChunkResult

        result = ChunkResult(
            text="Chunk text",
            start_index=0,
            end_index=10,
            chunk_index=0,
        )

        assert result.token_count is None


class TestChunkText:
    """Test chunk_text() method."""

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_text_returns_list_of_strings(self, mock_neural_chunker):
        """Test chunk_text() returns list of chunk strings."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_chunk1 = MagicMock()
        mock_chunk1.text = "First chunk."
        mock_chunk2 = MagicMock()
        mock_chunk2.text = "Second chunk."

        mock_instance = MagicMock()
        mock_instance.chunk.return_value = [mock_chunk1, mock_chunk2]
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_text("First chunk. Second chunk.")

        assert result == ["First chunk.", "Second chunk."]
        mock_instance.chunk.assert_called_once_with("First chunk. Second chunk.")

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_text_empty_string_returns_empty_list(self, mock_neural_chunker):
        """Test chunk_text() with empty string returns empty list."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_instance = MagicMock()
        mock_instance.chunk.return_value = []
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_text("")

        assert result == []

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_text_single_chunk(self, mock_neural_chunker):
        """Test chunk_text() with text that results in single chunk."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_chunk = MagicMock()
        mock_chunk.text = "Short text."

        mock_instance = MagicMock()
        mock_instance.chunk.return_value = [mock_chunk]
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_text("Short text.")

        assert result == ["Short text."]


class TestChunkTextWithPositions:
    """Test chunk_text_with_positions() method."""

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_text_with_positions_returns_chunk_results(self, mock_neural_chunker):
        """Test chunk_text_with_positions() returns list of ChunkResult."""
        from src.fact_checking.chunking_service import ChunkingService, ChunkResult

        mock_chunk1 = MagicMock()
        mock_chunk1.text = "First chunk."
        mock_chunk1.start_index = 0
        mock_chunk1.end_index = 12
        mock_chunk1.token_count = 3

        mock_chunk2 = MagicMock()
        mock_chunk2.text = "Second chunk."
        mock_chunk2.start_index = 13
        mock_chunk2.end_index = 26
        mock_chunk2.token_count = 3

        mock_instance = MagicMock()
        mock_instance.chunk.return_value = [mock_chunk1, mock_chunk2]
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_text_with_positions("First chunk. Second chunk.")

        assert len(result) == 2
        assert isinstance(result[0], ChunkResult)
        assert result[0].text == "First chunk."
        assert result[0].start_index == 0
        assert result[0].end_index == 12
        assert result[0].chunk_index == 0
        assert result[0].token_count == 3

        assert result[1].text == "Second chunk."
        assert result[1].start_index == 13
        assert result[1].end_index == 26
        assert result[1].chunk_index == 1
        assert result[1].token_count == 3

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_text_with_positions_empty_string(self, mock_neural_chunker):
        """Test chunk_text_with_positions() with empty string."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_instance = MagicMock()
        mock_instance.chunk.return_value = []
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_text_with_positions("")

        assert result == []

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_text_with_positions_assigns_sequential_indices(self, mock_neural_chunker):
        """Test chunk_text_with_positions() assigns sequential chunk indices."""
        from src.fact_checking.chunking_service import ChunkingService

        chunks = []
        for i in range(5):
            mock_chunk = MagicMock()
            mock_chunk.text = f"Chunk {i}."
            mock_chunk.start_index = i * 10
            mock_chunk.end_index = (i + 1) * 10
            mock_chunk.token_count = 2
            chunks.append(mock_chunk)

        mock_instance = MagicMock()
        mock_instance.chunk.return_value = chunks
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_text_with_positions("Long text with multiple chunks")

        for i, chunk_result in enumerate(result):
            assert chunk_result.chunk_index == i


class TestChunkBatch:
    """Test chunk_batch() method."""

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_batch_returns_list_of_string_lists(self, mock_neural_chunker):
        """Test chunk_batch() returns list of chunk string lists."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_chunk1 = MagicMock()
        mock_chunk1.text = "Doc1 chunk1."
        mock_chunk2 = MagicMock()
        mock_chunk2.text = "Doc1 chunk2."
        mock_chunk3 = MagicMock()
        mock_chunk3.text = "Doc2 chunk1."

        mock_instance = MagicMock()
        mock_instance.chunk_batch.return_value = [
            [mock_chunk1, mock_chunk2],
            [mock_chunk3],
        ]
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        texts = ["Doc1 content.", "Doc2 content."]
        result = service.chunk_batch(texts)

        assert result == [
            ["Doc1 chunk1.", "Doc1 chunk2."],
            ["Doc2 chunk1."],
        ]
        mock_instance.chunk_batch.assert_called_once_with(texts)

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_batch_empty_list(self, mock_neural_chunker):
        """Test chunk_batch() with empty list."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_instance = MagicMock()
        mock_instance.chunk_batch.return_value = []
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_batch([])

        assert result == []

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_batch_single_document(self, mock_neural_chunker):
        """Test chunk_batch() with single document."""
        from src.fact_checking.chunking_service import ChunkingService

        mock_chunk = MagicMock()
        mock_chunk.text = "Single doc chunk."

        mock_instance = MagicMock()
        mock_instance.chunk_batch.return_value = [[mock_chunk]]
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_batch(["Single document."])

        assert result == [["Single doc chunk."]]


class TestChunkBatchWithPositions:
    """Test chunk_batch_with_positions() method."""

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_batch_with_positions_returns_nested_chunk_results(self, mock_neural_chunker):
        """Test chunk_batch_with_positions() returns list of ChunkResult lists."""
        from src.fact_checking.chunking_service import ChunkingService, ChunkResult

        mock_chunk1 = MagicMock()
        mock_chunk1.text = "Doc1 chunk."
        mock_chunk1.start_index = 0
        mock_chunk1.end_index = 11
        mock_chunk1.token_count = 3

        mock_chunk2 = MagicMock()
        mock_chunk2.text = "Doc2 chunk."
        mock_chunk2.start_index = 0
        mock_chunk2.end_index = 11
        mock_chunk2.token_count = 3

        mock_instance = MagicMock()
        mock_instance.chunk_batch.return_value = [[mock_chunk1], [mock_chunk2]]
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_batch_with_positions(["Doc1.", "Doc2."])

        assert len(result) == 2
        assert len(result[0]) == 1
        assert len(result[1]) == 1
        assert isinstance(result[0][0], ChunkResult)
        assert result[0][0].text == "Doc1 chunk."
        assert result[0][0].chunk_index == 0
        assert result[1][0].text == "Doc2 chunk."
        assert result[1][0].chunk_index == 0

    @patch("chonkie.chunker.neural.NeuralChunker")
    def test_chunk_batch_with_positions_maintains_per_doc_indices(self, mock_neural_chunker):
        """Test chunk indices reset per document in batch."""
        from src.fact_checking.chunking_service import ChunkingService

        doc1_chunks = []
        for i in range(3):
            c = MagicMock()
            c.text = f"Doc1 chunk {i}"
            c.start_index = i * 10
            c.end_index = (i + 1) * 10
            c.token_count = 2
            doc1_chunks.append(c)

        doc2_chunks = []
        for i in range(2):
            c = MagicMock()
            c.text = f"Doc2 chunk {i}"
            c.start_index = i * 10
            c.end_index = (i + 1) * 10
            c.token_count = 2
            doc2_chunks.append(c)

        mock_instance = MagicMock()
        mock_instance.chunk_batch.return_value = [doc1_chunks, doc2_chunks]
        mock_neural_chunker.return_value = mock_instance

        service = ChunkingService()
        result = service.chunk_batch_with_positions(["Doc1 text", "Doc2 text"])

        for i, chunk_result in enumerate(result[0]):
            assert chunk_result.chunk_index == i

        for i, chunk_result in enumerate(result[1]):
            assert chunk_result.chunk_index == i
