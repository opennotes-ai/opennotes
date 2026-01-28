"""
Ratings DataFrame Builder for MFCoreScorer integration.

Transforms Rating model objects into the DataFrame format expected by
Community Notes MFCoreScorer.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import pandas as pd

HELPFULNESS_LEVEL_MAP: dict[str, float] = {
    "HELPFUL": 1.0,
    "SOMEWHAT_HELPFUL": 0.5,
    "NOT_HELPFUL": 0.0,
}

HELPFUL_TAG_COLUMNS = [
    "helpfulOther",
    "helpfulInformative",
    "helpfulClear",
    "helpfulEmpathetic",
    "helpfulGoodSources",
    "helpfulUniqueContext",
    "helpfulAddressesClaim",
    "helpfulImportantContext",
    "helpfulUnbiasedLanguage",
]

NOT_HELPFUL_TAG_COLUMNS = [
    "notHelpfulIncorrect",
    "notHelpfulOther",
    "notHelpfulSpamHarassmentOrAbuse",
    "notHelpfulArgumentativeOrBiased",
    "notHelpfulHardToUnderstand",
    "notHelpfulNoteNotNeeded",
    "notHelpfulSourcesMissingOrUnreliable",
    "notHelpfulIrrelevantSources",
    "notHelpfulOpinionSpeculationOrBias",
    "notHelpfulMissingKeyPoints",
    "notHelpfulOutdated",
    "notHelpfulOffTopic",
    "notHelpfulOpinionSpeculation",
]

ALL_TAG_COLUMNS = HELPFUL_TAG_COLUMNS + NOT_HELPFUL_TAG_COLUMNS

# Rating source values for ratingSourceBucketed column
RATING_SOURCE_DEFAULT = "DEFAULT"
RATING_SOURCE_POPULATION_SAMPLED = "POPULATION_SAMPLED"


def _datetime_to_millis(dt: datetime) -> int:
    """Convert datetime to milliseconds since epoch."""
    return int(dt.timestamp() * 1000)


def _to_string(value: Any) -> str:
    """Convert value to string, handling UUIDs."""
    if isinstance(value, UUID):
        return str(value)
    return str(value)


class RatingsDataFrameBuilder:
    """
    Builder for converting Rating model objects to Community Notes ratings DataFrame.

    The Community Notes MFCoreScorer expects a DataFrame with specific columns.
    This builder transforms our simplified Rating model (which lacks tag columns)
    into the expected format, defaulting missing tags to 0.
    """

    def build(self, ratings: list[dict[str, Any]]) -> pd.DataFrame:
        """
        Build a ratings DataFrame from rating data.

        Args:
            ratings: List of rating data dicts with keys:
                - id: UUID of the rating
                - note_id: UUID of the note being rated
                - rater_id: UUID of the rater's user profile
                - helpfulness_level: HELPFUL, SOMEWHAT_HELPFUL, or NOT_HELPFUL
                - created_at: datetime when the rating was created

        Returns:
            DataFrame with Community Notes rating columns including:
                - noteId, raterParticipantId, createdAtMillis
                - helpfulNum, helpfulnessLevel
                - All tag columns (defaulted to 0)
        """
        if not ratings:
            return self._create_empty_dataframe()

        rows = []
        for rating in ratings:
            row = self._transform_rating(rating)
            rows.append(row)

        return pd.DataFrame(rows)

    def _create_empty_dataframe(self) -> pd.DataFrame:
        """Create an empty DataFrame with the required columns."""
        columns = self._get_all_columns()
        return pd.DataFrame(columns=columns)

    def _get_all_columns(self) -> list[str]:
        """Get all required column names."""
        base_columns = [
            "noteId",
            "raterParticipantId",
            "createdAtMillis",
            "helpfulNum",
            "helpfulnessLevel",
            "ratingSourceBucketed",
            "highVolumeRater",
            "correlatedRater",
        ]
        return base_columns + ALL_TAG_COLUMNS

    def _transform_rating(self, rating: dict[str, Any]) -> dict[str, Any]:
        """Transform a single rating to Community Notes format."""
        helpfulness_level = rating["helpfulness_level"]
        helpful_num = HELPFULNESS_LEVEL_MAP.get(helpfulness_level, 0.0)

        row: dict[str, Any] = {
            "noteId": _to_string(rating["note_id"]),
            "raterParticipantId": _to_string(rating["rater_id"]),
            "createdAtMillis": _datetime_to_millis(rating["created_at"]),
            "helpfulNum": helpful_num,
            "helpfulnessLevel": helpfulness_level,
            "ratingSourceBucketed": RATING_SOURCE_DEFAULT,
            "highVolumeRater": 0,
            "correlatedRater": 0,
        }

        for tag in ALL_TAG_COLUMNS:
            row[tag] = 0

        return row
