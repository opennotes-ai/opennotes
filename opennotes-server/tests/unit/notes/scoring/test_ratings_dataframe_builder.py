"""
Tests for RatingsDataFrameBuilder.

TDD: Write failing tests first, then implement.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pandas as pd
import pytest


class TestRatingsDataFrameBuilder:
    """Tests for RatingsDataFrameBuilder (AC #1)."""

    def test_can_import_ratings_dataframe_builder(self):
        """RatingsDataFrameBuilder can be imported."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        assert RatingsDataFrameBuilder is not None

    def test_builder_can_be_instantiated(self):
        """RatingsDataFrameBuilder can be instantiated."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        assert builder is not None

    def test_build_returns_dataframe(self):
        """build() returns a pandas DataFrame."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([])

        assert isinstance(result, pd.DataFrame)

    def test_build_with_empty_list_returns_empty_dataframe_with_columns(self):
        """build() with empty list returns DataFrame with required columns."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([])

        assert len(result) == 0
        assert "noteId" in result.columns
        assert "raterParticipantId" in result.columns
        assert "createdAtMillis" in result.columns
        assert "helpfulNum" in result.columns
        assert "helpfulnessLevel" in result.columns

    def test_build_includes_helpful_tag_columns(self):
        """build() includes all helpful tag columns defaulted to 0."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([])

        helpful_tags = [
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
        for tag in helpful_tags:
            assert tag in result.columns, f"Missing helpful tag column: {tag}"

    def test_build_includes_not_helpful_tag_columns(self):
        """build() includes all not helpful tag columns defaulted to 0."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([])

        not_helpful_tags = [
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
        for tag in not_helpful_tags:
            assert tag in result.columns, f"Missing not helpful tag column: {tag}"


class TestRatingsDataFrameBuilderWithRatingData:
    """Tests for RatingsDataFrameBuilder with rating data (AC #1)."""

    @pytest.fixture
    def mock_rating_data(self):
        """Create mock rating data dict (simulating Rating model attributes)."""
        return {
            "id": uuid4(),
            "note_id": uuid4(),
            "rater_id": "discord_user_123",
            "helpfulness_level": "HELPFUL",
            "created_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        }

    def test_build_with_single_rating(self, mock_rating_data):
        """build() correctly transforms a single rating."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([mock_rating_data])

        assert len(result) == 1
        assert result.iloc[0]["raterParticipantId"] == "discord_user_123"

    def test_build_converts_note_id_to_string(self, mock_rating_data):
        """build() converts UUID note_id to string."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([mock_rating_data])

        note_id_value = result.iloc[0]["noteId"]
        assert isinstance(note_id_value, str)
        assert note_id_value == str(mock_rating_data["note_id"])

    def test_build_converts_created_at_to_millis(self, mock_rating_data):
        """build() converts created_at datetime to milliseconds."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([mock_rating_data])

        created_at_millis = result.iloc[0]["createdAtMillis"]
        expected_millis = int(mock_rating_data["created_at"].timestamp() * 1000)
        assert created_at_millis == expected_millis

    def test_build_maps_helpful_to_helpful_num_1(self, mock_rating_data):
        """build() maps HELPFUL to helpfulNum=1.0."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        mock_rating_data["helpfulness_level"] = "HELPFUL"

        builder = RatingsDataFrameBuilder()
        result = builder.build([mock_rating_data])

        assert result.iloc[0]["helpfulNum"] == 1.0

    def test_build_maps_somewhat_helpful_to_helpful_num_05(self, mock_rating_data):
        """build() maps SOMEWHAT_HELPFUL to helpfulNum=0.5."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        mock_rating_data["helpfulness_level"] = "SOMEWHAT_HELPFUL"

        builder = RatingsDataFrameBuilder()
        result = builder.build([mock_rating_data])

        assert result.iloc[0]["helpfulNum"] == 0.5

    def test_build_maps_not_helpful_to_helpful_num_0(self, mock_rating_data):
        """build() maps NOT_HELPFUL to helpfulNum=0.0."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        mock_rating_data["helpfulness_level"] = "NOT_HELPFUL"

        builder = RatingsDataFrameBuilder()
        result = builder.build([mock_rating_data])

        assert result.iloc[0]["helpfulNum"] == 0.0

    def test_build_sets_helpfulness_level(self, mock_rating_data):
        """build() sets helpfulnessLevel column."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([mock_rating_data])

        assert result.iloc[0]["helpfulnessLevel"] == "HELPFUL"

    def test_build_defaults_tag_columns_to_zero(self, mock_rating_data):
        """build() defaults all tag columns to 0 (AC #4)."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        builder = RatingsDataFrameBuilder()
        result = builder.build([mock_rating_data])

        assert result.iloc[0]["notHelpfulIncorrect"] == 0
        assert result.iloc[0]["helpfulOther"] == 0
        assert result.iloc[0]["notHelpfulSpamHarassmentOrAbuse"] == 0


class TestRatingsDataFrameBuilderMultipleRatings:
    """Tests for RatingsDataFrameBuilder with multiple ratings."""

    def test_build_with_multiple_ratings(self):
        """build() correctly transforms multiple ratings."""
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        ratings = [
            {
                "id": uuid4(),
                "note_id": uuid4(),
                "rater_id": "user_1",
                "helpfulness_level": "HELPFUL",
                "created_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            },
            {
                "id": uuid4(),
                "note_id": uuid4(),
                "rater_id": "user_2",
                "helpfulness_level": "NOT_HELPFUL",
                "created_at": datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC),
            },
        ]

        builder = RatingsDataFrameBuilder()
        result = builder.build(ratings)

        assert len(result) == 2
        assert result.iloc[0]["raterParticipantId"] == "user_1"
        assert result.iloc[0]["helpfulNum"] == 1.0
        assert result.iloc[1]["raterParticipantId"] == "user_2"
        assert result.iloc[1]["helpfulNum"] == 0.0
