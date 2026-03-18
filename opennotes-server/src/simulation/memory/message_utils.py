from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
        ToolCallPart,
        ToolReturnPart,
    )

try:
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
        ToolCallPart,
        ToolReturnPart,
    )

    _HAS_PYDANTIC_AI = True
except ImportError:
    _HAS_PYDANTIC_AI = False

logger = logging.getLogger(__name__)


def extract_text(message: Any) -> str:
    if _HAS_PYDANTIC_AI:
        if isinstance(message, ModelRequest):
            texts: list[str] = []
            for part in message.parts:
                if hasattr(part, "content") and isinstance(part.content, str):
                    texts.append(part.content)
            return " ".join(texts)

        if isinstance(message, ModelResponse):
            texts = []
            for part in message.parts:
                content = getattr(part, "content", None)
                if isinstance(content, str):
                    texts.append(content)
            return " ".join(texts)

    if isinstance(message, dict):
        parts = message.get("parts", [])
        texts = []
        for part in parts:
            if isinstance(part, dict):
                content = part.get("content", "")
                if content:
                    texts.append(str(content))
        return " ".join(texts)

    return str(message)


def is_system_message(message: Any) -> bool:
    if _HAS_PYDANTIC_AI and isinstance(message, ModelRequest):
        return any(isinstance(part, SystemPromptPart) for part in message.parts)

    if isinstance(message, dict):
        for part in message.get("parts", []):
            if isinstance(part, dict) and part.get("part_kind") == "system-prompt":
                return True

    return False


def is_tool_call_message(message: Any) -> bool:
    if _HAS_PYDANTIC_AI and isinstance(message, ModelResponse):
        return any(isinstance(part, ToolCallPart) for part in message.parts)

    if isinstance(message, dict):
        for part in message.get("parts", []):
            if isinstance(part, dict) and part.get("part_kind") == "tool-call":
                return True

    return False


def is_tool_return_message(message: Any) -> bool:
    if _HAS_PYDANTIC_AI and isinstance(message, ModelRequest):
        return any(isinstance(part, ToolReturnPart) for part in message.parts)

    if isinstance(message, dict):
        for part in message.get("parts", []):
            if isinstance(part, dict) and part.get("part_kind") == "tool-return":
                return True

    return False


def group_tool_pairs(messages: list[Any]) -> list[list[Any]]:
    if not messages:
        return []

    groups: list[list[Any]] = []
    i = 0

    while i < len(messages):
        msg = messages[i]

        if is_tool_call_message(msg):
            group = [msg]
            i += 1
            while i < len(messages) and is_tool_return_message(messages[i]):
                group.append(messages[i])
                i += 1
            groups.append(group)
        else:
            groups.append([msg])
            i += 1

    return groups


def validate_tool_pairs(messages: list[Any]) -> bool:
    seen_tool_call = False
    valid = True

    for i, msg in enumerate(messages):
        if is_tool_call_message(msg):
            seen_tool_call = True
        elif is_tool_return_message(msg):
            if not seen_tool_call:
                logger.warning(
                    "Orphaned tool-return message at index %d with no preceding tool-call",
                    i,
                )
                valid = False
        else:
            seen_tool_call = False

    return valid
