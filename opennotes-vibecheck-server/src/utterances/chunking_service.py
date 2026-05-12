"""Chunk long utterances before provider-specific analysis."""

from __future__ import annotations

import asyncio

from chonkie import RecursiveChunker
from pydantic import BaseModel, Field

from src.config import Settings, get_settings


class Chunk(BaseModel):
    text: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    chunk_idx: int
    chunk_count: int


class ChunkingService:
    def __init__(self, settings: Settings) -> None:
        self._threshold_tokens = settings.VIBECHECK_CHUNK_THRESHOLD_TOKENS
        self._max_tokens = settings.VIBECHECK_CHUNK_MAX_TOKENS
        self._chunkers: dict[int, RecursiveChunker] = {}

    def chunk_text(self, text: str, *, max_tokens: int | None = None) -> list[Chunk]:
        if not text or not text.strip():
            return []

        token_limit = max_tokens or self._max_tokens
        if self._estimated_tokens(text) <= self._threshold_tokens:
            return [
                Chunk(
                    text=text,
                    start_offset=0,
                    end_offset=len(text),
                    chunk_idx=0,
                    chunk_count=1,
                )
            ]

        chunker = self._chunker_for(token_limit)
        raw_chunks = [
            raw
            for raw in chunker.chunk(text)
            if getattr(raw, "text", "") and getattr(raw, "text", "").strip()
        ]
        chunk_count = len(raw_chunks)
        return [
            Chunk(
                text=raw.text,
                start_offset=max(0, int(raw.start_index)),
                end_offset=max(0, int(raw.end_index)),
                chunk_idx=index,
                chunk_count=chunk_count,
            )
            for index, raw in enumerate(raw_chunks)
        ]

    def _chunker_for(self, max_tokens: int) -> RecursiveChunker:
        if max_tokens not in self._chunkers:
            self._chunkers[max_tokens] = RecursiveChunker(
                tokenizer="character",
                chunk_size=max_tokens * 4,
            )
        return self._chunkers[max_tokens]

    @staticmethod
    def _estimated_tokens(text: str) -> int:
        return max(1, int(len(text) / 4))


_SERVICE_CACHE: dict[tuple[int, int], ChunkingService] = {}
_SERVICE_CACHE_LOCK = asyncio.Lock()


def _cache_key(settings: Settings) -> tuple[int, int]:
    return (
        settings.VIBECHECK_CHUNK_THRESHOLD_TOKENS,
        settings.VIBECHECK_CHUNK_MAX_TOKENS,
    )


async def get_chunking_service(settings: Settings | None = None) -> ChunkingService:
    resolved_settings = settings or get_settings()
    key = _cache_key(resolved_settings)
    if key not in _SERVICE_CACHE:
        async with _SERVICE_CACHE_LOCK:
            if key not in _SERVICE_CACHE:
                _SERVICE_CACHE[key] = ChunkingService(resolved_settings)
    return _SERVICE_CACHE[key]


__all__ = ["Chunk", "ChunkingService", "get_chunking_service"]
