"""Unit tests for BulkContentScanLog model.

Tests verify that required indexes exist on the model to match migration schema.
"""

from src.bulk_content_scan.models import BulkContentScanLog


class TestBulkContentScanLogModelIndexes:
    """Tests for BulkContentScanLog model index definitions."""

    def test_completed_at_has_index(self) -> None:
        """completed_at column should have index=True to match migration schema.

        The migration creates ix_bulk_content_scan_logs_completed_at index,
        so the model must have index=True on the completed_at column to
        prevent schema drift.
        """
        table = BulkContentScanLog.__table__
        index_names = [idx.name for idx in table.indexes]

        assert "ix_bulk_content_scan_logs_completed_at" in index_names, (
            f"Expected index 'ix_bulk_content_scan_logs_completed_at' on BulkContentScanLog model. "
            f"Found indexes: {index_names}. "
            "Add index=True to completed_at field in models.py to match migration."
        )

    def test_id_has_index(self) -> None:
        """id column should have index=True."""
        table = BulkContentScanLog.__table__
        index_names = [idx.name for idx in table.indexes]
        assert "ix_bulk_content_scan_logs_id" in index_names

    def test_community_server_id_has_index(self) -> None:
        """community_server_id column should have index=True."""
        table = BulkContentScanLog.__table__
        index_names = [idx.name for idx in table.indexes]
        assert "ix_bulk_content_scan_logs_community_server_id" in index_names

    def test_initiated_by_user_id_has_index(self) -> None:
        """initiated_by_user_id column should have index=True."""
        table = BulkContentScanLog.__table__
        index_names = [idx.name for idx in table.indexes]
        assert "ix_bulk_content_scan_logs_initiated_by_user_id" in index_names
