from __future__ import annotations

import copy

from src.simulation.scripts.repair_agent_memories import (
    is_corrupted_history,
    repair_histories,
    repair_history,
)


class TestIsCorruptedHistory:
    def test_identifies_corrupted_history_with_orphaned_tool_return(self):
        history = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
            {
                "kind": "request",
                "parts": [
                    {
                        "part_kind": "tool-return",
                        "tool_name": "t",
                        "content": "r",
                        "tool_call_id": "c1",
                    }
                ],
            },
        ]
        assert is_corrupted_history(history) is True

    def test_clean_history_not_corrupted(self):
        history = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
            {"kind": "response", "parts": [{"part_kind": "text", "content": "hello"}]},
        ]
        assert is_corrupted_history(history) is False

    def test_empty_history_not_corrupted(self):
        assert is_corrupted_history([]) is False

    def test_valid_tool_call_then_return_not_corrupted(self):
        history = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
            {
                "kind": "response",
                "parts": [
                    {
                        "part_kind": "tool-call",
                        "tool_name": "t",
                        "args": {},
                        "tool_call_id": "c1",
                    }
                ],
            },
            {
                "kind": "request",
                "parts": [
                    {
                        "part_kind": "tool-return",
                        "tool_name": "t",
                        "content": "r",
                        "tool_call_id": "c1",
                    }
                ],
            },
            {"kind": "response", "parts": [{"part_kind": "text", "content": "done"}]},
        ]
        assert is_corrupted_history(history) is False


class TestRepairHistory:
    def test_repair_strips_orphaned_tool_return(self):
        history = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
            {
                "kind": "request",
                "parts": [
                    {
                        "part_kind": "tool-return",
                        "tool_name": "t",
                        "content": "r",
                        "tool_call_id": "c1",
                    }
                ],
            },
            {"kind": "response", "parts": [{"part_kind": "text", "content": "hello"}]},
        ]
        repaired = repair_history(history)
        assert len(repaired) == 2
        assert repaired[0]["parts"][0]["part_kind"] == "user-prompt"
        assert repaired[1]["parts"][0]["part_kind"] == "text"

    def test_repair_preserves_valid_tool_pairs(self):
        history = [
            {
                "kind": "response",
                "parts": [
                    {
                        "part_kind": "tool-call",
                        "tool_name": "t",
                        "args": {},
                        "tool_call_id": "c1",
                    }
                ],
            },
            {
                "kind": "request",
                "parts": [
                    {
                        "part_kind": "tool-return",
                        "tool_name": "t",
                        "content": "r",
                        "tool_call_id": "c1",
                    }
                ],
            },
        ]
        repaired = repair_history(history)
        assert len(repaired) == 2

    def test_repair_returns_new_list(self):
        history = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
        ]
        repaired = repair_history(history)
        assert repaired is not history


class TestRepairHistories:
    def test_reports_stats(self):
        histories = [
            [
                {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
            ],
            [
                {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
                {
                    "kind": "request",
                    "parts": [
                        {
                            "part_kind": "tool-return",
                            "tool_name": "t",
                            "content": "r",
                            "tool_call_id": "c1",
                        }
                    ],
                },
            ],
        ]
        stats = repair_histories(histories, dry_run=False)
        assert stats["scanned"] == 2
        assert stats["corrupted"] == 1
        assert stats["messages_stripped"] == 1

    def test_dry_run_does_not_modify(self):
        history = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
            {
                "kind": "request",
                "parts": [
                    {
                        "part_kind": "tool-return",
                        "tool_name": "t",
                        "content": "r",
                        "tool_call_id": "c1",
                    }
                ],
            },
        ]
        original = copy.deepcopy(history)
        stats = repair_histories([history], dry_run=True)
        assert stats["corrupted"] == 1
        assert stats["messages_stripped"] == 1
        assert history == original

    def test_dry_run_false_modifies_in_place(self):
        history = [
            {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
            {
                "kind": "request",
                "parts": [
                    {
                        "part_kind": "tool-return",
                        "tool_name": "t",
                        "content": "r",
                        "tool_call_id": "c1",
                    }
                ],
            },
        ]
        stats = repair_histories([history], dry_run=False)
        assert stats["corrupted"] == 1
        assert len(history) == 1

    def test_multiple_corrupted_histories(self):
        histories = [
            [
                {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "a"}]},
                {
                    "kind": "request",
                    "parts": [
                        {
                            "part_kind": "tool-return",
                            "tool_name": "t1",
                            "content": "r1",
                            "tool_call_id": "c1",
                        }
                    ],
                },
                {
                    "kind": "request",
                    "parts": [
                        {
                            "part_kind": "tool-return",
                            "tool_name": "t2",
                            "content": "r2",
                            "tool_call_id": "c2",
                        }
                    ],
                },
            ],
            [
                {
                    "kind": "request",
                    "parts": [
                        {
                            "part_kind": "tool-return",
                            "tool_name": "t3",
                            "content": "r3",
                            "tool_call_id": "c3",
                        }
                    ],
                },
            ],
        ]
        stats = repair_histories(histories, dry_run=False)
        assert stats["scanned"] == 2
        assert stats["corrupted"] == 2
        assert stats["messages_stripped"] == 3

    def test_no_corrupted_histories(self):
        histories = [
            [
                {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "hi"}]},
                {"kind": "response", "parts": [{"part_kind": "text", "content": "hello"}]},
            ],
        ]
        stats = repair_histories(histories, dry_run=False)
        assert stats["scanned"] == 1
        assert stats["corrupted"] == 0
        assert stats["messages_stripped"] == 0
