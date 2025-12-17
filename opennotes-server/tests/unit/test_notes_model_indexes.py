"""Unit tests for notes model indexes.

Tests verify that required indexes exist on SQLAlchemy models
for query performance optimization.
"""

from src.notes.models import Request


class TestRequestModelIndexes:
    """Tests for Request model index definitions."""

    def test_composite_index_note_id_status_exists(self) -> None:
        """Request model should have composite index on note_id + status.

        This index optimizes the common query pattern of filtering requests
        by note_id and status together.
        """
        table_args = Request.__table_args__
        index_names = [idx.name for idx in table_args if hasattr(idx, "name") and idx.name]

        assert "idx_requests_note_status" in index_names, (
            f"Expected composite index 'idx_requests_note_status' on Request model. "
            f"Found indexes: {index_names}"
        )

    def test_composite_index_note_id_status_has_correct_columns(self) -> None:
        """The idx_requests_note_status index should cover note_id and status columns."""
        table_args = Request.__table_args__
        target_index = None

        for idx in table_args:
            if hasattr(idx, "name") and idx.name == "idx_requests_note_status":
                target_index = idx
                break

        assert target_index is not None, "Index idx_requests_note_status not found"

        column_names = [col.name for col in target_index.columns]
        assert column_names == ["note_id", "status"], (
            f"Expected index columns ['note_id', 'status'], got {column_names}"
        )
