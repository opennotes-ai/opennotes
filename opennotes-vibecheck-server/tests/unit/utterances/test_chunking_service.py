from __future__ import annotations

import asyncio
from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import patch

from src.config import Settings
from src.utterances.chunking_service import (
    _SERVICE_CACHE,
    ChunkingService,
    get_chunking_service,
)


def test_short_text_returns_single_chunk_spanning_input() -> None:
    service = ChunkingService(
        Settings(VIBECHECK_CHUNK_THRESHOLD_TOKENS=800, VIBECHECK_CHUNK_MAX_TOKENS=50)
    )

    chunks = service.chunk_text("short post")

    assert len(chunks) == 1
    assert chunks[0].text == "short post"
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == 10
    assert chunks[0].chunk_idx == 0
    assert chunks[0].chunk_count == 1


def test_long_text_returns_monotonic_chunks() -> None:
    service = ChunkingService(
        Settings(VIBECHECK_CHUNK_THRESHOLD_TOKENS=12, VIBECHECK_CHUNK_MAX_TOKENS=10)
    )
    text = "\n\n".join(
        [
            "Paragraph one has enough words to cross the chunk limit.",
            "Paragraph two keeps going with a different sentence.",
            "Paragraph three gives the chunker more content to split.",
        ]
    )

    chunks = service.chunk_text(text)

    assert len(chunks) > 1
    assert [chunk.chunk_idx for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.chunk_count for chunk in chunks} == {len(chunks)}
    assert chunks[0].start_offset == 0
    assert chunks[-1].end_offset == len(text)
    assert all(left.end_offset <= right.start_offset for left, right in pairwise(chunks))


def test_empty_or_whitespace_text_returns_no_chunks() -> None:
    service = ChunkingService(Settings())

    assert service.chunk_text("") == []
    assert service.chunk_text("   \n\t") == []


def test_gap_metric_emitted_when_chunks_have_gaps() -> None:
    service = ChunkingService(
        Settings(VIBECHECK_CHUNK_THRESHOLD_TOKENS=1, VIBECHECK_CHUNK_MAX_TOKENS=1)
    )

    class FakeChunker:
        def chunk(self, text: str) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(text="alpha", start_index=0, end_index=5),
                SimpleNamespace(text="omega", start_index=8, end_index=len(text)),
            ]

    with (
        patch.object(service, "_chunker_for", return_value=FakeChunker()),
        patch("src.utterances.chunking_service.logfire.info") as log_info,
    ):
        chunks = service.chunk_text("alpha   omega")

    assert len(chunks) == 2
    log_info.assert_called_once_with(
        "chunking.gap_metric",
        text_length=13,
        chunk_count=2,
        dropped_chars=3,
    )


def test_gap_metric_not_emitted_for_single_chunk() -> None:
    service = ChunkingService(Settings())

    with patch("src.utterances.chunking_service.logfire.info") as log_info:
        chunks = service.chunk_text("short post")

    assert len(chunks) == 1
    log_info.assert_not_called()


def test_chunker_exception_falls_back_to_single_chunk() -> None:
    service = ChunkingService(
        Settings(VIBECHECK_CHUNK_THRESHOLD_TOKENS=1, VIBECHECK_CHUNK_MAX_TOKENS=1)
    )

    class FailingChunker:
        def chunk(self, text: str) -> list[SimpleNamespace]:
            raise RuntimeError("boom")

    with patch.object(service, "_chunker_for", return_value=FailingChunker()):
        chunks = service.chunk_text("some long text here")

    assert len(chunks) == 1
    assert chunks[0].text == "some long text here"
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == 19
    assert chunks[0].chunk_idx == 0
    assert chunks[0].chunk_count == 1


def test_chunker_exception_emits_logfire_warning() -> None:
    service = ChunkingService(
        Settings(VIBECHECK_CHUNK_THRESHOLD_TOKENS=1, VIBECHECK_CHUNK_MAX_TOKENS=1)
    )

    class FailingChunker:
        def chunk(self, text: str) -> list[SimpleNamespace]:
            raise RuntimeError("boom")

    with (
        patch.object(service, "_chunker_for", return_value=FailingChunker()),
        patch("src.utterances.chunking_service.logfire.warning") as log_warning,
    ):
        service.chunk_text("some long text here")

    log_warning.assert_called_once_with(
        "chunking.fallback_single_chunk",
        error="boom",
        error_type="RuntimeError",
        text_length=19,
        max_tokens=1,
    )


def test_cache_works_across_event_loops() -> None:
    _SERVICE_CACHE.clear()
    settings = Settings(
        VIBECHECK_CHUNK_THRESHOLD_TOKENS=800,
        VIBECHECK_CHUNK_MAX_TOKENS=600,
    )
    results: list[ChunkingService] = []

    for _ in range(2):
        loop = asyncio.new_event_loop()
        try:
            async def go() -> ChunkingService:
                return get_chunking_service(settings)

            results.append(loop.run_until_complete(go()))
        finally:
            loop.close()

    assert results[0] is results[1]


def test_cache_returns_same_instance_for_same_settings() -> None:
    _SERVICE_CACHE.clear()
    settings = Settings(
        VIBECHECK_CHUNK_THRESHOLD_TOKENS=800,
        VIBECHECK_CHUNK_MAX_TOKENS=600,
    )

    assert get_chunking_service(settings) is get_chunking_service(settings)


def test_cache_returns_distinct_instance_for_different_settings() -> None:
    _SERVICE_CACHE.clear()

    first = get_chunking_service(
        Settings(VIBECHECK_CHUNK_THRESHOLD_TOKENS=800, VIBECHECK_CHUNK_MAX_TOKENS=600)
    )
    second = get_chunking_service(
        Settings(VIBECHECK_CHUNK_THRESHOLD_TOKENS=800, VIBECHECK_CHUNK_MAX_TOKENS=500)
    )

    assert first is not second
