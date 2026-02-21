from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from typing import Any

from src.simulation.memory.compactor_protocol import CompactionResult, ModelMessage

DEFAULT_SIMILARITY_THRESHOLD = 0.92


def _extract_text(message: ModelMessage) -> str:
    if isinstance(message, dict):
        parts = message.get("parts", [])
        texts = []
        for part in parts:
            if isinstance(part, dict):
                content = part.get("content", "")
                if content:
                    texts.append(str(content))
        return " ".join(texts)
    return str(message)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


class SemanticDedupCompactor:
    def __init__(self, embed: Callable[[str], Awaitable[list[float]]]) -> None:
        self._embed = embed

    async def compact(
        self, messages: list[ModelMessage], config: dict[str, Any]
    ) -> CompactionResult:
        original_count = len(messages)
        threshold: float = config.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)

        if not messages:
            return CompactionResult(
                messages=[],
                original_count=0,
                compacted_count=0,
                strategy="semantic_dedup",
                metadata={"similarity_threshold": threshold, "duplicates_removed": 0},
            )

        kept_messages: list[ModelMessage] = []
        kept_embeddings: list[list[float]] = []
        duplicates_removed = 0

        for message in messages:
            text = _extract_text(message)
            embedding = await self._embed(text)

            is_duplicate = False
            for prior_embedding in kept_embeddings:
                similarity = _cosine_similarity(embedding, prior_embedding)
                if similarity >= threshold:
                    is_duplicate = True
                    break

            if is_duplicate:
                duplicates_removed += 1
            else:
                kept_messages.append(message)
                kept_embeddings.append(embedding)

        return CompactionResult(
            messages=kept_messages,
            original_count=original_count,
            compacted_count=len(kept_messages),
            strategy="semantic_dedup",
            metadata={
                "similarity_threshold": threshold,
                "duplicates_removed": duplicates_removed,
            },
        )
