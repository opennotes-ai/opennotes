from __future__ import annotations

import logging
import math
from typing import Any
from uuid import UUID

import pendulum
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.notes.scoring.models import ScoringSnapshot

logger = logging.getLogger(__name__)


def _sanitize_float(value: float) -> float | None:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def extract_factors_from_model_result(
    model_result: Any,
    int_to_uuid: dict[int, str],
) -> dict[str, Any]:
    rater_factors: list[dict[str, Any]] = []
    if model_result.helpfulnessScores is not None:
        hs = model_result.helpfulnessScores
        for _, row in hs.iterrows():
            rater_id_raw = row.get("raterParticipantId", "")
            rater_factors.append(
                {
                    "rater_id": str(rater_id_raw),
                    "intercept": _sanitize_float(float(row.get("coreRaterIntercept", 0.0))),
                    "factor1": _sanitize_float(float(row.get("coreRaterFactor1", 0.0))),
                }
            )

    note_factors: list[dict[str, Any]] = []
    if model_result.scoredNotes is not None:
        sn = model_result.scoredNotes
        for _, row in sn.iterrows():
            int_note_id = int(row["noteId"])
            note_id = int_to_uuid.get(int_note_id, str(int_note_id))
            note_factors.append(
                {
                    "note_id": note_id,
                    "intercept": _sanitize_float(float(row.get("coreNoteIntercept", 0.0))),
                    "factor1": _sanitize_float(float(row.get("coreNoteFactor1", 0.0))),
                    "status": str(row.get("coreRatingStatus", "")),
                }
            )

    global_intercept = 0.0
    if (
        model_result.scoredNotes is not None
        and "coreNoteIntercept" in model_result.scoredNotes.columns
        and len(model_result.scoredNotes) > 0
    ):
        global_intercept = _sanitize_float(
            float(model_result.scoredNotes["coreNoteIntercept"].mean())
        )

    return {
        "rater_factors": rater_factors,
        "note_factors": note_factors,
        "global_intercept": global_intercept,
        "rater_count": len(rater_factors),
        "note_count": len(note_factors),
    }


async def persist_scoring_snapshot(
    community_server_id: UUID,
    rater_factors: list[dict[str, Any]],
    note_factors: list[dict[str, Any]],
    global_intercept: float | None,
    metadata: dict[str, Any],
    db: AsyncSession,
) -> ScoringSnapshot:
    now = pendulum.now("UTC")

    table = ScoringSnapshot.__table__
    values = {
        "community_server_id": community_server_id,
        "scored_at": now,
        "rater_factors": rater_factors,
        "note_factors": note_factors,
        "global_intercept": global_intercept if global_intercept is not None else 0.0,
        "metadata": metadata,
    }

    stmt = pg_insert(table).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["community_server_id"],
        set_={
            "scored_at": stmt.excluded.scored_at,
            "rater_factors": stmt.excluded.rater_factors,
            "note_factors": stmt.excluded.note_factors,
            "global_intercept": stmt.excluded.global_intercept,
            "metadata": stmt.excluded.metadata,
        },
    ).returning(table)

    result = await db.execute(stmt)
    row = result.mappings().one()

    snapshot = ScoringSnapshot(
        id=row["id"],
        community_server_id=row["community_server_id"],
        scored_at=row["scored_at"],
        rater_factors=row["rater_factors"],
        note_factors=row["note_factors"],
        global_intercept=row["global_intercept"],
        metadata_=row["metadata"],
    )

    logger.info(
        "Upserted scoring snapshot",
        extra={
            "community_server_id": str(community_server_id),
            "rater_count": len(rater_factors),
            "note_count": len(note_factors),
        },
    )
    return snapshot
