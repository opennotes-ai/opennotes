import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

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

DEFAULT_MODELING_GROUP = 13


def _timestamps_to_millis(ts_column: pa.Array) -> pa.Array:
    if len(ts_column) == 0:
        return pa.array([], type=pa.int64())
    ts_us = pc.cast(ts_column, pa.timestamp("us", tz="UTC"))
    epoch = pa.scalar(0, type=pa.timestamp("us", tz="UTC"))
    diff_us = pc.subtract(ts_us, epoch)
    return pc.cast(pc.divide(diff_us, 1000), pa.int64())


def _map_helpfulness(levels: pa.Array) -> pa.Array:
    return pc.if_else(
        pc.equal(levels, "HELPFUL"),
        1.0,
        pc.if_else(
            pc.equal(levels, "SOMEWHAT_HELPFUL"),
            0.5,
            0.0,
        ),
    )


def transform_community_data(
    ratings: pa.Table,
    notes: pa.Table,
    participants: pa.Array,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ratings_df = _transform_ratings(ratings)
    notes_df = _transform_notes(notes)
    enrollment_df = _transform_participants(participants)
    return ratings_df, notes_df, enrollment_df


def _transform_ratings(ratings: pa.Table) -> pd.DataFrame:
    n = ratings.num_rows
    if n == 0:
        columns = [
            "noteId",
            "raterParticipantId",
            "createdAtMillis",
            "helpfulNum",
            "helpfulnessLevel",
            "ratingSourceBucketed",
            "highVolumeRater",
            "correlatedRater",
            *ALL_TAG_COLUMNS,
        ]
        return pd.DataFrame(columns=columns)

    millis = _timestamps_to_millis(ratings.column("created_at"))
    helpful_num = _map_helpfulness(ratings.column("helpfulness_level"))

    zero_col = pa.array(np.zeros(n, dtype=np.int64))

    out_columns = {
        "noteId": ratings.column("note_id"),
        "raterParticipantId": ratings.column("rater_id"),
        "createdAtMillis": millis,
        "helpfulNum": helpful_num,
        "helpfulnessLevel": ratings.column("helpfulness_level"),
        "ratingSourceBucketed": pa.array(["DEFAULT"] * n),
        "highVolumeRater": zero_col,
        "correlatedRater": zero_col,
    }
    for tag in ALL_TAG_COLUMNS:
        out_columns[tag] = zero_col

    return pa.table(out_columns).to_pandas()


def _transform_notes(notes: pa.Table) -> pd.DataFrame:
    n = notes.num_rows
    if n == 0:
        columns = [
            "noteId",
            "noteAuthorParticipantId",
            "createdAtMillis",
            "classification",
            "currentStatus",
            "lockedStatus",
            "timestampMillisOfLatestNonNMRStatus",
        ]
        return pd.DataFrame(columns=columns)

    millis = _timestamps_to_millis(notes.column("created_at"))
    statuses = notes.column("status")

    is_nmr = pc.equal(statuses, "NEEDS_MORE_RATINGS")
    one_week_ms = 7 * 24 * 60 * 60 * 1000
    future_millis = pc.cast(pc.add(millis, one_week_ms), pa.float64())
    nan_val = pa.scalar(float("nan"))
    ts_non_nmr = pc.if_else(is_nmr, nan_val, future_millis)

    out_columns = {
        "noteId": notes.column("id"),
        "noteAuthorParticipantId": notes.column("author_id"),
        "createdAtMillis": millis,
        "classification": notes.column("classification"),
        "currentStatus": statuses,
        "lockedStatus": pa.array([None] * n),
        "timestampMillisOfLatestNonNMRStatus": ts_non_nmr,
    }

    return pa.table(out_columns).to_pandas()


def _transform_participants(participants: pa.Array) -> pd.DataFrame:
    n = len(participants)
    if n == 0:
        return pd.DataFrame(columns=["participantId", "modelingGroup"])

    return pa.table(
        {
            "participantId": participants,
            "modelingGroup": pa.array([DEFAULT_MODELING_GROUP] * n, type=pa.int64()),
        }
    ).to_pandas()
