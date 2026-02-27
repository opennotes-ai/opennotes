from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import case, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.llm_config.models import CommunityServer
from src.monitoring.metrics import notes_scored_total
from src.notes import loaders as note_loaders
from src.notes.models import Note, Rating, Request
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


@dataclass
class CommunityServerScoringResult:
    community_server_id: UUID
    unscored_notes_processed: int
    rescored_notes_processed: int
    total_scores_computed: int
    tier_name: str
    scorer_type: str


async def _record_scoring_metrics(
    db: AsyncSession,
    community_server_id: UUID,
    total_scores_computed: int,
    tier_value: str,
) -> str:
    """Record scoring metrics with platform label for Grafana filtering."""
    platform = "unknown"
    if total_scores_computed > 0:
        platform_result = await db.execute(
            select(CommunityServer.platform).where(CommunityServer.id == community_server_id)
        )
        platform = platform_result.scalar_one_or_none() or "unknown"
        notes_scored_total.add(
            total_scores_computed,
            {"platform": platform, "tier": tier_value},
        )
    return platform


async def score_community_server_notes(
    community_server_id: UUID,
    db: AsyncSession,
) -> CommunityServerScoringResult:
    """Score all eligible notes in a community server.

    Two-pass approach:
    1. Score unscored notes: status=NEEDS_MORE_RATINGS with >= MIN_RATINGS_NEEDED ratings
    2. Rescore already-scored notes: status in (CRH, CRNH)

    Both passes ordered by stalest-last-rating first (note whose most recent
    rating.created_at is the oldest goes first).
    """
    count_result = await db.execute(
        select(func.count(Note.id)).where(
            Note.community_server_id == community_server_id,
            Note.deleted_at.is_(None),
        )
    )
    note_count = count_result.scalar() or 0

    if note_count == 0:
        return CommunityServerScoringResult(
            community_server_id=community_server_id,
            unscored_notes_processed=0,
            rescored_notes_processed=0,
            total_scores_computed=0,
            tier_name="Minimal",
            scorer_type="none",
        )

    tier = get_tier_for_note_count(note_count)
    factory = ScorerFactory()
    scorer = factory.get_scorer(str(community_server_id), note_count)
    scorer_type = type(scorer).__name__

    latest_rating_subq = (
        select(func.max(Rating.created_at))
        .where(Rating.note_id == Note.id)
        .correlate(Note)
        .scalar_subquery()
    )

    rating_count_subq = (
        select(func.count(Rating.id))
        .where(Rating.note_id == Note.id)
        .correlate(Note)
        .scalar_subquery()
    )

    unscored_notes_processed = 0
    rescored_notes_processed = 0
    total_scores_computed = 0

    for pass_label, status_filter in [
        (
            "unscored",
            [
                Note.status == "NEEDS_MORE_RATINGS",
                rating_count_subq >= settings.MIN_RATINGS_NEEDED,
            ],
        ),
        (
            "rescore",
            [
                Note.status.in_(["CURRENTLY_RATED_HELPFUL", "CURRENTLY_RATED_NOT_HELPFUL"]),
            ],
        ),
    ]:
        offset = 0
        pass_count = 0

        while True:
            batch_result = await db.execute(
                select(Note)
                .where(
                    Note.community_server_id == community_server_id,
                    Note.deleted_at.is_(None),
                    *status_filter,
                )
                .options(*note_loaders.full())
                .order_by(latest_rating_subq.asc(), Note.id)
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
                    pass_count += 1
                    total_scores_computed += 1
                except Exception:
                    logger.exception(
                        "Failed to score note",
                        extra={
                            "note_id": str(note.id),
                            "community_server_id": str(community_server_id),
                            "pass": pass_label,
                        },
                    )

            if score_mapping:
                note_ids = list(score_mapping.keys())
                await db.execute(
                    update(Note)
                    .where(Note.id.in_(note_ids))
                    .values(
                        helpfulness_score=case(score_mapping, value=Note.id),
                        status=cast(case(status_mapping, value=Note.id), Note.status.type),
                    )
                )

            if len(batch) < SCORING_BATCH_SIZE:
                break

            if pass_label == "rescore":
                offset += SCORING_BATCH_SIZE

        if pass_label == "unscored":
            unscored_notes_processed = pass_count
        else:
            rescored_notes_processed = pass_count

    helpful_note_for_request = (
        select(Note.id)
        .where(
            Note.request_id == Request.request_id,
            Note.community_server_id == community_server_id,
            Note.status == "CURRENTLY_RATED_HELPFUL",
            Note.deleted_at.is_(None),
        )
        .correlate(Request)
        .order_by(Note.helpfulness_score.desc())
        .limit(1)
        .scalar_subquery()
    )
    await db.execute(
        update(Request)
        .where(
            Request.community_server_id == community_server_id,
            Request.status == "PENDING",
            helpful_note_for_request.isnot(None),
        )
        .values(status="COMPLETED", note_id=helpful_note_for_request)
    )

    await db.commit()

    platform = await _record_scoring_metrics(
        db, community_server_id, total_scores_computed, tier.value
    )

    logger.info(
        "Community server scoring completed",
        extra={
            "community_server_id": str(community_server_id),
            "unscored_notes_processed": unscored_notes_processed,
            "rescored_notes_processed": rescored_notes_processed,
            "total_scores_computed": total_scores_computed,
            "tier": tier.value,
            "scorer_type": scorer_type,
            "platform": platform,
        },
    )

    return CommunityServerScoringResult(
        community_server_id=community_server_id,
        unscored_notes_processed=unscored_notes_processed,
        rescored_notes_processed=rescored_notes_processed,
        total_scores_computed=total_scores_computed,
        tier_name=tier.value.capitalize(),
        scorer_type=scorer_type,
    )


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
            .options(*note_loaders.full())
            .order_by(Note.id)
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
                    status=cast(case(status_mapping, value=Note.id), Note.status.type),
                )
            )

        if len(batch) < SCORING_BATCH_SIZE:
            break

        offset += SCORING_BATCH_SIZE

    helpful_note_for_request = (
        select(Note.id)
        .where(
            Note.request_id == Request.request_id,
            Note.community_server_id == community_server_id,
            Note.status == "CURRENTLY_RATED_HELPFUL",
            Note.deleted_at.is_(None),
        )
        .correlate(Request)
        .order_by(Note.helpfulness_score.desc())
        .limit(1)
        .scalar_subquery()
    )
    await db.execute(
        update(Request)
        .where(
            Request.community_server_id == community_server_id,
            Request.status == "PENDING",
            helpful_note_for_request.isnot(None),
        )
        .values(status="COMPLETED", note_id=helpful_note_for_request)
    )

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
