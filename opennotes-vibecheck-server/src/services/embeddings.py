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

    Empty input -> empty list; does not call the API.
    """
    if not texts:
        return []
    embedder = get_embedder(settings)
    async with vertex_slot(settings):
        result = await embedder.embed_documents(texts)
    return [list(v) for v in result.embeddings]
