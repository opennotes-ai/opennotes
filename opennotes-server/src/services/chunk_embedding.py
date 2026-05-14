import threading

from pydantic_ai import Embedder

from src.config import get_settings
from src.fact_checking.chunk_embedding_service import ChunkEmbeddingService
from src.fact_checking.chunking_service import (
    reset_chunking_service,
    use_chunking_service_sync,
)
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.service import LLMService
from src.monitoring import get_logger

logger = get_logger(__name__)

_encryption_service: EncryptionService | None = None
_llm_client_manager: LLMClientManager | None = None
_embedder: Embedder | None = None
_llm_service: LLMService | None = None
_chunk_embedding_service: ChunkEmbeddingService | None = None
_service_lock = threading.RLock()


def _get_encryption_service() -> EncryptionService:
    global _encryption_service  # noqa: PLW0603
    if _encryption_service is None:
        with _service_lock:
            if _encryption_service is None:
                settings = get_settings()
                _encryption_service = EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    return _encryption_service


def _get_llm_client_manager() -> LLMClientManager:
    global _llm_client_manager  # noqa: PLW0603
    if _llm_client_manager is None:
        with _service_lock:
            if _llm_client_manager is None:
                _llm_client_manager = LLMClientManager(encryption_service=_get_encryption_service())
    return _llm_client_manager


def _get_embedder() -> Embedder:
    global _embedder  # noqa: PLW0603
    if _embedder is None:
        with _service_lock:
            if _embedder is None:
                settings = get_settings()
                _embedder = Embedder(
                    settings.EMBEDDING_MODEL.to_pydantic_ai(),
                    defer_model_check=True,
                )
    return _embedder


def _get_llm_service() -> LLMService:
    global _llm_service  # noqa: PLW0603
    if _llm_service is None:
        with _service_lock:
            if _llm_service is None:
                _llm_service = LLMService(
                    client_manager=_get_llm_client_manager(),
                    embedder=_get_embedder(),
                )
    return _llm_service


def get_chunk_embedding_service() -> ChunkEmbeddingService:
    """Get or create singleton ChunkEmbeddingService with double-checked locking.

    All service dependencies are also singletons, ensuring consistent caching
    behavior for LLM clients and avoiding repeated model loading.

    Lock ordering: acquires _service_lock and _access_lock (via
    use_chunking_service_sync) independently to avoid ABBA deadlock with
    callers that acquire _access_lock without _service_lock (TASK-1061.06).
    """
    global _chunk_embedding_service  # noqa: PLW0603
    if _chunk_embedding_service is None:
        with _service_lock:
            if _chunk_embedding_service is not None:
                return _chunk_embedding_service
            llm_service = _get_llm_service()

        with use_chunking_service_sync() as chunking_service:
            service = ChunkEmbeddingService(
                chunking_service=chunking_service,
                llm_service=llm_service,
            )

        with _service_lock:
            if _chunk_embedding_service is None:
                _chunk_embedding_service = service
    return _chunk_embedding_service


def reset_chunk_embedding_services() -> None:
    """Reset all service singletons. For testing only."""
    global _encryption_service, _llm_client_manager  # noqa: PLW0603
    global _embedder, _llm_service, _chunk_embedding_service  # noqa: PLW0603
    with _service_lock:
        _encryption_service = None
        _llm_client_manager = None
        _embedder = None
        _llm_service = None
        _chunk_embedding_service = None
    reset_chunking_service()
