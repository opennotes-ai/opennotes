from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.simulation.memory.compactor_protocol import CompactionResult, ModelMessage
from src.simulation.memory.message_utils import extract_text, group_tool_pairs

DEFAULT_KEEP_RECENT = 10


def _make_summary_message(summary_text: str) -> Any:
    return {
        "kind": "request",
        "parts": [{"part_kind": "system-prompt", "content": summary_text}],
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

        split_idx = len(messages) - keep_recent
        groups = group_tool_pairs(messages)

        cumulative = 0
        for group in groups:
            group_end = cumulative + len(group)
            if cumulative < split_idx < group_end:
                split_idx = cumulative
                break
            cumulative = group_end

        old_messages = messages[:split_idx]
        recent_messages = messages[split_idx:]

        old_text = "\n".join(extract_text(m) for m in old_messages)
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
