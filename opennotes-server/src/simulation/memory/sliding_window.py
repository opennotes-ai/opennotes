from __future__ import annotations

from typing import Any

from src.simulation.memory.compactor_protocol import CompactionResult, ModelMessage
from src.simulation.memory.message_utils import _is_system_message

DEFAULT_WINDOW_SIZE = 50


class SlidingWindowCompactor:
    async def compact(
        self, messages: list[ModelMessage], config: dict[str, Any]
    ) -> CompactionResult:
        original_count = len(messages)
        window_size: int = config.get("window_size", DEFAULT_WINDOW_SIZE)

        if len(messages) <= window_size:
            return CompactionResult(
                messages=list(messages),
                original_count=original_count,
                compacted_count=original_count,
                strategy="sliding_window",
                metadata={"window_size": window_size},
            )

        system_message: ModelMessage | None = None
        non_system_messages = messages

        if messages and _is_system_message(messages[0]):
            system_message = messages[0]
            non_system_messages = messages[1:]

        if system_message is not None:
            remaining = window_size - 1
            kept = non_system_messages[-remaining:] if remaining > 0 else []
            result_messages = [system_message, *kept]
        else:
            result_messages = non_system_messages[-window_size:]

        return CompactionResult(
            messages=result_messages,
            original_count=original_count,
            compacted_count=len(result_messages),
            strategy="sliding_window",
            metadata={"window_size": window_size},
        )
