from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from src.monitoring import get_logger
from src.notes.models import Note, Rating
from src.simulation.models import SimAgentInstance, SimAgentMemory, SimulationRun
from src.simulation.schemas import (
    AgentBehaviorData,
    AnalysisAttributes,
    ConsensusMetricsData,
    NoteQualityData,
    PerAgentRatingData,
    RatingDistributionData,
    ScoringCoverageData,
)
from src.simulation.scoring_integration import get_scoring_metrics

logger = get_logger(__name__)


async def _get_agent_instances(
    simulation_run_id: UUID,
    db: AsyncSession,
) -> list[SimAgentInstance]:
    result = await db.execute(
        select(SimAgentInstance)
        .where(SimAgentInstance.simulation_run_id == simulation_run_id)
        .options(selectinload(SimAgentInstance.agent_profile))
    )
    return list(result.scalars().all())


async def compute_rating_distribution(
    simulation_run_id: UUID,
    instances: list[SimAgentInstance],
    db: AsyncSession,
) -> RatingDistributionData:
    user_profile_ids = [inst.user_profile_id for inst in instances]

    if not user_profile_ids:
        return RatingDistributionData(
            overall={},
            per_agent=[],
            total_ratings=0,
        )

    overall_result = await db.execute(
        select(Rating.helpfulness_level, func.count(Rating.id))
        .where(Rating.rater_id.in_(user_profile_ids))
        .group_by(Rating.helpfulness_level)
    )
    overall = {row[0]: row[1] for row in overall_result.all()}

    per_agent_result = await db.execute(
        select(Rating.rater_id, Rating.helpfulness_level, func.count(Rating.id))
        .where(Rating.rater_id.in_(user_profile_ids))
        .group_by(Rating.rater_id, Rating.helpfulness_level)
    )

    profile_to_instance: dict[UUID, SimAgentInstance] = {
        inst.user_profile_id: inst for inst in instances
    }

    agent_distributions: dict[UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rater_id, level, count in per_agent_result.all():
        agent_distributions[rater_id][level] = count

    per_agent = []
    for profile_id, dist in agent_distributions.items():
        inst = profile_to_instance.get(profile_id)
        if inst:
            per_agent.append(
                PerAgentRatingData(
                    agent_instance_id=str(inst.id),
                    agent_name=inst.agent_profile.name if inst.agent_profile else "Unknown",
                    distribution=dict(dist),
                    total=sum(dist.values()),
                )
            )

    total_ratings = sum(overall.values())

    return RatingDistributionData(
        overall=overall,
        per_agent=per_agent,
        total_ratings=total_ratings,
    )


async def compute_consensus_metrics(
    instances: list[SimAgentInstance],
    db: AsyncSession,
) -> ConsensusMetricsData:
    user_profile_ids = [inst.user_profile_id for inst in instances]

    if not user_profile_ids:
        return ConsensusMetricsData(
            mean_agreement=0.0,
            polarization_index=0.0,
            notes_with_consensus=0,
            notes_with_disagreement=0,
            total_notes_rated=0,
        )

    rated_notes_result = await db.execute(
        select(Rating.note_id)
        .where(Rating.rater_id.in_(user_profile_ids))
        .group_by(Rating.note_id)
        .having(func.count(Rating.id) >= 2)
    )
    note_ids_with_multiple = [row[0] for row in rated_notes_result.all()]

    if not note_ids_with_multiple:
        single_count_result = await db.execute(
            select(func.count(func.distinct(Rating.note_id))).where(
                Rating.rater_id.in_(user_profile_ids)
            )
        )
        total = single_count_result.scalar() or 0
        return ConsensusMetricsData(
            mean_agreement=0.0,
            polarization_index=0.0,
            notes_with_consensus=0,
            notes_with_disagreement=0,
            total_notes_rated=total,
        )

    ratings_result = await db.execute(
        select(Rating.note_id, Rating.helpfulness_level)
        .where(
            Rating.rater_id.in_(user_profile_ids),
            Rating.note_id.in_(note_ids_with_multiple),
        )
        .order_by(Rating.note_id)
    )

    note_ratings: dict[UUID, list[str]] = defaultdict(list)
    for note_id, level in ratings_result.all():
        note_ratings[note_id].append(level)

    agreements: list[float] = []
    polarized_count = 0
    consensus_count = 0
    disagreement_count = 0

    for _note_id, levels in note_ratings.items():
        counter = Counter(levels)
        total_for_note = len(levels)
        max_same = max(counter.values())
        agreement = max_same / total_for_note
        agreements.append(agreement)

        if agreement == 1.0:
            consensus_count += 1
        else:
            disagreement_count += 1

        has_helpful = counter.get("HELPFUL", 0)
        has_not_helpful = counter.get("NOT_HELPFUL", 0)
        if has_helpful > 0 and has_not_helpful > 0:
            min_extreme = min(has_helpful, has_not_helpful)
            polarized_count += min_extreme / total_for_note

    total_multi_rated = len(note_ratings)
    total_distinct_result = await db.execute(
        select(func.count(func.distinct(Rating.note_id))).where(
            Rating.rater_id.in_(user_profile_ids)
        )
    )
    total_notes_rated = total_distinct_result.scalar() or 0

    mean_agreement = sum(agreements) / len(agreements) if agreements else 0.0
    polarization_index = polarized_count / total_multi_rated if total_multi_rated > 0 else 0.0

    return ConsensusMetricsData(
        mean_agreement=round(mean_agreement, 4),
        polarization_index=round(polarization_index, 4),
        notes_with_consensus=consensus_count,
        notes_with_disagreement=disagreement_count,
        total_notes_rated=total_notes_rated,
    )


async def compute_scoring_coverage(
    simulation_run_id: UUID,
    db: AsyncSession,
) -> ScoringCoverageData:
    metrics = await get_scoring_metrics(simulation_run_id, db)

    run = await db.get(SimulationRun, simulation_run_id)
    run_metrics = (run.metrics or {}) if run else {}

    return ScoringCoverageData(
        current_tier=metrics.current_tier,
        total_scores_computed=metrics.total_scores_computed,
        tier_distribution=metrics.tier_distribution,
        scorer_breakdown=metrics.scorer_breakdown,
        notes_by_status=metrics.notes_by_status,
        tiers_reached=run_metrics.get("tiers_reached", []),
        scorers_exercised=run_metrics.get("scorers_used", []),
    )


async def compute_agent_behavior_metrics(
    instances: list[SimAgentInstance],
    db: AsyncSession,
) -> list[AgentBehaviorData]:
    if not instances:
        return []

    user_profile_ids = [inst.user_profile_id for inst in instances]

    notes_count_result = await db.execute(
        select(Note.author_id, func.count(Note.id))
        .where(
            Note.author_id.in_(user_profile_ids),
            Note.deleted_at.is_(None),
        )
        .group_by(Note.author_id)
    )
    notes_by_author: dict[UUID, int] = {row[0]: row[1] for row in notes_count_result.all()}

    ratings_count_result = await db.execute(
        select(Rating.rater_id, func.count(Rating.id))
        .where(Rating.rater_id.in_(user_profile_ids))
        .group_by(Rating.rater_id)
    )
    ratings_by_rater: dict[UUID, int] = {row[0]: row[1] for row in ratings_count_result.all()}

    ratings_trend_result = await db.execute(
        select(Rating.rater_id, Rating.helpfulness_level)
        .where(Rating.rater_id.in_(user_profile_ids))
        .order_by(Rating.created_at)
    )
    trends: dict[UUID, list[str]] = defaultdict(list)
    for rater_id, level in ratings_trend_result.all():
        trends[rater_id].append(level)

    instance_ids = [inst.id for inst in instances]
    memories_result = await db.execute(
        select(SimAgentMemory)
        .where(SimAgentMemory.agent_instance_id.in_(instance_ids))
        .options(load_only(SimAgentMemory.agent_instance_id, SimAgentMemory.recent_actions))
    )
    memories_by_instance: dict[UUID, SimAgentMemory] = {
        mem.agent_instance_id: mem for mem in memories_result.scalars().all()
    }

    behaviors = []
    for inst in instances:
        memory = memories_by_instance.get(inst.id)
        action_dist: dict[str, int] = {}
        if memory and memory.recent_actions:
            action_counter: Counter[str] = Counter()
            for action in memory.recent_actions:
                if isinstance(action, str):
                    action_counter[action] += 1
                elif isinstance(action, dict) and "action_type" in action:
                    action_counter[action["action_type"]] += 1
            action_dist = dict(action_counter)

        behaviors.append(
            AgentBehaviorData(
                agent_instance_id=str(inst.id),
                agent_name=inst.agent_profile.name if inst.agent_profile else "Unknown",
                notes_written=notes_by_author.get(inst.user_profile_id, 0),
                ratings_given=ratings_by_rater.get(inst.user_profile_id, 0),
                turn_count=inst.turn_count,
                state=inst.state,
                helpfulness_trend=trends.get(inst.user_profile_id, []),
                action_distribution=action_dist,
            )
        )

    return behaviors


async def compute_note_quality(
    instances: list[SimAgentInstance],
    db: AsyncSession,
) -> NoteQualityData:
    user_profile_ids = [inst.user_profile_id for inst in instances]

    if not user_profile_ids:
        return NoteQualityData(
            avg_helpfulness_score=None,
            notes_by_status={},
            notes_by_classification={},
        )

    avg_result = await db.execute(
        select(func.avg(Note.helpfulness_score)).where(
            Note.author_id.in_(user_profile_ids),
            Note.deleted_at.is_(None),
            Note.status.in_(["CURRENTLY_RATED_HELPFUL", "CURRENTLY_RATED_NOT_HELPFUL"]),
        )
    )
    avg_score_raw = avg_result.scalar()
    avg_score = round(float(avg_score_raw), 2) if avg_score_raw is not None else None

    status_result = await db.execute(
        select(Note.status, func.count(Note.id))
        .where(
            Note.author_id.in_(user_profile_ids),
            Note.deleted_at.is_(None),
        )
        .group_by(Note.status)
    )
    notes_by_status = {row[0]: row[1] for row in status_result.all()}

    classification_result = await db.execute(
        select(Note.classification, func.count(Note.id))
        .where(
            Note.author_id.in_(user_profile_ids),
            Note.deleted_at.is_(None),
        )
        .group_by(Note.classification)
    )
    notes_by_classification = {row[0]: row[1] for row in classification_result.all()}

    return NoteQualityData(
        avg_helpfulness_score=avg_score,
        notes_by_status=notes_by_status,
        notes_by_classification=notes_by_classification,
    )


async def compute_full_analysis(
    simulation_run_id: UUID,
    db: AsyncSession,
) -> AnalysisAttributes:
    instances = await _get_agent_instances(simulation_run_id, db)

    rating_distribution = await compute_rating_distribution(simulation_run_id, instances, db)
    consensus_metrics = await compute_consensus_metrics(instances, db)
    scoring_coverage = await compute_scoring_coverage(simulation_run_id, db)
    agent_behaviors = await compute_agent_behavior_metrics(instances, db)
    note_quality = await compute_note_quality(instances, db)

    return AnalysisAttributes(
        rating_distribution=rating_distribution,
        consensus_metrics=consensus_metrics,
        scoring_coverage=scoring_coverage,
        agent_behaviors=agent_behaviors,
        note_quality=note_quality,
    )
