"""Scan type definitions for bulk content scanning."""

from enum import StrEnum


class ScanType(StrEnum):
    """Types of scans that can be performed on messages."""

    SIMILARITY = "similarity"
    OPENAI_MODERATION = "openai_moderation"


DEFAULT_SCAN_TYPES: tuple[ScanType, ...] = (ScanType.SIMILARITY,)
ALL_SCAN_TYPES: tuple[ScanType, ...] = tuple(ScanType)
