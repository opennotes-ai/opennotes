from __future__ import annotations

from itertools import pairwise

from src.config import Settings
from src.utterances.chunking_service import ChunkingService


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
        Settings(VIBECHECK_CHUNK_THRESHOLD_TOKENS=10, VIBECHECK_CHUNK_MAX_TOKENS=12)
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
