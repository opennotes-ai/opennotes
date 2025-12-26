"""
Chunking service for semantic text segmentation.

This module provides the ChunkingService class that uses NeuralChunker from the
chonkie library to split text into semantically coherent chunks. This is used
for creating more granular embeddings that improve semantic search accuracy.

The NeuralChunker uses a fine-tuned BERT model to detect topic shifts and
create chunks at natural semantic boundaries rather than arbitrary character
or token limits.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chonkie.chunker.neural import NeuralChunker


@dataclass
class ChunkResult:
    """
    Result of chunking a text segment with position information.

    Attributes:
        text: The text content of the chunk
        start_index: Starting character position in original text
        end_index: Ending character position in original text
        chunk_index: Sequential index of this chunk within the document (0-indexed)
        token_count: Optional number of tokens in the chunk
    """

    text: str
    start_index: int
    end_index: int
    chunk_index: int
    token_count: int | None = None


class ChunkingService:
    """
    Service for chunking text using neural-based semantic segmentation.

    Uses the chonkie library's NeuralChunker to split text at semantic
    boundaries detected by a fine-tuned BERT model. This produces higher
    quality chunks compared to simple character or token-based splitting.

    The chunker is lazily initialized on first use to avoid loading the
    model until it's actually needed.

    Attributes:
        DEFAULT_MODEL: The default model identifier for NeuralChunker

    Example:
        >>> service = ChunkingService()
        >>> chunks = service.chunk_text("First topic here. Second topic starts now.")
        >>> print(chunks)
        ['First topic here.', 'Second topic starts now.']
    """

    DEFAULT_MODEL = "mirth/chonky_modernbert_base_1"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        device_map: str = "cpu",
        min_characters_per_chunk: int = 50,
    ) -> None:
        """
        Initialize the ChunkingService.

        Args:
            model: The identifier or path to the fine-tuned BERT model
                   used for detecting semantic shifts
            device_map: Device to run inference on ('cpu', 'cuda', 'mps')
            min_characters_per_chunk: Minimum number of characters required
                                      for a text segment to be a valid chunk
        """
        self._model = model
        self._device_map = device_map
        self._min_characters_per_chunk = min_characters_per_chunk
        self._chunker: NeuralChunker | None = None

    @property
    def chunker(self) -> "NeuralChunker":
        """
        Get the NeuralChunker instance, initializing it if necessary.

        The chunker is lazily initialized on first access to defer model
        loading until actually needed.

        Returns:
            The initialized NeuralChunker instance
        """
        if self._chunker is None:
            from chonkie.chunker.neural import NeuralChunker

            self._chunker = NeuralChunker(
                model=self._model,
                device_map=self._device_map,
                min_characters_per_chunk=self._min_characters_per_chunk,
            )
        return self._chunker

    def chunk_text(self, text: str) -> list[str]:
        """
        Split text into semantic chunks and return the chunk texts.

        Args:
            text: The input text to be chunked

        Returns:
            List of chunk text strings
        """
        chunks = self.chunker.chunk(text)
        return [chunk.text for chunk in chunks]

    def chunk_text_with_positions(self, text: str) -> list[ChunkResult]:
        """
        Split text into semantic chunks with position information.

        Args:
            text: The input text to be chunked

        Returns:
            List of ChunkResult objects containing text and position data
        """
        chunks = self.chunker.chunk(text)
        return [
            ChunkResult(
                text=chunk.text,
                start_index=chunk.start_index,
                end_index=chunk.end_index,
                chunk_index=i,
                token_count=chunk.token_count,
            )
            for i, chunk in enumerate(chunks)
        ]

    def chunk_batch(self, texts: list[str]) -> list[list[str]]:
        """
        Chunk multiple texts efficiently in a batch.

        Args:
            texts: List of input texts to be chunked

        Returns:
            List of chunk text lists, one per input text
        """
        batch_results = self.chunker.chunk_batch(texts)
        return [[chunk.text for chunk in doc_chunks] for doc_chunks in batch_results]

    def chunk_batch_with_positions(self, texts: list[str]) -> list[list[ChunkResult]]:
        """
        Chunk multiple texts with position information.

        Args:
            texts: List of input texts to be chunked

        Returns:
            List of ChunkResult lists, one per input text.
            Chunk indices are per-document (reset to 0 for each text).
        """
        batch_results = self.chunker.chunk_batch(texts)
        return [
            [
                ChunkResult(
                    text=chunk.text,
                    start_index=chunk.start_index,
                    end_index=chunk.end_index,
                    chunk_index=i,
                    token_count=chunk.token_count,
                )
                for i, chunk in enumerate(doc_chunks)
            ]
            for doc_chunks in batch_results
        ]
