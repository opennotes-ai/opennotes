from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
else:
    ModelMessage = Any


@dataclass
class CompactionResult:
    messages: list[ModelMessage]
    original_count: int
    compacted_count: int
    strategy: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MemoryCompactor(Protocol):
    async def compact(
        self, messages: list[ModelMessage], config: dict[str, Any]
    ) -> CompactionResult: ...
