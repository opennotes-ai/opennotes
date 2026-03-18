from __future__ import annotations

import logging
from typing import Any

from src.simulation.memory.message_utils import (
    strip_orphaned_tool_messages,
    validate_tool_pairs,
)


def _make_user_message(content: str) -> dict[str, Any]:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": content}]}


def _make_response_message(content: str) -> dict[str, Any]:
    return {"kind": "response", "parts": [{"part_kind": "text", "content": content}]}


def _make_tool_call_response(tool_name: str = "test_tool", args: str = "{}") -> dict[str, Any]:
    return {
        "kind": "response",
        "parts": [
            {
                "part_kind": "tool-call",
                "tool_name": tool_name,
                "args": args,
                "tool_call_id": "call-1",
            }
        ],
    }


def _make_tool_return_request(
    tool_name: str = "test_tool", content: str = "result"
) -> dict[str, Any]:
    return {
        "kind": "request",
        "parts": [
            {
                "part_kind": "tool-return",
                "tool_name": tool_name,
                "content": content,
                "tool_call_id": "call-1",
            }
        ],
    }


class TestStripOrphanedToolMessages:
    def test_strips_orphaned_tool_return(self):
        messages = [
            _make_user_message("hello"),
            _make_tool_return_request("test_tool", "result"),
            _make_user_message("world"),
        ]
        result = strip_orphaned_tool_messages(messages)
        assert len(result) == 2
        assert result[0] == messages[0]
        assert result[1] == messages[2]

    def test_preserves_valid_tool_pair(self):
        messages = [
            _make_user_message("hello"),
            _make_tool_call_response("test_tool"),
            _make_tool_return_request("test_tool", "result"),
            _make_user_message("world"),
        ]
        result = strip_orphaned_tool_messages(messages)
        assert len(result) == 4
        assert result == messages

    def test_empty_messages(self):
        result = strip_orphaned_tool_messages([])
        assert result == []

    def test_strips_multiple_orphaned_returns(self):
        messages = [
            _make_tool_return_request("a", "res_a"),
            _make_user_message("hello"),
            _make_tool_return_request("b", "res_b"),
        ]
        result = strip_orphaned_tool_messages(messages)
        assert len(result) == 1
        assert result[0] == messages[1]

    def test_preserves_non_tool_messages(self):
        messages = [
            _make_user_message("start"),
            _make_response_message("reply"),
            _make_user_message("end"),
        ]
        result = strip_orphaned_tool_messages(messages)
        assert result == messages

    def test_strips_orphan_but_keeps_valid_pair(self):
        messages = [
            _make_tool_return_request("orphan", "bad"),
            _make_user_message("hello"),
            _make_tool_call_response("good_tool"),
            _make_tool_return_request("good_tool", "ok"),
            _make_response_message("done"),
        ]
        result = strip_orphaned_tool_messages(messages)
        assert len(result) == 4
        assert result[0] == messages[1]
        assert result[1] == messages[2]
        assert result[2] == messages[3]
        assert result[3] == messages[4]

    def test_stripped_result_passes_validation(self):
        messages = [
            _make_user_message("hello"),
            _make_tool_return_request("orphan", "bad"),
            _make_tool_call_response("good_tool"),
            _make_tool_return_request("good_tool", "ok"),
        ]
        result = strip_orphaned_tool_messages(messages)
        assert validate_tool_pairs(result) is True


class TestPostCompactionValidation:
    def test_logs_warning_on_orphaned_tool_messages(self, caplog: Any):
        from src.simulation.workflows.agent_turn_workflow import (
            _deserialize_messages,
        )

        orphaned_messages = [
            _make_user_message("hello"),
            _make_tool_return_request("orphan_tool", "bad_result"),
            _make_user_message("world"),
        ]

        deserialized = _deserialize_messages(orphaned_messages)
        with caplog.at_level(logging.WARNING):
            valid = validate_tool_pairs(deserialized)
        assert valid is False
        assert "orphaned" in caplog.text.lower() or "tool" in caplog.text.lower()

    def test_repair_produces_valid_messages(self):
        from src.simulation.workflows.agent_turn_workflow import (
            _deserialize_messages,
            _serialize_messages,
        )

        orphaned_messages = [
            _make_user_message("hello"),
            _make_tool_return_request("orphan_tool", "bad_result"),
            _make_tool_call_response("good_tool"),
            _make_tool_return_request("good_tool", "ok"),
            _make_user_message("world"),
        ]

        deserialized = _deserialize_messages(orphaned_messages)
        assert validate_tool_pairs(deserialized) is False

        cleaned = strip_orphaned_tool_messages(deserialized)
        assert validate_tool_pairs(cleaned) is True

        reserialized = _serialize_messages(cleaned)
        assert len(reserialized) == 4

    def test_workflow_validates_after_compaction(self, caplog: Any):
        from src.simulation.workflows.agent_turn_workflow import (
            _deserialize_messages,
            _serialize_messages,
        )

        orphaned = [
            _make_user_message("start"),
            _make_tool_return_request("orphan", "stale"),
            _make_response_message("reply"),
        ]

        memory_result: dict[str, Any] = {
            "messages": orphaned,
            "was_compacted": True,
        }

        deserialized = _deserialize_messages(memory_result["messages"])
        with caplog.at_level(logging.WARNING):
            if not validate_tool_pairs(deserialized):
                cleaned = strip_orphaned_tool_messages(deserialized)
                memory_result["messages"] = _serialize_messages(cleaned)

        assert len(memory_result["messages"]) == 2
        re_deserialized = _deserialize_messages(memory_result["messages"])
        assert validate_tool_pairs(re_deserialized) is True
