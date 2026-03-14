from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pyarrow as pa


class TestTransformRatings:
    def test_transforms_ratings_table_to_dataframe(self):
        ratings = pa.table(
            {
                "id": ["r1", "r2"],
                "note_id": ["n1", "n1"],
                "rater_id": ["u1", "u2"],
                "helpfulness_level": ["HELPFUL", "NOT_HELPFUL"],
                "created_at": [
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                ],
            }
        )
        notes = pa.table(
            {
                "id": ["n1"],
                "author_id": ["u3"],
                "classification": ["NOT_MISLEADING"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [datetime(2025, 1, 1, tzinfo=UTC)],
            }
        )
        participants = pa.array(["u1", "u2", "u3"])

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, _, _ = transform_community_data(ratings, notes, participants)

        assert isinstance(ratings_df, pd.DataFrame)
        assert len(ratings_df) == 2
        assert "noteId" in ratings_df.columns
        assert "raterParticipantId" in ratings_df.columns
        assert "createdAtMillis" in ratings_df.columns
        assert "helpfulNum" in ratings_df.columns

    def test_ratings_column_renames(self):
        ratings = pa.table(
            {
                "id": ["r1"],
                "note_id": ["n1"],
                "rater_id": ["u1"],
                "helpfulness_level": ["HELPFUL"],
                "created_at": [datetime(2025, 1, 1, tzinfo=UTC)],
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1"])

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, _, _ = transform_community_data(ratings, notes, participants)

        assert ratings_df["noteId"].iloc[0] == "n1"
        assert ratings_df["raterParticipantId"].iloc[0] == "u1"

    def test_ratings_helpfulness_mapping(self):
        ratings = pa.table(
            {
                "id": ["r1", "r2", "r3"],
                "note_id": ["n1", "n1", "n1"],
                "rater_id": ["u1", "u2", "u3"],
                "helpfulness_level": ["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"],
                "created_at": [
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 1, tzinfo=UTC),
                ],
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1", "u2", "u3"])

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, _, _ = transform_community_data(ratings, notes, participants)

        assert ratings_df["helpfulNum"].iloc[0] == 1.0
        assert ratings_df["helpfulNum"].iloc[1] == 0.5
        assert ratings_df["helpfulNum"].iloc[2] == 0.0

    def test_ratings_created_at_millis(self):
        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        ratings = pa.table(
            {
                "id": ["r1"],
                "note_id": ["n1"],
                "rater_id": ["u1"],
                "helpfulness_level": ["HELPFUL"],
                "created_at": [dt],
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1"])

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, _, _ = transform_community_data(ratings, notes, participants)

        expected_millis = int(dt.timestamp() * 1000)
        assert ratings_df["createdAtMillis"].iloc[0] == expected_millis

    def test_ratings_default_tag_columns(self):
        ratings = pa.table(
            {
                "id": ["r1"],
                "note_id": ["n1"],
                "rater_id": ["u1"],
                "helpfulness_level": ["HELPFUL"],
                "created_at": [datetime(2025, 1, 1, tzinfo=UTC)],
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1"])

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, _, _ = transform_community_data(ratings, notes, participants)

        tag_cols = [
            "helpfulOther",
            "helpfulInformative",
            "helpfulClear",
            "notHelpfulIncorrect",
            "notHelpfulOther",
        ]
        for col in tag_cols:
            assert col in ratings_df.columns
            assert ratings_df[col].iloc[0] == 0

    def test_ratings_default_metadata_columns(self):
        ratings = pa.table(
            {
                "id": ["r1"],
                "note_id": ["n1"],
                "rater_id": ["u1"],
                "helpfulness_level": ["HELPFUL"],
                "created_at": [datetime(2025, 1, 1, tzinfo=UTC)],
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1"])

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, _, _ = transform_community_data(ratings, notes, participants)

        assert ratings_df["ratingSourceBucketed"].iloc[0] == "DEFAULT"
        assert ratings_df["highVolumeRater"].iloc[0] == 0
        assert ratings_df["correlatedRater"].iloc[0] == 0

    def test_empty_ratings_table(self):
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array([], type=pa.string())

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, notes_df, enrollment_df = transform_community_data(ratings, notes, participants)

        assert len(ratings_df) == 0
        assert len(notes_df) == 0
        assert len(enrollment_df) == 0


class TestTransformNotes:
    def test_transforms_notes_table_to_dataframe(self):
        notes = pa.table(
            {
                "id": ["n1", "n2"],
                "author_id": ["u1", "u2"],
                "classification": ["NOT_MISLEADING", "MISINFORMED_OR_POTENTIALLY_MISLEADING"],
                "status": ["NEEDS_MORE_RATINGS", "CURRENTLY_RATED_HELPFUL"],
                "created_at": [
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                ],
            }
        )
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1", "u2"])

        from src.notes.scoring.data_transforms import transform_community_data

        _, notes_df, _ = transform_community_data(ratings, notes, participants)

        assert isinstance(notes_df, pd.DataFrame)
        assert len(notes_df) == 2
        assert "noteId" in notes_df.columns
        assert "noteAuthorParticipantId" in notes_df.columns
        assert "createdAtMillis" in notes_df.columns
        assert "currentStatus" in notes_df.columns
        assert "lockedStatus" in notes_df.columns

    def test_notes_column_renames(self):
        notes = pa.table(
            {
                "id": ["n1"],
                "author_id": ["u1"],
                "classification": ["NOT_MISLEADING"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [datetime(2025, 1, 1, tzinfo=UTC)],
            }
        )
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1"])

        from src.notes.scoring.data_transforms import transform_community_data

        _, notes_df, _ = transform_community_data(ratings, notes, participants)

        assert notes_df["noteId"].iloc[0] == "n1"
        assert notes_df["noteAuthorParticipantId"].iloc[0] == "u1"
        assert notes_df["currentStatus"].iloc[0] == "NEEDS_MORE_RATINGS"

    def test_notes_timestamp_non_nmr_status(self):
        notes = pa.table(
            {
                "id": ["n1", "n2"],
                "author_id": ["u1", "u2"],
                "classification": ["NOT_MISLEADING", "NOT_MISLEADING"],
                "status": ["NEEDS_MORE_RATINGS", "CURRENTLY_RATED_HELPFUL"],
                "created_at": [
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                ],
            }
        )
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1", "u2"])

        from src.notes.scoring.data_transforms import transform_community_data

        _, notes_df, _ = transform_community_data(ratings, notes, participants)

        assert np.isnan(notes_df["timestampMillisOfLatestNonNMRStatus"].iloc[0])

        expected_millis = int(datetime(2025, 1, 2, tzinfo=UTC).timestamp() * 1000)
        assert notes_df["timestampMillisOfLatestNonNMRStatus"].iloc[1] == expected_millis

    def test_notes_locked_status_is_none(self):
        notes = pa.table(
            {
                "id": ["n1"],
                "author_id": ["u1"],
                "classification": ["NOT_MISLEADING"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [datetime(2025, 1, 1, tzinfo=UTC)],
            }
        )
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1"])

        from src.notes.scoring.data_transforms import transform_community_data

        _, notes_df, _ = transform_community_data(ratings, notes, participants)

        assert notes_df["lockedStatus"].iloc[0] is None


class TestTransformParticipants:
    def test_transforms_participants_to_enrollment_dataframe(self):
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1", "u2", "u3"])

        from src.notes.scoring.data_transforms import transform_community_data

        _, _, enrollment_df = transform_community_data(ratings, notes, participants)

        assert isinstance(enrollment_df, pd.DataFrame)
        assert len(enrollment_df) == 3
        assert "participantId" in enrollment_df.columns
        assert "modelingGroup" in enrollment_df.columns
        assert list(enrollment_df["participantId"]) == ["u1", "u2", "u3"]
        assert all(enrollment_df["modelingGroup"] == 13)

    def test_empty_participants(self):
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array([], type=pa.string())

        from src.notes.scoring.data_transforms import transform_community_data

        _, _, enrollment_df = transform_community_data(ratings, notes, participants)

        assert len(enrollment_df) == 0
        assert "participantId" in enrollment_df.columns
        assert "modelingGroup" in enrollment_df.columns


class TestTransformOutputColumnsMatchBuilders:
    def test_ratings_columns_match_builder_output(self):
        from src.notes.scoring.ratings_dataframe_builder import (
            RatingsDataFrameBuilder,
        )

        dt = datetime(2025, 1, 1, tzinfo=UTC)
        builder_df = RatingsDataFrameBuilder().build(
            [
                {
                    "id": "r1",
                    "note_id": "n1",
                    "rater_id": "u1",
                    "helpfulness_level": "HELPFUL",
                    "created_at": dt,
                }
            ]
        )

        ratings = pa.table(
            {
                "id": ["r1"],
                "note_id": ["n1"],
                "rater_id": ["u1"],
                "helpfulness_level": ["HELPFUL"],
                "created_at": [dt],
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1"])

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, _, _ = transform_community_data(ratings, notes, participants)

        assert set(builder_df.columns) == set(ratings_df.columns)

    def test_notes_columns_match_builder_output(self):
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        dt = datetime(2025, 1, 1, tzinfo=UTC)
        builder_df = NoteStatusHistoryBuilder().build(
            [
                {
                    "id": "n1",
                    "author_id": "u1",
                    "classification": "NOT_MISLEADING",
                    "status": "NEEDS_MORE_RATINGS",
                    "created_at": dt,
                }
            ]
        )

        notes = pa.table(
            {
                "id": ["n1"],
                "author_id": ["u1"],
                "classification": ["NOT_MISLEADING"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [dt],
            }
        )
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1"])

        from src.notes.scoring.data_transforms import transform_community_data

        _, notes_df, _ = transform_community_data(ratings, notes, participants)

        assert set(builder_df.columns) == set(notes_df.columns)

    def test_ratings_values_match_builder_output(self):
        from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder

        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        input_data = [
            {
                "id": "r1",
                "note_id": "n1",
                "rater_id": "u1",
                "helpfulness_level": "HELPFUL",
                "created_at": dt,
            },
            {
                "id": "r2",
                "note_id": "n1",
                "rater_id": "u2",
                "helpfulness_level": "NOT_HELPFUL",
                "created_at": dt,
            },
        ]
        builder_df = RatingsDataFrameBuilder().build(input_data)

        ratings = pa.table(
            {
                "id": ["r1", "r2"],
                "note_id": ["n1", "n1"],
                "rater_id": ["u1", "u2"],
                "helpfulness_level": ["HELPFUL", "NOT_HELPFUL"],
                "created_at": [dt, dt],
            }
        )
        notes = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "author_id": pa.array([], type=pa.string()),
                "classification": pa.array([], type=pa.string()),
                "status": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1", "u2"])

        from src.notes.scoring.data_transforms import transform_community_data

        ratings_df, _, _ = transform_community_data(ratings, notes, participants)

        for col in builder_df.columns:
            pd.testing.assert_series_equal(
                builder_df[col].reset_index(drop=True),
                ratings_df[col].reset_index(drop=True),
                check_names=False,
                check_dtype=False,
            )

    def test_notes_values_match_builder_output(self):
        from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder

        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        input_data = [
            {
                "id": "n1",
                "author_id": "u1",
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
                "created_at": dt,
            },
            {
                "id": "n2",
                "author_id": "u2",
                "classification": "NOT_MISLEADING",
                "status": "CURRENTLY_RATED_HELPFUL",
                "created_at": dt,
            },
        ]
        builder_df = NoteStatusHistoryBuilder().build(input_data)

        notes = pa.table(
            {
                "id": ["n1", "n2"],
                "author_id": ["u1", "u2"],
                "classification": ["NOT_MISLEADING", "NOT_MISLEADING"],
                "status": ["NEEDS_MORE_RATINGS", "CURRENTLY_RATED_HELPFUL"],
                "created_at": [dt, dt],
            }
        )
        ratings = pa.table(
            {
                "id": pa.array([], type=pa.string()),
                "note_id": pa.array([], type=pa.string()),
                "rater_id": pa.array([], type=pa.string()),
                "helpfulness_level": pa.array([], type=pa.string()),
                "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }
        )
        participants = pa.array(["u1", "u2"])

        from src.notes.scoring.data_transforms import transform_community_data

        _, notes_df, _ = transform_community_data(ratings, notes, participants)

        for col in builder_df.columns:
            pd.testing.assert_series_equal(
                builder_df[col].reset_index(drop=True),
                notes_df[col].reset_index(drop=True),
                check_names=False,
                check_dtype=False,
            )
