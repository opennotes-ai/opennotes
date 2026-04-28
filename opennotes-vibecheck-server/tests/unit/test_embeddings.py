from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from src.config import Settings
from src.services import embeddings
from src.services.embeddings import embed_texts


@dataclass
class _FakeEmbeddingResult:
    embeddings: list[list[float]]


class _BlockingEmbedder:
    def __init__(self) -> None:
        self.first_started = asyncio.Event()
        self.second_entered = asyncio.Event()
        self.release_first = asyncio.Event()

    async def embed_documents(self, texts: list[str]) -> _FakeEmbeddingResult:
        if texts == ["first"]:
            self.first_started.set()
            await self.release_first.wait()
            return _FakeEmbeddingResult(embeddings=[[1.0, 0.0]])

        self.second_entered.set()
        return _FakeEmbeddingResult(embeddings=[[0.0, 1.0]])


async def test_embed_texts_waits_for_vertex_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    embedder = _BlockingEmbedder()
    settings = Settings(VERTEX_MAX_CONCURRENCY=1)
    monkeypatch.setattr(embeddings, "get_embedder", lambda _settings: embedder)

    first_task = asyncio.create_task(embed_texts(["first"], settings))
    await embedder.first_started.wait()

    second_task = asyncio.create_task(embed_texts(["second"], settings))
    await asyncio.sleep(0)

    assert not embedder.second_entered.is_set()

    embedder.release_first.set()
    first_vectors, second_vectors = await asyncio.gather(first_task, second_task)

    assert first_vectors == [[1.0, 0.0]]
    assert second_vectors == [[0.0, 1.0]]
