"""
Integration tests for ChunkingService with real NeuralChunker initialization.

These tests verify that the NeuralChunker can be initialized with the actual model
and tokenizer, catching configuration or version compatibility issues that mocked
unit tests would miss.

Task: task-888 - NeuralChunker tokenizer initialization error with mirth/chonky_modernbert_base_1
"""

import os

import pytest

from src.fact_checking.chunking_service import ChunkingService

# Skip all tests in this module when running in CI (HuggingFace model download times out)
pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true" or os.environ.get("SKIP_TESTCONTAINERS") == "1",
    reason="Skipped in CI: HuggingFace model download exceeds timeout",
)


class TestNeuralChunkerIntegration:
    """Integration tests that exercise real NeuralChunker initialization."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_chunking_service_initializes_with_default_model(self):
        """Test ChunkingService can initialize NeuralChunker with the default model.

        This test exercises the actual model and tokenizer loading to catch
        version compatibility issues between chonkie, transformers, and tokenizers.
        """
        service = ChunkingService()

        # Access the chunker property to trigger lazy initialization
        chunker = service.chunker

        assert chunker is not None

    @pytest.mark.integration
    @pytest.mark.slow
    def test_chunking_service_can_chunk_text(self):
        """Test ChunkingService can successfully chunk text with real model.

        This verifies the full pipeline: model load -> tokenization -> chunking.
        """
        service = ChunkingService()

        text = (
            "Machine learning is a subset of artificial intelligence. "
            "It enables computers to learn from data. "
            "Deep learning uses neural networks with many layers. "
            "Natural language processing helps computers understand text."
        )

        chunks = service.chunk_text(text)

        assert isinstance(chunks, list)
        assert len(chunks) > 0
        assert all(isinstance(chunk, str) for chunk in chunks)
        # Verify content is preserved - check key words appear in chunks
        assert any("Machine" in c for c in chunks)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_chunking_service_with_positions(self):
        """Test chunk_text_with_positions returns valid ChunkResult objects."""
        service = ChunkingService()

        text = "First topic here. Second topic is different. Third topic appears."

        results = service.chunk_text_with_positions(text)

        assert isinstance(results, list)
        assert len(results) > 0
        for result in results:
            assert hasattr(result, "text")
            assert hasattr(result, "start_index")
            assert hasattr(result, "end_index")
            assert hasattr(result, "chunk_index")
            assert result.start_index >= 0
            assert result.end_index <= len(text)
            assert result.start_index < result.end_index

    @pytest.mark.integration
    @pytest.mark.slow
    def test_neuralchunker_with_device_map_none(self):
        """Test that NeuralChunker with device_map=None works without accelerate.

        This is a regression test for task-888. The library's default device_map="auto"
        requires the accelerate library. Using device_map=None allows loading on CPU
        without that dependency.
        """
        from chonkie import NeuralChunker

        # device_map=None works without accelerate library
        chunker = NeuralChunker(device_map=None)

        text = "This is a test sentence. Another sentence here."
        chunks = chunker.chunk(text)

        assert len(chunks) > 0
