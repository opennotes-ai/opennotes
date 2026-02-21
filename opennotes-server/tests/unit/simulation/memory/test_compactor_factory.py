import pytest

from src.simulation.memory.compactor_factory import CompactorFactory
from src.simulation.memory.compactor_protocol import MemoryCompactor
from src.simulation.memory.semantic_dedup import SemanticDedupCompactor
from src.simulation.memory.sliding_window import SlidingWindowCompactor
from src.simulation.memory.summarize_and_prune import SummarizeAndPruneCompactor


class TestCompactorImplementsProtocol:
    def test_sliding_window_implements_protocol(self):
        compactor = SlidingWindowCompactor()
        assert isinstance(compactor, MemoryCompactor)

    def test_summarize_and_prune_implements_protocol(self):
        async def noop(text: str) -> str:
            return ""

        compactor = SummarizeAndPruneCompactor(summarizer=noop)
        assert isinstance(compactor, MemoryCompactor)

    def test_semantic_dedup_implements_protocol(self):
        async def noop(text: str) -> list[float]:
            return []

        compactor = SemanticDedupCompactor(embed=noop)
        assert isinstance(compactor, MemoryCompactor)


class TestCompactionResultFields:
    def test_compaction_result_has_required_fields(self):
        from src.simulation.memory.compactor_protocol import CompactionResult

        result = CompactionResult(
            messages=[],
            original_count=10,
            compacted_count=5,
            strategy="test",
        )

        assert result.messages == []
        assert result.original_count == 10
        assert result.compacted_count == 5
        assert result.strategy == "test"
        assert result.metadata == {}

    def test_compaction_result_with_metadata(self):
        from src.simulation.memory.compactor_protocol import CompactionResult

        result = CompactionResult(
            messages=[{"kind": "request"}],
            original_count=1,
            compacted_count=1,
            strategy="test",
            metadata={"key": "value"},
        )

        assert result.metadata == {"key": "value"}


class TestCompactorFactoryCreate:
    def test_creates_sliding_window(self):
        compactor = CompactorFactory.create("sliding_window")
        assert isinstance(compactor, SlidingWindowCompactor)

    def test_creates_summarize_and_prune(self):
        async def noop(text: str) -> str:
            return ""

        compactor = CompactorFactory.create("summarize_and_prune", summarizer=noop)
        assert isinstance(compactor, SummarizeAndPruneCompactor)

    def test_creates_semantic_dedup(self):
        async def noop(text: str) -> list[float]:
            return []

        compactor = CompactorFactory.create("semantic_dedup", embed=noop)
        assert isinstance(compactor, SemanticDedupCompactor)

    def test_raises_for_unknown_strategy(self):
        with pytest.raises(ValueError, match="Unknown compaction strategy"):
            CompactorFactory.create("nonexistent")

    def test_error_message_lists_available_strategies(self):
        with pytest.raises(ValueError, match="sliding_window"):
            CompactorFactory.create("nonexistent")


class TestCompactorFactoryRegister:
    def test_register_custom_strategy(self):
        class CustomCompactor:
            async def compact(self, messages, config):
                pass

        CompactorFactory.register("custom_test", CustomCompactor)
        compactor = CompactorFactory.create("custom_test")
        assert isinstance(compactor, CustomCompactor)
        CompactorFactory._registry.pop("custom_test", None)

    def test_available_strategies_includes_builtins(self):
        strategies = CompactorFactory.available_strategies()
        assert "sliding_window" in strategies
        assert "summarize_and_prune" in strategies
        assert "semantic_dedup" in strategies
