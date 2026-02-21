from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.simulation.memory.compactor_protocol import CompactionResult, ModelMessage

DEFAULT_KEEP_RECENT = 10


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


def _make_summary_message(summary_text: str) -> ModelMessage:
    return {
        "kind": "request",
        "parts": [{"part_kind": "user-prompt", "content": summary_text}],
    }


class SummarizeAndPruneCompactor:
    def __init__(self, summarizer: Callable[[str], Awaitable[str]]) -> None:
        self._summarizer = summarizer

    async def compact(
        self, messages: list[ModelMessage], config: dict[str, Any]
    ) -> CompactionResult:
        original_count = len(messages)
        keep_recent: int = config.get("keep_recent", DEFAULT_KEEP_RECENT)

        if len(messages) <= keep_recent:
            return CompactionResult(
                messages=list(messages),
                original_count=original_count,
                compacted_count=original_count,
                strategy="summarize_and_prune",
                metadata={"keep_recent": keep_recent, "summarized": False},
            )

        old_messages = messages[:-keep_recent]
        recent_messages = messages[-keep_recent:]

        old_text = "\n".join(_extract_text(m) for m in old_messages)
        summary = await self._summarizer(old_text)

        summary_message = _make_summary_message(summary)
        result_messages = [summary_message, *recent_messages]

        return CompactionResult(
            messages=result_messages,
            original_count=original_count,
            compacted_count=len(result_messages),
            strategy="summarize_and_prune",
            metadata={
                "keep_recent": keep_recent,
                "summarized": True,
                "messages_summarized": len(old_messages),
            },
        )
