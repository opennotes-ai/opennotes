"""Unit tests for BulkContentScanLog model.

Tests verify that required indexes and server_defaults exist on the model to match migration schema.
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


class TestBulkContentScanLogModelServerDefaults:
    """Tests for BulkContentScanLog model server_default definitions.

    These tests ensure the model uses server_default instead of Python default
    to match the migration schema and ensure defaults are applied at the database level.
    """

    def test_messages_scanned_has_server_default(self) -> None:
        """messages_scanned column should use server_default=text('0') to match migration.

        The migration defines: sa.Column("messages_scanned", sa.Integer(), server_default="0", nullable=False)
        so the model must use server_default=text("0"), not default=0.
        """
        table = BulkContentScanLog.__table__
        column = table.c.messages_scanned

        assert column.server_default is not None, (
            "messages_scanned should have server_default=text('0'), not default=0. "
            "Using server_default ensures the default is applied at the database level."
        )
        assert str(column.server_default.arg) == "0", (
            f"messages_scanned server_default should be '0', got '{column.server_default.arg}'"
        )

    def test_messages_flagged_has_server_default(self) -> None:
        """messages_flagged column should use server_default=text('0') to match migration.

        The migration defines: sa.Column("messages_flagged", sa.Integer(), server_default="0", nullable=False)
        so the model must use server_default=text("0"), not default=0.
        """
        table = BulkContentScanLog.__table__
        column = table.c.messages_flagged

        assert column.server_default is not None, (
            "messages_flagged should have server_default=text('0'), not default=0. "
            "Using server_default ensures the default is applied at the database level."
        )
        assert str(column.server_default.arg) == "0", (
            f"messages_flagged server_default should be '0', got '{column.server_default.arg}'"
        )
