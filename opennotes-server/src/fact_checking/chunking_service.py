"""
Chunking service for semantic text segmentation.

This module provides the ChunkingService class that uses NeuralChunker from the
chonkie library to split text into semantically coherent chunks. This is used
for creating more granular embeddings that improve semantic search accuracy.

The NeuralChunker uses a fine-tuned BERT model to detect topic shifts and
create chunks at natural semantic boundaries rather than arbitrary character
or token limits.

Singleton Pattern (TASK-1058.02):
    The module provides singleton access to ChunkingService to avoid repeated
    model loading. Use get_chunking_service() to get the singleton instance.
    Use use_chunking_service() or use_chunking_service_sync() for gated access
    that ensures only one caller uses the chunker at a time.

Concurrency Model (TASK-1058.18):
    This module provides two context managers for accessing the shared ChunkingService
    singleton with unified concurrency control via a single threading.Lock:

    - use_chunking_service() - async context manager for async code paths
      Acquires the lock via run_in_executor to avoid blocking the event loop.

    - use_chunking_service_sync() - sync context manager for sync code paths
      Directly acquires the threading lock.

    Both context managers use the same underlying lock (_access_lock), ensuring
    mutual exclusion between async and sync callers. This prevents race conditions
    where an async caller and sync caller could access the singleton simultaneously.

    Process Isolation:
        TaskIQ workers and DBOS workers run in separate processes. Each process
        maintains its own singleton instance with independent locking. Cross-process
        coordination is not needed because:

        1. NeuralChunker model loading is process-local (no shared memory)
        2. Each process has its own event loop and thread pool
        3. The lock only coordinates access within one process
"""

import asyncio
import threading
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
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

_chunking_service_singleton: "ChunkingService | None" = None
_singleton_lock = threading.Lock()
_access_lock = threading.Lock()  # Unified lock for all access patterns (TASK-1058.18)

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

    DEFAULT_MODEL = "mirth/chonky_distilbert_base_uncased_1"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        device_map: str | None = None,
        min_characters_per_chunk: int = 50,
    ) -> None:
        """
        Initialize the ChunkingService.

        Args:
            model: The identifier or path to the fine-tuned BERT model
                   used for detecting semantic shifts. The previous default
                   'mirth/chonky_modernbert_base_1' has tokenizer compatibility
                   issues with current transformers/tokenizers versions.
            device_map: Device to run inference on. Use None (default) to load
                       on CPU without requiring the accelerate library. Pass
                       'cuda', 'mps', or 'auto' for GPU support (requires
                       accelerate library to be installed).
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
            device_map=self._device_map,  # type: ignore
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


def get_chunking_service(
    model: str = ChunkingService.DEFAULT_MODEL,
    device_map: str | None = None,
    min_characters_per_chunk: int = 50,
) -> ChunkingService:
    """
    Get the singleton ChunkingService instance.

    This function implements a thread-safe singleton pattern to ensure the
    NeuralChunker model is loaded only once per process. Subsequent calls
    return the same instance, saving memory and initialization time.

    Note: If called with different parameters after the singleton is created,
    the original singleton is returned (parameters are ignored). Call
    reset_chunking_service() first if you need to change configuration.

    Args:
        model: Model identifier (only used on first call)
        device_map: Device mapping (only used on first call)
        min_characters_per_chunk: Minimum chars per chunk (only used on first call)

    Returns:
        The singleton ChunkingService instance

    Example:
        >>> service = get_chunking_service()
        >>> chunks = service.chunk_text("Some text to chunk")
    """
    global _chunking_service_singleton  # noqa: PLW0603

    if _chunking_service_singleton is None:
        with _singleton_lock:
            if _chunking_service_singleton is None:
                logger.info("Creating ChunkingService singleton")
                _chunking_service_singleton = ChunkingService(
                    model=model,
                    device_map=device_map,
                    min_characters_per_chunk=min_characters_per_chunk,
                )
    return _chunking_service_singleton


def reset_chunking_service() -> None:
    """
    Reset the singleton ChunkingService instance.

    This function clears the cached singleton, allowing a new instance to be
    created on the next call to get_chunking_service(). Primarily useful for
    testing or when configuration changes are needed.

    Warning: Any in-flight operations using the old singleton may fail.
    """
    global _chunking_service_singleton  # noqa: PLW0603

    with _singleton_lock:
        if _chunking_service_singleton is not None:
            logger.info("Resetting ChunkingService singleton")
            _chunking_service_singleton = None


@asynccontextmanager
async def use_chunking_service(
    model: str = ChunkingService.DEFAULT_MODEL,
    device_map: str | None = None,
    min_characters_per_chunk: int = 50,
) -> AsyncGenerator[ChunkingService, None]:
    """
    Async context manager for lock-gated access to the ChunkingService.

    This ensures only one caller can use the NeuralChunker at a time, which is
    important because the model may not be thread-safe and concurrent access
    could cause issues or excessive memory usage.

    Uses the unified _access_lock (threading.Lock) acquired via run_in_executor
    to avoid blocking the event loop while waiting. This provides mutual exclusion
    with sync callers using use_chunking_service_sync().

    Args:
        model: Model identifier (only used on first call)
        device_map: Device mapping (only used on first call)
        min_characters_per_chunk: Minimum chars per chunk (only used on first call)

    Yields:
        The singleton ChunkingService instance

    Example:
        >>> async with use_chunking_service() as service:
        ...     chunks = service.chunk_text("Text to chunk")
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _access_lock.acquire)
    try:
        yield get_chunking_service(
            model=model,
            device_map=device_map,
            min_characters_per_chunk=min_characters_per_chunk,
        )
    finally:
        _access_lock.release()


@contextmanager
def use_chunking_service_sync(
    model: str = ChunkingService.DEFAULT_MODEL,
    device_map: str | None = None,
    min_characters_per_chunk: int = 50,
) -> Generator[ChunkingService, None, None]:
    """
    Sync context manager for lock-gated access to the ChunkingService.

    This is designed for use in synchronous DBOS workflow steps where async
    context managers are not available. Uses the unified _access_lock
    (threading.Lock) to ensure mutual exclusion with async callers.

    Args:
        model: Model identifier (only used on first call)
        device_map: Device mapping (only used on first call)
        min_characters_per_chunk: Minimum chars per chunk (only used on first call)

    Yields:
        The singleton ChunkingService instance

    Example:
        >>> with use_chunking_service_sync() as service:
        ...     chunks = service.chunk_text("Text to chunk")
    """
    with _access_lock:
        yield get_chunking_service(
            model=model,
            device_map=device_map,
            min_characters_per_chunk=min_characters_per_chunk,
        )
