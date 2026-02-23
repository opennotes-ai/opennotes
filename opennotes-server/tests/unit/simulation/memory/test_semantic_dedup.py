from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.simulation.memory.semantic_dedup import SemanticDedupCompactor


def _make_user_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": content}]}


def _make_system_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "system-prompt", "content": content}]}


class TestSemanticDedupCompactor:
    @pytest.mark.asyncio
    async def test_removes_near_duplicates(self):
        embeddings_map = {
            "hello world": [1.0, 0.0, 0.0],
            "hello world!": [0.99, 0.01, 0.0],
            "goodbye moon": [0.0, 1.0, 0.0],
            "something else": [0.0, 0.0, 1.0],
            "another thing": [0.3, 0.3, 0.6],
        }

        async def mock_embed(texts: list[str]) -> list[list[float]]:
            return [embeddings_map.get(t, [0.0, 0.0, 0.0]) for t in texts]

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
        call_count = 0

        async def mock_embed(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            unique_embeddings = {
                "first": [1.0, 0.0, 0.0],
                "second": [0.0, 1.0, 0.0],
                "third": [0.0, 0.0, 1.0],
            }
            return [unique_embeddings.get(t, [0.5, 0.5, 0.5]) for t in texts]

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [
            _make_user_message("first"),
            _make_user_message("second"),
            _make_user_message("third"),
        ]

        result = await compactor.compact(messages, {"similarity_threshold": 0.92})

        contents = [m["parts"][0]["content"] for m in result.messages]
        assert contents == ["first", "second", "third"]
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_threshold_1_removes_nothing(self):
        async def mock_embed(texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0]] * len(texts)

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
        async def mock_embed(texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0]] * len(texts)

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
        mock_embed = AsyncMock(return_value=[])
        compactor = SemanticDedupCompactor(embed=mock_embed)

        result = await compactor.compact([], {"similarity_threshold": 0.92})

        assert result.compacted_count == 0
        assert result.original_count == 0
        assert result.messages == []
        mock_embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_similarity_threshold(self):
        async def mock_embed(texts: list[str]) -> list[list[float]]:
            mapping = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
            return [mapping.get(t, [0.5, 0.5]) for t in texts]

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [_make_user_message("a"), _make_user_message("b")]

        result = await compactor.compact(messages, {})

        assert result.metadata["similarity_threshold"] == 0.92
        assert result.compacted_count == 2

    @pytest.mark.asyncio
    async def test_strategy_name_in_result(self):
        mock_embed = AsyncMock(return_value=[])
        compactor = SemanticDedupCompactor(embed=mock_embed)

        result = await compactor.compact([], {})

        assert result.strategy == "semantic_dedup"

    @pytest.mark.asyncio
    async def test_batch_embed_single_call(self):
        call_count = 0

        async def mock_embed(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            return [[float(i), 0.0, 0.0] for i in range(len(texts))]

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [_make_user_message(f"msg-{i}") for i in range(10)]

        await compactor.compact(messages, {"similarity_threshold": 0.99})

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_preserves_system_messages(self):
        async def mock_embed(texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0]] * len(texts)

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [
            _make_system_message("You are a helper"),
            _make_user_message("hello"),
            _make_user_message("hello again"),
        ]

        result = await compactor.compact(messages, {"similarity_threshold": 0.0})

        assert result.messages[0]["parts"][0]["part_kind"] == "system-prompt"
        assert result.messages[0]["parts"][0]["content"] == "You are a helper"
        assert len(result.messages) == 2

    @pytest.mark.asyncio
    async def test_system_messages_not_embedded(self):
        received_texts: list[list[str]] = []

        async def mock_embed(texts: list[str]) -> list[list[float]]:
            received_texts.append(texts)
            return [[float(i), 0.0, 0.0] for i in range(len(texts))]

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [
            _make_system_message("system"),
            _make_user_message("user1"),
            _make_user_message("user2"),
        ]

        await compactor.compact(messages, {"similarity_threshold": 0.99})

        assert len(received_texts) == 1
        assert "system" not in received_texts[0]
        assert "user1" in received_texts[0]
        assert "user2" in received_texts[0]

    @pytest.mark.asyncio
    async def test_max_messages_limits_input(self):
        import math

        async def mock_embed(texts: list[str]) -> list[list[float]]:
            result = []
            for i in range(len(texts)):
                angle = (i + 1) * math.pi / (2 * (len(texts) + 1))
                result.append([math.cos(angle), math.sin(angle), 0.0])
            return result

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [_make_user_message(f"msg-{i}") for i in range(20)]

        result = await compactor.compact(
            messages, {"max_messages": 5, "similarity_threshold": 0.99}
        )

        assert result.metadata["max_messages"] == 5
        assert result.original_count == 20
        assert result.compacted_count == 20

    @pytest.mark.asyncio
    async def test_max_messages_embeds_only_tail(self):
        received_texts: list[list[str]] = []

        async def mock_embed(texts: list[str]) -> list[list[float]]:
            received_texts.append(texts)
            return [[float(i), 0.0, 0.0] for i in range(len(texts))]

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [_make_user_message(f"msg-{i}") for i in range(10)]

        await compactor.compact(messages, {"max_messages": 3, "similarity_threshold": 0.99})

        assert len(received_texts) == 1
        assert len(received_texts[0]) == 3
        assert received_texts[0] == ["msg-7", "msg-8", "msg-9"]

    @pytest.mark.asyncio
    async def test_preserves_original_order_with_system_and_dedup(self):
        async def mock_embed(texts: list[str]) -> list[list[float]]:
            mapping = {
                "a": [1.0, 0.0, 0.0],
                "b": [0.0, 1.0, 0.0],
                "c": [0.0, 0.0, 1.0],
            }
            return [mapping.get(t, [0.5, 0.5, 0.5]) for t in texts]

        compactor = SemanticDedupCompactor(embed=mock_embed)
        messages = [
            _make_system_message("system"),
            _make_user_message("a"),
            _make_user_message("b"),
            _make_user_message("c"),
        ]

        result = await compactor.compact(messages, {"similarity_threshold": 0.92})

        contents = [m["parts"][0]["content"] for m in result.messages]
        assert contents == ["system", "a", "b", "c"]
