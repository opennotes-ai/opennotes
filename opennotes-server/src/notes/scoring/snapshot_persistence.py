from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import pendulum
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.notes.scoring.models import ScoringSnapshot

logger = logging.getLogger(__name__)


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
                    "intercept": float(row.get("coreRaterIntercept", 0.0)),
                    "factor1": float(row.get("coreRaterFactor1", 0.0)),
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
                    "intercept": float(row.get("coreNoteIntercept", 0.0)),
                    "factor1": float(row.get("coreNoteFactor1", 0.0)),
                    "status": str(row.get("coreRatingStatus", "")),
                }
            )

    global_intercept = 0.0
    if (
        model_result.scoredNotes is not None
        and "coreNoteIntercept" in model_result.scoredNotes.columns
        and len(model_result.scoredNotes) > 0
    ):
        global_intercept = float(model_result.scoredNotes["coreNoteIntercept"].mean())

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
    global_intercept: float,
    metadata: dict[str, Any],
    db: AsyncSession,
) -> ScoringSnapshot:
    result = await db.execute(
        select(ScoringSnapshot).where(ScoringSnapshot.community_server_id == community_server_id)
    )
    existing = result.scalar_one_or_none()

    now = pendulum.now("UTC")

    if existing:
        existing.scored_at = now
        existing.rater_factors = rater_factors
        existing.note_factors = note_factors
        existing.global_intercept = global_intercept
        existing.metadata_ = metadata
        logger.info(
            "Updated scoring snapshot",
            extra={
                "community_server_id": str(community_server_id),
                "rater_count": len(rater_factors),
                "note_count": len(note_factors),
            },
        )
        return existing

    snapshot = ScoringSnapshot(
        community_server_id=community_server_id,
        scored_at=now,
        rater_factors=rater_factors,
        note_factors=note_factors,
        global_intercept=global_intercept,
        metadata_=metadata,
    )
    db.add(snapshot)
    logger.info(
        "Created scoring snapshot",
        extra={
            "community_server_id": str(community_server_id),
            "rater_count": len(rater_factors),
            "note_count": len(note_factors),
        },
    )
    return snapshot
