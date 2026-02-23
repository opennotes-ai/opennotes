from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from typing import Any

from src.simulation.memory.compactor_protocol import CompactionResult, ModelMessage
from src.simulation.memory.message_utils import extract_text, is_system_message

DEFAULT_SIMILARITY_THRESHOLD = 0.92
DEFAULT_MAX_MESSAGES = 500


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
    def __init__(self, embed: Callable[[list[str]], Awaitable[list[list[float]]]]) -> None:
        self._embed = embed

    async def compact(
        self, messages: list[ModelMessage], config: dict[str, Any]
    ) -> CompactionResult:
        original_count = len(messages)
        threshold: float = config.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)
        max_messages: int = config.get("max_messages", DEFAULT_MAX_MESSAGES)

        if not messages:
            return CompactionResult(
                messages=[],
                original_count=0,
                compacted_count=0,
                strategy="semantic_dedup",
                metadata={
                    "similarity_threshold": threshold,
                    "duplicates_removed": 0,
                    "max_messages": max_messages,
                },
            )

        preserved: list[tuple[int, ModelMessage]] = []
        candidates: list[tuple[int, ModelMessage]] = []
        for idx, msg in enumerate(messages):
            if is_system_message(msg):
                preserved.append((idx, msg))
            else:
                candidates.append((idx, msg))

        if len(candidates) > max_messages:
            overflow = candidates[:-max_messages]
            candidates = candidates[-max_messages:]
            preserved.extend(overflow)

        texts = [extract_text(msg) for _, msg in candidates]
        embeddings = await self._embed(texts) if texts else []

        kept_indices: list[int] = []
        kept_embeddings: list[list[float]] = []
        duplicates_removed = 0

        for i, embedding in enumerate(embeddings):
            is_duplicate = False
            for prior_embedding in kept_embeddings:
                similarity = _cosine_similarity(embedding, prior_embedding)
                if similarity >= threshold:
                    is_duplicate = True
                    break

            if is_duplicate:
                duplicates_removed += 1
            else:
                kept_indices.append(i)
                kept_embeddings.append(embedding)

        deduped: list[tuple[int, ModelMessage]] = [candidates[i] for i in kept_indices]

        all_kept = preserved + deduped
        all_kept.sort(key=lambda t: t[0])
        result_messages = [msg for _, msg in all_kept]

        return CompactionResult(
            messages=result_messages,
            original_count=original_count,
            compacted_count=len(result_messages),
            strategy="semantic_dedup",
            metadata={
                "similarity_threshold": threshold,
                "duplicates_removed": duplicates_removed,
                "max_messages": max_messages,
            },
        )
