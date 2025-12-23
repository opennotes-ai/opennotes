"""Tests for scan type definitions."""

from src.bulk_content_scan.scan_types import ALL_SCAN_TYPES, ScanType


class TestScanTypeEnum:
    """Tests for ScanType enum."""

    def test_openai_moderation_exists(self):
        """OPENAI_MODERATION scan type should exist."""
        assert hasattr(ScanType, "OPENAI_MODERATION")
        assert ScanType.OPENAI_MODERATION == "openai_moderation"

    def test_openai_moderation_in_all_scan_types(self):
        """OPENAI_MODERATION should be included in ALL_SCAN_TYPES."""
        assert ScanType.OPENAI_MODERATION in ALL_SCAN_TYPES

    def test_similarity_still_exists(self):
        """Existing SIMILARITY scan type should still work."""
        assert ScanType.SIMILARITY == "similarity"
