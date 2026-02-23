from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.notes.models import Note
from src.notes.scoring.scorer_factory import ScorerFactory
from src.notes.scoring.tier_config import (
    ScoringTier,
    get_tier_for_note_count,
)
from src.notes.scoring_utils import calculate_note_score
from src.simulation.models import SimulationRun

logger = logging.getLogger(__name__)

SCORING_BATCH_SIZE = 100


@dataclass
class ScoringRunResult:
    scores_computed: int
    tier: ScoringTier
    tier_name: str
    scorer_type: str
    note_count: int


@dataclass
class CoverageResult:
    all_targets_met: bool
    target_tiers: list[str]
    reached_tiers: list[str]
    missing_tiers: list[str]
    scorers_exercised: list[str] = field(default_factory=list)


@dataclass
class ScoringMetrics:
    total_scores_computed: int
    current_tier: str
    tier_distribution: dict[str, int]
    scorer_breakdown: dict[str, int]
    notes_by_status: dict[str, int]


async def trigger_scoring_for_simulation(
    simulation_run_id: UUID,
    db: AsyncSession,
) -> ScoringRunResult:
    run = await db.get(SimulationRun, simulation_run_id)
    if run is None:
        raise ValueError(f"SimulationRun {simulation_run_id} not found")

    community_server_id = run.community_server_id

    count_result = await db.execute(
        select(func.count(Note.id)).where(
            Note.community_server_id == community_server_id,
            Note.deleted_at.is_(None),
        )
    )
    note_count = count_result.scalar() or 0

    if note_count == 0:
        _empty_result = ScoringRunResult(
            scores_computed=0,
            tier=ScoringTier.MINIMAL,
            tier_name="Minimal",
            scorer_type="none",
            note_count=0,
        )
        _update_run_metrics(run, _empty_result)
        await db.commit()
        return _empty_result

    tier = get_tier_for_note_count(note_count)
    factory = ScorerFactory()
    scorer = factory.get_scorer(str(community_server_id), note_count)
    scorer_type = type(scorer).__name__

    scores_computed = 0
    offset = 0

    while True:
        batch_result = await db.execute(
            select(Note)
            .where(
                Note.community_server_id == community_server_id,
                Note.deleted_at.is_(None),
            )
            .options(selectinload(Note.ratings))
            .limit(SCORING_BATCH_SIZE)
            .offset(offset)
        )
        batch = batch_result.scalars().all()

        if not batch:
            break

        score_mapping: dict[UUID, int] = {}
        status_mapping: dict[UUID, str] = {}

        for note in batch:
            try:
                score_response = await calculate_note_score(note, note_count, scorer)

                status_update = "NEEDS_MORE_RATINGS"
                if score_response.rating_count >= settings.MIN_RATINGS_NEEDED:
                    status_update = (
                        "CURRENTLY_RATED_HELPFUL"
                        if score_response.score >= 0.5
                        else "CURRENTLY_RATED_NOT_HELPFUL"
                    )

                score_mapping[note.id] = int(score_response.score * 100)
                status_mapping[note.id] = status_update
                scores_computed += 1
            except Exception:
                logger.exception(
                    "Failed to score note",
                    extra={
                        "note_id": str(note.id),
                        "simulation_run_id": str(simulation_run_id),
                    },
                )

        if score_mapping:
            note_ids = list(score_mapping.keys())
            await db.execute(
                update(Note)
                .where(Note.id.in_(note_ids))
                .values(
                    helpfulness_score=case(score_mapping, value=Note.id),
                    status=case(status_mapping, value=Note.id),
                )
            )

        if len(batch) < SCORING_BATCH_SIZE:
            break

        offset += SCORING_BATCH_SIZE

    result = ScoringRunResult(
        scores_computed=scores_computed,
        tier=tier,
        tier_name=tier.value.capitalize(),
        scorer_type=scorer_type,
        note_count=note_count,
    )

    _update_run_metrics(run, result)
    await db.commit()

    logger.info(
        "Scoring completed for simulation",
        extra={
            "simulation_run_id": str(simulation_run_id),
            "scores_computed": scores_computed,
            "tier": tier.value,
            "scorer_type": scorer_type,
            "note_count": note_count,
        },
    )

    return result


def _update_run_metrics(run: SimulationRun, result: ScoringRunResult) -> None:
    metrics = dict(run.metrics) if run.metrics else {}

    prev_computed = metrics.get("scores_computed", 0)
    metrics["scores_computed"] = prev_computed + result.scores_computed
    metrics["last_scoring_tier"] = result.tier.value
    metrics["last_scorer_type"] = result.scorer_type
    metrics["last_note_count"] = result.note_count

    tiers_reached: list[str] = metrics.get("tiers_reached", [])
    if result.tier.value not in tiers_reached:
        tiers_reached.append(result.tier.value)
    metrics["tiers_reached"] = tiers_reached

    scorers_used: list[str] = metrics.get("scorers_used", [])
    if result.scorer_type != "none" and result.scorer_type not in scorers_used:
        scorers_used.append(result.scorer_type)
    metrics["scorers_used"] = scorers_used

    tier_distribution: dict[str, int] = metrics.get("tier_distribution", {})
    tier_distribution[result.tier.value] = (
        tier_distribution.get(result.tier.value, 0) + result.scores_computed
    )
    metrics["tier_distribution"] = tier_distribution

    scorer_breakdown: dict[str, int] = metrics.get("scorer_breakdown", {})
    if result.scorer_type != "none":
        scorer_breakdown[result.scorer_type] = (
            scorer_breakdown.get(result.scorer_type, 0) + result.scores_computed
        )
    metrics["scorer_breakdown"] = scorer_breakdown

    run.metrics = metrics


async def check_scoring_coverage(
    simulation_run_id: UUID,
    scoring_config: dict[str, Any],
    db: AsyncSession,
) -> CoverageResult:
    run = await db.get(SimulationRun, simulation_run_id)
    if run is None:
        raise ValueError(f"SimulationRun {simulation_run_id} not found")

    metrics = run.metrics or {}
    reached_tiers: list[str] = metrics.get("tiers_reached", [])
    scorers_used: list[str] = metrics.get("scorers_used", [])

    target_tiers: list[str] = scoring_config.get("target_tiers", [])
    missing_tiers = [t for t in target_tiers if t not in reached_tiers]

    return CoverageResult(
        all_targets_met=len(missing_tiers) == 0,
        target_tiers=target_tiers,
        reached_tiers=reached_tiers,
        missing_tiers=missing_tiers,
        scorers_exercised=scorers_used,
    )


async def get_scoring_metrics(
    simulation_run_id: UUID,
    db: AsyncSession,
) -> ScoringMetrics:
    run = await db.get(SimulationRun, simulation_run_id)
    if run is None:
        raise ValueError(f"SimulationRun {simulation_run_id} not found")

    metrics = run.metrics or {}
    community_server_id = run.community_server_id

    notes_by_status_result = await db.execute(
        select(Note.status, func.count(Note.id))
        .where(
            Note.community_server_id == community_server_id,
            Note.deleted_at.is_(None),
        )
        .group_by(Note.status)
    )
    notes_by_status = {row[0]: row[1] for row in notes_by_status_result.all()}

    return ScoringMetrics(
        total_scores_computed=metrics.get("scores_computed", 0),
        current_tier=metrics.get("last_scoring_tier", ScoringTier.MINIMAL.value),
        tier_distribution=metrics.get("tier_distribution", {}),
        scorer_breakdown=metrics.get("scorer_breakdown", {}),
        notes_by_status=notes_by_status,
    )
