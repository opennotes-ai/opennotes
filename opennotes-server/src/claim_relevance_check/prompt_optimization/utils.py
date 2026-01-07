"""Shared utilities for prompt optimization scripts."""

import os


def setup_openai_environment() -> str:
    """Set up OpenAI environment for litellm.

    Cleans the API key and removes any OPENAI_API_BASE override
    (e.g., from VSCode/GitHub Copilot) to ensure requests go to OpenAI.

    Returns:
        The cleaned API key

    Raises:
        ValueError: If OPENAI_API_KEY environment variable is not set
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    api_key = api_key.strip().strip("'\"")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

    os.environ["OPENAI_API_KEY"] = api_key

    if "OPENAI_API_BASE" in os.environ:
        del os.environ["OPENAI_API_BASE"]

    return api_key


def truncate_utf8_safe(text: str, max_chars: int, suffix: str = "...") -> str:
    """Truncate a string safely at character boundaries.

    This function truncates at character (not byte) boundaries,
    which is safe for UTF-8 strings in Python 3 since strings
    are sequences of Unicode code points.

    Args:
        text: The string to truncate
        max_chars: Maximum number of characters (excluding suffix)
        suffix: String to append if truncation occurs

    Returns:
        Truncated string with suffix if it was truncated
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + suffix
