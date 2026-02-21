from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.simulation.memory.semantic_dedup import SemanticDedupCompactor


def _make_user_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": content}]}


class TestSemanticDedupCompactor:
    @pytest.mark.asyncio
    async def test_removes_near_duplicates(self):
        embeddings = {
            "hello world": [1.0, 0.0, 0.0],
            "hello world!": [0.99, 0.01, 0.0],
            "goodbye moon": [0.0, 1.0, 0.0],
            "something else": [0.0, 0.0, 1.0],
            "another thing": [0.3, 0.3, 0.6],
        }

        async def mock_embed(text: str) -> list[float]:
            return embeddings.get(text, [0.0, 0.0, 0.0])

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [
            _make_user_message("hello world"),
            _make_user_message("goodbye moon"),
            _make_user_message("hello world!"),
            _make_user_message("something else"),
            _make_user_message("another thing"),
        ]

        result = await compactor.compact(messages, {"similarity_threshold": 0.95})

        assert result.original_count == 5
        assert result.compacted_count == 4
        assert result.metadata["duplicates_removed"] == 1
        contents = [m["parts"][0]["content"] for m in result.messages]
        assert "hello world" in contents
        assert "hello world!" not in contents

    @pytest.mark.asyncio
    async def test_preserves_order(self):
        call_order: list[str] = []

        async def mock_embed(text: str) -> list[float]:
            call_order.append(text)
            unique_embeddings = {
                "first": [1.0, 0.0, 0.0],
                "second": [0.0, 1.0, 0.0],
                "third": [0.0, 0.0, 1.0],
            }
            return unique_embeddings.get(text, [0.5, 0.5, 0.5])

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [
            _make_user_message("first"),
            _make_user_message("second"),
            _make_user_message("third"),
        ]

        result = await compactor.compact(messages, {"similarity_threshold": 0.92})

        contents = [m["parts"][0]["content"] for m in result.messages]
        assert contents == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_threshold_1_removes_nothing(self):
        async def mock_embed(text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [
            _make_user_message("a"),
            _make_user_message("b"),
            _make_user_message("c"),
        ]

        result = await compactor.compact(messages, {"similarity_threshold": 1.01})

        assert result.compacted_count == 3
        assert result.metadata["duplicates_removed"] == 0

    @pytest.mark.asyncio
    async def test_threshold_0_removes_all_but_first(self):
        async def mock_embed(text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [
            _make_user_message("a"),
            _make_user_message("b"),
            _make_user_message("c"),
        ]

        result = await compactor.compact(messages, {"similarity_threshold": 0.0})

        assert result.compacted_count == 1
        assert result.messages[0]["parts"][0]["content"] == "a"

    @pytest.mark.asyncio
    async def test_handles_empty_messages(self):
        mock_embed = AsyncMock(return_value=[1.0, 0.0])
        compactor = SemanticDedupCompactor(embed=mock_embed)

        result = await compactor.compact([], {"similarity_threshold": 0.92})

        assert result.compacted_count == 0
        assert result.original_count == 0
        assert result.messages == []
        mock_embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_similarity_threshold(self):
        async def mock_embed(text: str) -> list[float]:
            return {"a": [1.0, 0.0], "b": [0.0, 1.0]}.get(text, [0.5, 0.5])

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [_make_user_message("a"), _make_user_message("b")]

        result = await compactor.compact(messages, {})

        assert result.metadata["similarity_threshold"] == 0.92
        assert result.compacted_count == 2

    @pytest.mark.asyncio
    async def test_strategy_name_in_result(self):
        mock_embed = AsyncMock(return_value=[1.0, 0.0])
        compactor = SemanticDedupCompactor(embed=mock_embed)

        result = await compactor.compact([], {})

        assert result.strategy == "semantic_dedup"
