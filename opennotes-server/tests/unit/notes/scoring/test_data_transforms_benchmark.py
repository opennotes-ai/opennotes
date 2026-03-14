import tracemalloc
from datetime import UTC, datetime
from uuid import uuid4

import pandas as pd
import pyarrow as pa
import pytest

from src.notes.scoring.data_transforms import transform_community_data
from src.notes.scoring.note_status_history_builder import NoteStatusHistoryBuilder
from src.notes.scoring.ratings_dataframe_builder import RatingsDataFrameBuilder
from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

NUM_RATINGS = 50_000
NUM_NOTES = 50_000
NUM_PARTICIPANTS = 10_000


def _generate_list_data():
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    ratings = [
        {
            "id": str(uuid4()),
            "note_id": str(uuid4()),
            "rater_id": f"user-{i % NUM_PARTICIPANTS}",
            "helpfulness_level": ["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"][i % 3],
            "created_at": now,
        }
        for i in range(NUM_RATINGS)
    ]
    notes = [
        {
            "id": str(uuid4()),
            "author_id": f"user-{i % NUM_PARTICIPANTS}",
            "classification": "NOT_MISLEADING"
            if i % 2 == 0
            else "MISINFORMED_OR_POTENTIALLY_MISLEADING",
            "status": [
                "NEEDS_MORE_RATINGS",
                "CURRENTLY_RATED_HELPFUL",
                "CURRENTLY_RATED_NOT_HELPFUL",
            ][i % 3],
            "created_at": now,
        }
        for i in range(NUM_NOTES)
    ]
    participants = [f"user-{i}" for i in range(NUM_PARTICIPANTS)]
    return ratings, notes, participants


def _generate_arrow_data():
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    levels = ["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"]
    statuses = ["NEEDS_MORE_RATINGS", "CURRENTLY_RATED_HELPFUL", "CURRENTLY_RATED_NOT_HELPFUL"]

    ratings_table = pa.table(
        {
            "id": [str(uuid4()) for _ in range(NUM_RATINGS)],
            "note_id": [str(uuid4()) for _ in range(NUM_RATINGS)],
            "rater_id": [f"user-{i % NUM_PARTICIPANTS}" for i in range(NUM_RATINGS)],
            "helpfulness_level": [levels[i % 3] for i in range(NUM_RATINGS)],
            "created_at": [now] * NUM_RATINGS,
        }
    )
    notes_table = pa.table(
        {
            "id": [str(uuid4()) for _ in range(NUM_NOTES)],
            "author_id": [f"user-{i % NUM_PARTICIPANTS}" for i in range(NUM_NOTES)],
            "classification": [
                "NOT_MISLEADING" if i % 2 == 0 else "MISINFORMED_OR_POTENTIALLY_MISLEADING"
                for i in range(NUM_NOTES)
            ],
            "status": [statuses[i % 3] for i in range(NUM_NOTES)],
            "created_at": [now] * NUM_NOTES,
        }
    )
    participants_array = pa.array([f"user-{i}" for i in range(NUM_PARTICIPANTS)])
    return ratings_table, notes_table, participants_array


def _old_approach(ratings_list, notes_list, participants_list):
    rb = RatingsDataFrameBuilder()
    nb = NoteStatusHistoryBuilder()
    ub = UserEnrollmentBuilder()
    ratings_df = rb.build(ratings_list)
    notes_df = nb.build(notes_list)
    enrollment_df = ub.build(participants_list)
    return ratings_df, notes_df, enrollment_df


def _new_approach(ratings_table, notes_table, participants_array):
    return transform_community_data(ratings_table, notes_table, participants_array)


@pytest.mark.benchmark
class TestDataTransformsBenchmark:
    def test_old_approach_memory(self):
        ratings_list, notes_list, participants_list = _generate_list_data()

        tracemalloc.start()
        _old_approach(ratings_list, notes_list, participants_list)
        _, old_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert old_peak > 0

    def test_new_approach_memory(self):
        ratings_table, notes_table, participants_array = _generate_arrow_data()

        tracemalloc.start()
        _new_approach(ratings_table, notes_table, participants_array)
        _, new_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert new_peak > 0

    def test_new_approach_uses_less_memory_than_old(self):
        ratings_list, notes_list, participants_list = _generate_list_data()

        tracemalloc.start()
        _old_approach(ratings_list, notes_list, participants_list)
        _, old_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        ratings_table, notes_table, participants_array = _generate_arrow_data()

        tracemalloc.start()
        _new_approach(ratings_table, notes_table, participants_array)
        _, new_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        old_mb = old_peak / (1024 * 1024)
        new_mb = new_peak / (1024 * 1024)
        ratio = new_peak / old_peak if old_peak > 0 else 0

        print(f"\nOld approach peak memory: {old_mb:.1f} MB")
        print(f"New approach peak memory: {new_mb:.1f} MB")
        print(f"Memory ratio (new/old): {ratio:.2f}")
        print(f"Memory savings: {(1 - ratio) * 100:.0f}%")

        assert new_peak < old_peak, (
            f"New approach ({new_mb:.1f} MB) should use less memory "
            f"than old approach ({old_mb:.1f} MB)"
        )

    def test_new_approach_output_matches_old_approach(self):
        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        ratings_data = [
            {
                "id": "r1",
                "note_id": "n1",
                "rater_id": "u1",
                "helpfulness_level": "HELPFUL",
                "created_at": now,
            },
            {
                "id": "r2",
                "note_id": "n1",
                "rater_id": "u2",
                "helpfulness_level": "NOT_HELPFUL",
                "created_at": now,
            },
        ]
        notes_data = [
            {
                "id": "n1",
                "author_id": "u3",
                "classification": "NOT_MISLEADING",
                "status": "NEEDS_MORE_RATINGS",
                "created_at": now,
            },
            {
                "id": "n2",
                "author_id": "u4",
                "classification": "NOT_MISLEADING",
                "status": "CURRENTLY_RATED_HELPFUL",
                "created_at": now,
            },
        ]
        participants_data = ["u1", "u2", "u3", "u4"]

        old_ratings, old_notes, old_enrollment = _old_approach(
            ratings_data, notes_data, participants_data
        )

        ratings_table = pa.table(
            {
                "id": ["r1", "r2"],
                "note_id": ["n1", "n1"],
                "rater_id": ["u1", "u2"],
                "helpfulness_level": ["HELPFUL", "NOT_HELPFUL"],
                "created_at": [now, now],
            }
        )
        notes_table = pa.table(
            {
                "id": ["n1", "n2"],
                "author_id": ["u3", "u4"],
                "classification": ["NOT_MISLEADING", "NOT_MISLEADING"],
                "status": ["NEEDS_MORE_RATINGS", "CURRENTLY_RATED_HELPFUL"],
                "created_at": [now, now],
            }
        )
        participants_array = pa.array(["u1", "u2", "u3", "u4"])

        new_ratings, new_notes, new_enrollment = _new_approach(
            ratings_table, notes_table, participants_array
        )

        assert set(old_ratings.columns) == set(new_ratings.columns)
        assert set(old_notes.columns) == set(new_notes.columns)
        assert set(old_enrollment.columns) == set(new_enrollment.columns)

        for col in old_ratings.columns:
            pd.testing.assert_series_equal(
                old_ratings[col].reset_index(drop=True),
                new_ratings[col].reset_index(drop=True),
                check_names=False,
                check_dtype=False,
            )
