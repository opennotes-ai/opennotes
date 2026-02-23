from __future__ import annotations

from typing import Any

try:
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
    )

    _HAS_PYDANTIC_AI = True
except ImportError:
    _HAS_PYDANTIC_AI = False


def _extract_text(message: Any) -> str:
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
                if hasattr(part, "content") and isinstance(part.content, str):
                    texts.append(part.content)
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


def _is_system_message(message: Any) -> bool:
    if _HAS_PYDANTIC_AI and isinstance(message, ModelRequest):
        return any(isinstance(part, SystemPromptPart) for part in message.parts)

    if isinstance(message, dict):
        for part in message.get("parts", []):
            if isinstance(part, dict) and part.get("part_kind") == "system-prompt":
                return True

    return False
