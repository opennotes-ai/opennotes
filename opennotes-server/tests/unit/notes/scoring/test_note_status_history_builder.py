"""
Tests for NoteStatusHistoryBuilder.

TDD: Write failing tests first, then implement.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pandas as pd
import pytest


class TestNoteStatusHistoryBuilder:
    """Tests for NoteStatusHistoryBuilder (AC #2)."""

    def test_can_import_note_status_history_builder(self):
        """NoteStatusHistoryBuilder can be imported."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        assert NoteStatusHistoryBuilder is not None

    def test_builder_can_be_instantiated(self):
        """NoteStatusHistoryBuilder can be instantiated."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        assert builder is not None

    def test_build_returns_dataframe(self):
        """build() returns a pandas DataFrame."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        result = builder.build([])

        assert isinstance(result, pd.DataFrame)

    def test_build_with_empty_list_returns_empty_dataframe_with_columns(self):
        """build() with empty list returns DataFrame with required columns."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        result = builder.build([])

        assert len(result) == 0
        assert "noteId" in result.columns
        assert "noteAuthorParticipantId" in result.columns
        assert "createdAtMillis" in result.columns
        assert "classification" in result.columns
        assert "currentStatus" in result.columns
        assert "lockedStatus" in result.columns


class TestNoteStatusHistoryBuilderWithNoteData:
    """Tests for NoteStatusHistoryBuilder with note data (AC #2)."""

    @pytest.fixture
    def mock_note_data(self):
        """Create mock note data dict (simulating Note model attributes)."""
        return {
            "id": uuid4(),
            "author_id": "discord_author_123",
            "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
            "status": "NEEDS_MORE_RATINGS",
            "created_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        }

    def test_build_with_single_note(self, mock_note_data):
        """build() correctly transforms a single note."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        assert len(result) == 1
        assert result.iloc[0]["noteAuthorParticipantId"] == "discord_author_123"

    def test_build_converts_note_id_to_string(self, mock_note_data):
        """build() converts UUID note id to string."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        note_id_value = result.iloc[0]["noteId"]
        assert isinstance(note_id_value, str)
        assert note_id_value == str(mock_note_data["id"])

    def test_build_converts_created_at_to_millis(self, mock_note_data):
        """build() converts created_at datetime to milliseconds."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        created_at_millis = result.iloc[0]["createdAtMillis"]
        expected_millis = int(mock_note_data["created_at"].timestamp() * 1000)
        assert created_at_millis == expected_millis

    def test_build_sets_classification(self, mock_note_data):
        """build() sets classification column."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        assert result.iloc[0]["classification"] == "MISINFORMED_OR_POTENTIALLY_MISLEADING"

    def test_build_maps_status_to_current_status(self, mock_note_data):
        """build() maps status to currentStatus column."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        assert result.iloc[0]["currentStatus"] == "NEEDS_MORE_RATINGS"

    def test_build_defaults_locked_status_to_none(self, mock_note_data):
        """build() defaults lockedStatus to None (not locked)."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        assert pd.isna(result.iloc[0]["lockedStatus"]) or result.iloc[0]["lockedStatus"] is None

    def test_build_with_currently_rated_helpful_status(self, mock_note_data):
        """build() correctly handles CURRENTLY_RATED_HELPFUL status."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        mock_note_data["status"] = "CURRENTLY_RATED_HELPFUL"

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        assert result.iloc[0]["currentStatus"] == "CURRENTLY_RATED_HELPFUL"

    def test_build_with_currently_rated_not_helpful_status(self, mock_note_data):
        """build() correctly handles CURRENTLY_RATED_NOT_HELPFUL status."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        mock_note_data["status"] = "CURRENTLY_RATED_NOT_HELPFUL"

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        assert result.iloc[0]["currentStatus"] == "CURRENTLY_RATED_NOT_HELPFUL"

    def test_build_with_not_misleading_classification(self, mock_note_data):
        """build() correctly handles NOT_MISLEADING classification."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        mock_note_data["classification"] = "NOT_MISLEADING"

        builder = NoteStatusHistoryBuilder()
        result = builder.build([mock_note_data])

        assert result.iloc[0]["classification"] == "NOT_MISLEADING"


class TestNoteStatusHistoryBuilderMultipleNotes:
    """Tests for NoteStatusHistoryBuilder with multiple notes."""

    def test_build_with_multiple_notes(self):
        """build() correctly transforms multiple notes."""
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        notes = [
            {
                "id": uuid4(),
                "author_id": "author_1",
                "classification": "NOT_MISLEADING",
                "status": "CURRENTLY_RATED_HELPFUL",
                "created_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            },
            {
                "id": uuid4(),
                "author_id": "author_2",
                "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
                "created_at": datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC),
            },
        ]

        builder = NoteStatusHistoryBuilder()
        result = builder.build(notes)

        assert len(result) == 2
        assert result.iloc[0]["noteAuthorParticipantId"] == "author_1"
        assert result.iloc[0]["currentStatus"] == "CURRENTLY_RATED_HELPFUL"
        assert result.iloc[1]["noteAuthorParticipantId"] == "author_2"
        assert result.iloc[1]["currentStatus"] == "NEEDS_MORE_RATINGS"
