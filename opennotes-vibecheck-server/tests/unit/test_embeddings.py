from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from src.config import Settings
from src.services import embeddings
from src.services.embeddings import VERTEX_EMBEDDING_MAX_BATCH, embed_texts


@pytest.fixture(autouse=True)
def _reset_embedder_singleton() -> None:
    embeddings._embedder = None


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


@dataclass
class _RecordingEmbedder:
    call_sizes: list[int] = field(default_factory=list)

    async def embed_documents(self, texts: list[str]) -> _FakeEmbeddingResult:
        self.call_sizes.append(len(texts))
        return _FakeEmbeddingResult(embeddings=[[float(int(t))] for t in texts])


class _ExplodingEmbedder:
    async def embed_documents(self, texts: list[str]) -> _FakeEmbeddingResult:
        raise AssertionError("embedder should not be called for empty input")


async def test_embed_texts_empty_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "get_embedder", lambda _settings: _ExplodingEmbedder())
    settings = Settings(VERTEX_MAX_CONCURRENCY=1)

    result = await embed_texts([], settings)

    assert result == []


async def test_embed_texts_single_batch_at_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    embedder = _RecordingEmbedder()
    monkeypatch.setattr(embeddings, "get_embedder", lambda _settings: embedder)
    settings = Settings(VERTEX_MAX_CONCURRENCY=1)
    texts = [str(i) for i in range(VERTEX_EMBEDDING_MAX_BATCH)]

    result = await embed_texts(texts, settings)

    assert embedder.call_sizes == [VERTEX_EMBEDDING_MAX_BATCH]
    assert len(result) == VERTEX_EMBEDDING_MAX_BATCH
    assert result == [[float(i)] for i in range(VERTEX_EMBEDDING_MAX_BATCH)]


async def test_embed_texts_chunks_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    embedder = _RecordingEmbedder()
    monkeypatch.setattr(embeddings, "get_embedder", lambda _settings: embedder)
    settings = Settings(VERTEX_MAX_CONCURRENCY=1)
    texts = [str(i) for i in range(261)]

    result = await embed_texts(texts, settings)

    assert embedder.call_sizes == [250, 11]
    assert len(result) == 261
    assert result == [[float(i)] for i in range(261)]


async def test_embed_texts_preserves_order_across_three_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedder = _RecordingEmbedder()
    monkeypatch.setattr(embeddings, "get_embedder", lambda _settings: embedder)
    settings = Settings(VERTEX_MAX_CONCURRENCY=1)
    texts = [str(i) for i in range(501)]

    result = await embed_texts(texts, settings)

    assert embedder.call_sizes == [250, 250, 1]
    assert result == [[float(i)] for i in range(501)]
