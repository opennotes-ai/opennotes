"""Standalone capability functions for bulk content scanning.

Each capability accepts dependencies as parameters and returns typed results.
They are independently importable without BulkContentScanService.
"""

from src.bulk_content_scan.capabilities.flashpoint import detect_flashpoint
from src.bulk_content_scan.capabilities.moderation import check_content_moderation
from src.bulk_content_scan.capabilities.similarity import search_similar_claims

__all__ = [
    "check_content_moderation",
    "detect_flashpoint",
    "search_similar_claims",
]
