"""Public API for Coral HTML signature detection."""

from __future__ import annotations

from .detector import CoralSignal, detect_coral

__all__ = [
    "CoralSignal",
    "detect_coral",
]
