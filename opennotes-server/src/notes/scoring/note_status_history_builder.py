"""
Note Status History DataFrame Builder for MFCoreScorer integration.

Transforms Note model objects into the DataFrame format expected by
Community Notes MFCoreScorer.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import pandas as pd


def _datetime_to_millis(dt: datetime) -> int:
    """Convert datetime to milliseconds since epoch."""
    return int(dt.timestamp() * 1000)


def _to_string(value: Any) -> str:
    """Convert value to string, handling UUIDs."""
    if isinstance(value, UUID):
        return str(value)
    return str(value)


class NoteStatusHistoryBuilder:
    """
    Builder for converting Note model objects to Community Notes noteStatusHistory DataFrame.

    The Community Notes MFCoreScorer expects a DataFrame with specific columns.
    This builder transforms our Note model into the expected format.
    """

    def build(self, notes: list[dict[str, Any]]) -> pd.DataFrame:
        """
        Build a note status history DataFrame from note data.

        Args:
            notes: List of note data dicts with keys:
                - id: UUID of the note
                - author_participant_id: String identifier of the author
                - classification: NOT_MISLEADING or MISINFORMED_OR_POTENTIALLY_MISLEADING
                - status: NEEDS_MORE_RATINGS, CURRENTLY_RATED_HELPFUL, or CURRENTLY_RATED_NOT_HELPFUL
                - created_at: datetime when the note was created

        Returns:
            DataFrame with Community Notes note status history columns including:
                - noteId, noteAuthorParticipantId, createdAtMillis
                - classification, currentStatus, lockedStatus
        """
        if not notes:
            return self._create_empty_dataframe()

        rows = []
        for note in notes:
            row = self._transform_note(note)
            rows.append(row)

        return pd.DataFrame(rows)

    def _create_empty_dataframe(self) -> pd.DataFrame:
        """Create an empty DataFrame with the required columns."""
        columns = self._get_all_columns()
        return pd.DataFrame(columns=columns)

    def _get_all_columns(self) -> list[str]:
        """Get all required column names."""
        return [
            "noteId",
            "noteAuthorParticipantId",
            "createdAtMillis",
            "classification",
            "currentStatus",
            "lockedStatus",
            "timestampMillisOfLatestNonNMRStatus",
        ]

    def _transform_note(self, note: dict[str, Any]) -> dict[str, Any]:
        """Transform a single note to Community Notes format."""
        status = note["status"]
        created_at_millis = _datetime_to_millis(note["created_at"])

        timestamp_of_latest_non_nmr = float("nan")
        if status != "NEEDS_MORE_RATINGS":
            timestamp_of_latest_non_nmr = float(created_at_millis)

        return {
            "noteId": _to_string(note["id"]),
            "noteAuthorParticipantId": note["author_participant_id"],
            "createdAtMillis": created_at_millis,
            "classification": note["classification"],
            "currentStatus": status,
            "lockedStatus": None,
            "timestampMillisOfLatestNonNMRStatus": timestamp_of_latest_non_nmr,
        }
