"""Shared comment-platform dispatch types."""

from __future__ import annotations

from typing import TypeAlias

from src.coral import CoralSignal
from src.viafoura import ViafouraSignal

PlatformSignal: TypeAlias = CoralSignal | ViafouraSignal

__all__ = ["PlatformSignal"]
