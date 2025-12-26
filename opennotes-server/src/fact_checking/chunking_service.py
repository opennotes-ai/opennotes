"""
Chunking service for semantic text segmentation.

This module provides the ChunkingService class that uses NeuralChunker from the
chonkie library to split text into semantically coherent chunks. This is used
for creating more granular embeddings that improve semantic search accuracy.

The NeuralChunker uses a fine-tuned BERT model to detect topic shifts and
create chunks at natural semantic boundaries rather than arbitrary character
or token limits.
"""

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.monitoring import get_logger

if TYPE_CHECKING:
    from chonkie.chunker.neural import NeuralChunker

logger = get_logger(__name__)

NETWORK_RETRY_EXCEPTIONS = (OSError, ConnectionError, TimeoutError)


def _log_retry_attempt(retry_state) -> None:
    """Log retry attempts for model loading."""
    attempt = retry_state.attempt_number
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "NeuralChunker model loading attempt %d failed: %s. Retrying...",
        attempt,
        exception,
    )


class ChunkingModelLoadError(Exception):
    """Raised when the chunking model fails to load.

    This typically occurs due to:
    - Network failures during model download
    - Invalid model identifier
    - Insufficient disk space or permissions
    - Corrupted model cache
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


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
    model until it's actually needed. Initialization is thread-safe.

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
        self._chunker_lock = threading.Lock()

    @property
    def chunker(self) -> "NeuralChunker":
        """
        Get the NeuralChunker instance, initializing it if necessary.

        The chunker is lazily initialized on first access to defer model
        loading until actually needed. Uses double-checked locking pattern
        for thread-safe initialization.

        Returns:
            The initialized NeuralChunker instance

        Raises:
            ChunkingModelLoadError: If the model fails to load
        """
        if self._chunker is None:
            with self._chunker_lock:
                if self._chunker is None:
                    self._chunker = self._initialize_chunker()
        return self._chunker

    def _initialize_chunker(self) -> "NeuralChunker":
        """
        Initialize the NeuralChunker with error handling and retry logic.

        Uses tenacity to automatically retry on transient network failures
        (OSError, ConnectionError, TimeoutError) with exponential backoff.
        Maximum 3 attempts with waits of 2s, 4s between retries.

        Returns:
            The initialized NeuralChunker instance

        Raises:
            ChunkingModelLoadError: If initialization fails after all retries
        """
        logger.info(
            "Initializing NeuralChunker with model=%s, device=%s",
            self._model,
            self._device_map,
        )

        try:
            chunker = self._load_chunker_with_retry()
            logger.info("NeuralChunker initialized successfully")
            return chunker

        except RetryError as e:
            exc = e.last_attempt.exception() if e.last_attempt else None
            original = exc if isinstance(exc, Exception) else None
            error_msg = (
                f"Failed to load chunking model '{self._model}' after 3 attempts. "
                f"Last error: {original}. "
                "Please check your internet connection and try again later."
            )
            logger.error(error_msg)
            raise ChunkingModelLoadError(error_msg, original_error=original) from e

        except ValueError as e:
            error_msg = (
                f"Invalid configuration for chunking model '{self._model}': {e}. "
                "Please verify the model identifier and parameters are correct."
            )
            logger.error(error_msg)
            raise ChunkingModelLoadError(error_msg, original_error=e) from e

        except Exception as e:
            if isinstance(e, NETWORK_RETRY_EXCEPTIONS):
                error_msg = (
                    f"Network error while downloading chunking model '{self._model}': {e}. "
                    "Please check your internet connection and try again."
                )
            else:
                error_msg = (
                    f"Unexpected error loading chunking model '{self._model}': "
                    f"{type(e).__name__}: {e}"
                )
            logger.exception(error_msg)
            raise ChunkingModelLoadError(error_msg, original_error=e) from e

    @retry(
        retry=retry_if_exception_type(NETWORK_RETRY_EXCEPTIONS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_log_retry_attempt,
        reraise=False,
    )
    def _load_chunker_with_retry(self) -> "NeuralChunker":
        """
        Load the NeuralChunker with automatic retry on network failures.

        This method is decorated with tenacity retry logic to handle transient
        network issues during model download from Hugging Face Hub.

        Returns:
            The initialized NeuralChunker instance

        Raises:
            OSError: On file system or network errors (will be retried)
            ConnectionError: On connection failures (will be retried)
            TimeoutError: On timeout (will be retried)
            ValueError: On invalid configuration (not retried)
        """
        from chonkie.chunker.neural import NeuralChunker

        return NeuralChunker(
            model=self._model,
            device_map=self._device_map,
            min_characters_per_chunk=self._min_characters_per_chunk,
        )

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
