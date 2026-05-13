"""Shared pydantic-ai Embedder wrapper for vibecheck analyses.

Uses Vertex AI via pydantic-ai's first-class Embedder. Mirrors opennotes-server's
pattern (see src/services/chunk_embedding.py). Configured via
Settings.VERTEXAI_EMBEDDING_MODEL (e.g. 'google-vertex:gemini-embedding-001').
"""
from __future__ import annotations

import threading

from pydantic_ai import Embedder

from src.config import Settings
from src.services.vertex_limiter import vertex_slot

_embedder: Embedder | None = None
_lock = threading.RLock()

# gemini-embedding-001 hard cap: API rejects batchSize >= 251 with INVALID_ARGUMENT.
VERTEX_EMBEDDING_MAX_BATCH = 250


def get_embedder(settings: Settings) -> Embedder:
    """Double-checked-locking singleton — matches opennotes-server chunk_embedding._get_embedder."""
    global _embedder  # noqa: PLW0603
    if _embedder is None:
        with _lock:
            if _embedder is None:
                _embedder = Embedder(settings.VERTEXAI_EMBEDDING_MODEL)
    return _embedder


async def embed_texts(texts: list[str], settings: Settings) -> list[list[float]]:
    """Convenience: embed a batch of texts, return vectors in input order.

    Empty input -> empty list; does not call the API. Inputs larger than
    VERTEX_EMBEDDING_MAX_BATCH are split into successive sub-batches, with each
    sub-batch acquiring its own vertex_slot so other Vertex callers can
    interleave between chunks; results are concatenated in input order.
    """
    if not texts:
        return []
    embedder = get_embedder(settings)
    out: list[list[float]] = []
    for start in range(0, len(texts), VERTEX_EMBEDDING_MAX_BATCH):
        chunk = texts[start : start + VERTEX_EMBEDDING_MAX_BATCH]
        async with vertex_slot(settings):
            result = await embedder.embed_documents(chunk)
        out.extend(list(v) for v in result.embeddings)
    return out
