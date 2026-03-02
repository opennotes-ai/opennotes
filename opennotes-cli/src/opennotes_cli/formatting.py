from __future__ import annotations


def truncate_uuid(uuid_str: str, prefix_len: int = 3, tail_len: int = 9) -> str:
    if len(uuid_str) <= prefix_len + tail_len + 1:
        return uuid_str
    return f"{uuid_str[:prefix_len]}\u2026{uuid_str[-tail_len:]}"
