from src.simulation.schemas import TimelineAttributes, TimelineBucketData


def test_timeline_bucket_data_validates():
    bucket = TimelineBucketData(
        timestamp="2026-03-16T00:00:00+00:00",
        notes_by_status={"NEEDS_MORE_RATINGS": 3, "CURRENTLY_RATED_HELPFUL": 1},
        ratings_by_level={"HELPFUL": 5, "NOT_HELPFUL": 2},
    )
    assert bucket.timestamp == "2026-03-16T00:00:00+00:00"
    assert sum(bucket.notes_by_status.values()) == 4
    assert sum(bucket.ratings_by_level.values()) == 7


def test_timeline_bucket_data_defaults_empty():
    bucket = TimelineBucketData(timestamp="2026-03-16T00:00:00+00:00")
    assert bucket.notes_by_status == {}
    assert bucket.ratings_by_level == {}


def test_timeline_attributes_validates():
    attrs = TimelineAttributes(
        bucket_size="hour",
        buckets=[
            TimelineBucketData(
                timestamp="2026-03-16T00:00:00+00:00",
                notes_by_status={"NEEDS_MORE_RATINGS": 1},
                ratings_by_level={"HELPFUL": 2},
            ),
            TimelineBucketData(
                timestamp="2026-03-16T01:00:00+00:00",
                notes_by_status={"CURRENTLY_RATED_HELPFUL": 3},
                ratings_by_level={"NOT_HELPFUL": 1, "HELPFUL": 4},
            ),
        ],
        total_notes=4,
        total_ratings=7,
    )
    assert len(attrs.buckets) == 2
    assert attrs.bucket_size == "hour"
    assert attrs.total_notes == 4
    assert attrs.total_ratings == 7


def test_timeline_attributes_empty_buckets():
    attrs = TimelineAttributes(
        bucket_size="auto",
        buckets=[],
        total_notes=0,
        total_ratings=0,
    )
    assert len(attrs.buckets) == 0
