from __future__ import annotations

from typing import Any

from src.simulation.memory.compactor_protocol import MemoryCompactor
from src.simulation.memory.semantic_dedup import SemanticDedupCompactor
from src.simulation.memory.sliding_window import SlidingWindowCompactor
from src.simulation.memory.summarize_and_prune import SummarizeAndPruneCompactor


class CompactorFactory:
    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, compactor_cls: type) -> None:
        cls._registry[name] = compactor_cls

    @classmethod
    def create(cls, strategy: str, **kwargs: Any) -> MemoryCompactor:
        if strategy not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(f"Unknown compaction strategy: {strategy!r}. Available: {available}")
        return cls._registry[strategy](**kwargs)

    @classmethod
    def available_strategies(cls) -> list[str]:
        return sorted(cls._registry.keys())


CompactorFactory.register("sliding_window", SlidingWindowCompactor)
CompactorFactory.register("summarize_and_prune", SummarizeAndPruneCompactor)
CompactorFactory.register("semantic_dedup", SemanticDedupCompactor)
