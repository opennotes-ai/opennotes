"""Secure string handling for API keys to prevent memory leakage.

Python strings are immutable and may be interned, which means:
1. Overwriting a string variable doesn't clear the original from memory
2. The original plaintext may persist until garbage collection

This module provides SecureString which uses a mutable bytearray for storage,
allowing us to explicitly zero out the memory when done.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class SecureString:
    """
    A secure string wrapper that stores sensitive data in a mutable bytearray.

    Unlike Python strings which are immutable and may be interned,
    SecureString allows explicit zeroing of memory when the sensitive
    data is no longer needed.

    Usage:
        with SecureString("my-secret-api-key") as ss:
            api_key = ss.get_value()
            # use api_key...
        # Memory is automatically cleared after the with block

    Or manually:
        ss = SecureString("my-secret")
        try:
            # use ss.get_value()
        finally:
            ss.clear()
    """

    __slots__ = ("_buffer", "_cleared")

    def __init__(self, value: str) -> None:
        """
        Initialize SecureString with the given value.

        Args:
            value: The sensitive string to store securely
        """
        self._buffer = bytearray(value.encode("utf-8"))
        self._cleared = False

    def get_value(self) -> str:
        """
        Get the stored string value.

        Returns:
            The stored string, or empty string if cleared
        """
        if self._cleared:
            return ""
        return self._buffer.decode("utf-8")

    def clear(self) -> None:
        """
        Securely clear the stored value by zeroing the buffer.

        This overwrites the buffer contents with zeros before
        clearing, reducing the risk of the sensitive data
        remaining in memory.
        """
        if self._cleared:
            return

        for i in range(len(self._buffer)):
            self._buffer[i] = 0

        self._buffer.clear()
        self._cleared = True

    def __len__(self) -> int:
        """Return the length of the stored string."""
        if self._cleared:
            return 0
        return len(self._buffer)

    def __enter__(self) -> SecureString:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        """Context manager exit - always clears the buffer."""
        self.clear()

    def __del__(self) -> None:
        """Destructor - ensure buffer is cleared."""
        if not self._cleared:
            self.clear()


@contextmanager
def secure_api_key_context(api_key: str) -> Generator[str, None, None]:
    """
    Context manager for securely handling API keys.

    Creates a SecureString internally and yields the key value.
    The internal buffer is cleared when the context exits.

    Usage:
        with secure_api_key_context("sk-my-api-key") as key:
            provider = create_provider(key)
            # use provider...
        # Internal secure storage is cleared

    Args:
        api_key: The API key to handle securely

    Yields:
        The API key string value
    """
    ss = SecureString(api_key)
    try:
        yield ss.get_value()
    finally:
        ss.clear()
