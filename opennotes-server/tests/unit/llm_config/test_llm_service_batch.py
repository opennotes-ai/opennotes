"""Unit tests for LLMService batch embedding functionality."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llm_config.service import VERTEX_EMBEDDING_MAX_BATCH, LLMService


@dataclass
class _FakeEmbeddingResult:
    embeddings: list[list[float]]
    inputs: list[str]
    input_type: str
    model_name: str
    provider_name: str


def _make_embedder_mock(**overrides: object) -> MagicMock:
    mock = MagicMock()
    mock.embed_documents = AsyncMock(**overrides)
    mock.embed_query = AsyncMock(**overrides)
    return mock


class TestGenerateEmbeddingsBatch:
    """Tests for LLMService.generate_embeddings_batch() method."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        mock_embedder = _make_embedder_mock()
        service = LLMService(client_manager=MagicMock(), embedder=mock_embedder)

        results = await service.generate_embeddings_batch(texts=[])

        assert results == []
        mock_embedder.embed_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_embedding_single_api_call(self):
        result = _FakeEmbeddingResult(
            embeddings=[[0.1] * 1536, [0.2] * 1536, [0.3] * 1536],
            inputs=["Text A", "Text B", "Text C"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        mock_embedder = _make_embedder_mock(return_value=result)
        service = LLMService(client_manager=MagicMock(), embedder=mock_embedder)

        results = await service.generate_embeddings_batch(
            texts=["Text A", "Text B", "Text C"],
        )

        mock_embedder.embed_documents.assert_awaited_once()
        call_args = mock_embedder.embed_documents.call_args
        assert call_args[0][0] == ["Text A", "Text B", "Text C"]

        assert len(results) == 3
        assert results[0][0] == [0.1] * 1536
        assert results[1][0] == [0.2] * 1536
        assert results[2][0] == [0.3] * 1536
        assert all(r[1] == "openai" for r in results)
        assert all(r[2] == "text-embedding-3-small" for r in results)

    @pytest.mark.asyncio
    async def test_batch_returns_correct_order(self):
        result = _FakeEmbeddingResult(
            embeddings=[[0.1] * 1536, [0.2] * 1536, [0.3] * 1536],
            inputs=["Text 0", "Text 1", "Text 2"],
            input_type="document",
            model_name="text-embedding-3-small",
            provider_name="openai",
        )
        mock_embedder = _make_embedder_mock(return_value=result)
        service = LLMService(client_manager=MagicMock(), embedder=mock_embedder)

        results = await service.generate_embeddings_batch(
            texts=["Text 0", "Text 1", "Text 2"],
        )

        assert results[0][0] == [0.1] * 1536
        assert results[1][0] == [0.2] * 1536
        assert results[2][0] == [0.3] * 1536

    @pytest.mark.asyncio
    async def test_batch_chunks_inputs_over_vertex_cap(self):
        """Inputs >250 must be split into <=250 sub-batches; outputs preserve input order."""
        call_sizes: list[int] = []

        async def fake_embed_documents(texts: list[str]) -> _FakeEmbeddingResult:
            call_sizes.append(len(texts))
            return _FakeEmbeddingResult(
                embeddings=[[float(int(t))] for t in texts],
                inputs=list(texts),
                input_type="document",
                model_name="gemini-embedding-001",
                provider_name="google",
            )

        mock_embedder = MagicMock()
        mock_embedder.embed_documents = AsyncMock(side_effect=fake_embed_documents)
        mock_embedder.embed_query = AsyncMock()
        service = LLMService(client_manager=MagicMock(), embedder=mock_embedder)
        texts = [str(i) for i in range(261)]

        results = await service.generate_embeddings_batch(texts=texts)

        assert call_sizes == [VERTEX_EMBEDDING_MAX_BATCH, 11]
        assert len(results) == 261
        assert [r[0] for r in results] == [[float(i)] for i in range(261)]
        assert all(r[1] == "google" for r in results)
        assert all(r[2] == "gemini-embedding-001" for r in results)
