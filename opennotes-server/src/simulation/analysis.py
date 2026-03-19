from __future__ import annotations

from collections import Counter, defaultdict
from typing import Literal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from src.monitoring import get_logger
from src.notes import loaders
from src.notes.models import Note, Rating, Request
from src.simulation.model_display import humanize_model_name
from src.simulation.models import SimAgentInstance, SimAgentMemory, SimulationRun
from src.simulation.schemas import (
    AgentBehaviorData,
    AgentProfileData,
    AnalysisAttributes,
    ConsensusMetricsData,
    DetailedNoteData,
    DetailedRatingData,
    DetailedRequestData,
    NoteQualityData,
    PerAgentRatingData,
    RatingDistributionData,
    ScoringCoverageData,
    TimelineAttributes,
    TimelineBucketData,
)
from src.simulation.scoring_integration import get_scoring_metrics

logger = get_logger(__name__)


def build_profile_aggregation_map(
    instances: list[SimAgentInstance],
) -> dict[UUID, UUID]:
    return {
        inst.user_profile_id: inst.agent_profile_id for inst in instances if inst.turn_count > 0
    }


def group_instances_by_profile(
    instances: list[SimAgentInstance],
) -> dict[UUID, list[SimAgentInstance]]:
    groups: dict[UUID, list[SimAgentInstance]] = defaultdict(list)
    for inst in instances:
        if inst.turn_count > 0:
            groups[inst.agent_profile_id].append(inst)
    return dict(groups)


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


async def compute_agent_profiles(
    simulation_run_id: UUID,
    db: AsyncSession,
) -> list[AgentProfileData]:
    instances = await _get_agent_instances(simulation_run_id, db)
    if not instances:
        return []

    instance_ids = [inst.id for inst in instances]
    memories_result = await db.execute(
        select(SimAgentMemory).where(SimAgentMemory.agent_instance_id.in_(instance_ids))
    )
    memories_by_instance = {mem.agent_instance_id: mem for mem in memories_result.scalars().all()}

    grouped = group_instances_by_profile(instances)

    profiles = []
    for profile_id, group in grouped.items():
        latest = max(group, key=lambda i: i.turn_count)
        total_turns = sum(i.turn_count for i in group)

        memory = memories_by_instance.get(latest.id)
        last_messages: list[dict] = []
        token_count = 0
        recent_actions: list = []
        compaction_strategy = ""

        if memory:
            token_count = memory.token_count
            recent_actions = memory.recent_actions or []
            compaction_strategy = memory.compaction_strategy or ""
            msg_history = memory.message_history or []
            last_messages = msg_history[-30:] if msg_history else []

        profiles.append(
            AgentProfileData(
                agent_profile_id=str(profile_id),
                agent_name=latest.agent_profile.name if latest.agent_profile else "Unknown",
                personality=latest.agent_profile.personality if latest.agent_profile else "",
                short_description=latest.agent_profile.short_description
                if latest.agent_profile
                else None,
                model_name=latest.agent_profile.model_name if latest.agent_profile else "",
                memory_compaction_strategy=compaction_strategy
                or (
                    latest.agent_profile.memory_compaction_strategy if latest.agent_profile else ""
                ),
                turn_count=total_turns,
                state=latest.state,
                token_count=token_count,
                recent_actions=recent_actions,
                last_messages=last_messages,
            )
        )

    return profiles


async def compute_rating_distribution(
    simulation_run_id: UUID,
    instances: list[SimAgentInstance],
    db: AsyncSession,
) -> RatingDistributionData:
    active_instances = [inst for inst in instances if inst.turn_count > 0]
    user_profile_ids = [inst.user_profile_id for inst in active_instances]

    if not user_profile_ids:
        return RatingDistributionData(
            overall={},
            per_agent=[],
            total_ratings=0,
        )

    aggregation_map = build_profile_aggregation_map(active_instances)

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

    profile_distributions: dict[UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rater_id, level, count in per_agent_result.all():
        agent_profile_id = aggregation_map.get(rater_id)
        if agent_profile_id:
            profile_distributions[agent_profile_id][level] += count

    profile_name_map: dict[UUID, str] = {}
    for inst in active_instances:
        if inst.agent_profile_id not in profile_name_map:
            profile_name_map[inst.agent_profile_id] = (
                inst.agent_profile.name if inst.agent_profile else "Unknown"
            )

    per_agent = []
    for agent_profile_id, dist in profile_distributions.items():
        per_agent.append(
            PerAgentRatingData(
                agent_profile_id=str(agent_profile_id),
                agent_name=profile_name_map.get(agent_profile_id, "Unknown"),
                short_description=None,
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
    user_profile_ids = [inst.user_profile_id for inst in instances if inst.turn_count > 0]

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
    grouped = group_instances_by_profile(instances)
    if not grouped:
        return []

    user_profile_ids = [inst.user_profile_id for inst in instances if inst.turn_count > 0]

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

    active_instances = [inst for inst in instances if inst.turn_count > 0]
    instance_ids = [inst.id for inst in active_instances]
    memories_result = await db.execute(
        select(SimAgentMemory)
        .where(SimAgentMemory.agent_instance_id.in_(instance_ids))
        .options(load_only(SimAgentMemory.agent_instance_id, SimAgentMemory.recent_actions))
    )
    memories_by_instance: dict[UUID, SimAgentMemory] = {
        mem.agent_instance_id: mem for mem in memories_result.scalars().all()
    }

    behaviors = []
    for profile_id, group in grouped.items():
        latest = max(group, key=lambda i: i.turn_count)
        total_notes = sum(notes_by_author.get(i.user_profile_id, 0) for i in group)
        total_ratings = sum(ratings_by_rater.get(i.user_profile_id, 0) for i in group)
        total_turns = sum(i.turn_count for i in group)

        merged_trend: list[str] = []
        for inst in group:
            merged_trend.extend(trends.get(inst.user_profile_id, []))

        merged_actions: Counter[str] = Counter()
        for inst in group:
            memory = memories_by_instance.get(inst.id)
            if memory and memory.recent_actions:
                for action in memory.recent_actions:
                    if isinstance(action, str):
                        merged_actions[action] += 1
                    elif isinstance(action, dict) and "action_type" in action:
                        merged_actions[action["action_type"]] += 1

        behaviors.append(
            AgentBehaviorData(
                agent_profile_id=str(profile_id),
                agent_name=latest.agent_profile.name if latest.agent_profile else "Unknown",
                personality=latest.agent_profile.personality if latest.agent_profile else "",
                short_description=latest.agent_profile.short_description
                if latest.agent_profile
                else None,
                notes_written=total_notes,
                ratings_given=total_ratings,
                turn_count=total_turns,
                state=latest.state,
                display_model=humanize_model_name(
                    latest.agent_profile.model_name if latest.agent_profile else ""
                ),
                helpfulness_trend=merged_trend,
                action_distribution=dict(merged_actions),
            )
        )

    return behaviors


async def compute_note_quality(
    instances: list[SimAgentInstance],
    db: AsyncSession,
) -> NoteQualityData:
    user_profile_ids = [inst.user_profile_id for inst in instances if inst.turn_count > 0]

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


async def compute_detailed_notes(
    simulation_run_id: UUID,
    db: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_by: Literal["count", "has_score"] = "count",
    filter_classification: list[str] | None = None,
    filter_status: list[str] | None = None,
) -> tuple[list[DetailedNoteData], int]:
    instances = await _get_agent_instances(simulation_run_id, db)
    user_profile_ids = [inst.user_profile_id for inst in instances]

    if not user_profile_ids:
        return [], 0

    profile_to_instance: dict[UUID, SimAgentInstance] = {
        inst.user_profile_id: inst for inst in instances
    }

    base_filters = [
        Note.author_id.in_(user_profile_ids),
        Note.deleted_at.is_(None),
    ]
    if filter_classification:
        base_filters.append(Note.classification.in_(filter_classification))
    if filter_status:
        base_filters.append(Note.status.in_(filter_status))

    count_result = await db.execute(select(func.count(Note.id)).where(*base_filters))
    total = count_result.scalar() or 0

    if sort_by == "has_score":
        score_priority = case(
            (
                Note.status.in_(["CURRENTLY_RATED_HELPFUL", "CURRENTLY_RATED_NOT_HELPFUL"]),
                0,
            ),
            else_=1,
        )
        order_clauses = [score_priority, Note.created_at.desc()]
    else:
        order_clauses = [Note.created_at.desc()]

    notes_result = await db.execute(
        select(Note)
        .where(*base_filters)
        .options(*loaders.detailed())
        .order_by(*order_clauses)
        .offset(offset)
        .limit(limit)
    )
    notes = notes_result.scalars().all()

    rater_profile_ids = set()
    for note in notes:
        for rating in note.ratings:
            rater_profile_ids.add(rating.rater_id)

    detailed_notes: list[DetailedNoteData] = []
    for note in notes:
        author_inst = profile_to_instance.get(note.author_id)
        author_agent_name = "Unknown"
        author_agent_profile_id = ""
        if author_inst:
            author_agent_name = (
                author_inst.agent_profile.name if author_inst.agent_profile else "Unknown"
            )
            author_agent_profile_id = str(author_inst.agent_profile_id)

        rating_data_list: list[DetailedRatingData] = []
        for rating in note.ratings:
            rater_inst = profile_to_instance.get(rating.rater_id)
            rater_name = "Unknown"
            rater_inst_id = ""
            if rater_inst:
                rater_name = (
                    rater_inst.agent_profile.name if rater_inst.agent_profile else "Unknown"
                )
                rater_inst_id = str(rater_inst.agent_profile_id)

            rating_data_list.append(
                DetailedRatingData(
                    rater_agent_name=rater_name,
                    rater_agent_profile_id=rater_inst_id,
                    helpfulness_level=rating.helpfulness_level,
                    created_at=rating.created_at,
                )
            )

        msg_metadata = None
        if note.request and note.request.message_archive:
            msg_metadata = note.request.message_archive.message_metadata

        detailed_notes.append(
            DetailedNoteData(
                note_id=str(note.id),
                summary=note.summary,
                classification=note.classification,
                status=note.status,
                helpfulness_score=note.helpfulness_score,
                author_agent_name=author_agent_name,
                author_agent_profile_id=author_agent_profile_id,
                request_id=note.request_id,
                message_metadata=msg_metadata,
                created_at=note.created_at,
                ratings=rating_data_list,
            )
        )

    return detailed_notes, total


def _compute_classification_diversity(classifications: list[str]) -> float:
    if len(classifications) <= 1:
        return 0.0
    counter = Counter(classifications)
    max_count = max(counter.values())
    return 1.0 - (max_count / len(classifications))


def _compute_rating_spread(ratings_per_note: list[list[str]]) -> float:
    if not ratings_per_note:
        return 0.0
    spreads: list[float] = []
    for levels in ratings_per_note:
        if len(levels) <= 1:
            spreads.append(0.0)
            continue
        counter = Counter(levels)
        max_count = max(counter.values())
        spreads.append(1.0 - (max_count / len(levels)))
    return sum(spreads) / len(spreads) if spreads else 0.0


async def compute_request_variance(
    simulation_run_id: UUID,
    db: AsyncSession,
) -> list[DetailedRequestData]:
    instances = await _get_agent_instances(simulation_run_id, db)
    user_profile_ids = [inst.user_profile_id for inst in instances if inst.turn_count > 0]

    if not user_profile_ids:
        return []

    notes_result = await db.execute(
        select(Note)
        .where(
            Note.author_id.in_(user_profile_ids),
            Note.deleted_at.is_(None),
            Note.request_id.isnot(None),
        )
        .options(*loaders.ratings())
    )
    notes = list(notes_result.scalars().all())

    request_ids = {note.request_id for note in notes if note.request_id}

    request_result = await db.execute(
        select(Request).where(Request.id.in_(request_ids)).options(*loaders.request_with_archive())
    )
    requests_by_id: dict[UUID, Request] = {req.id: req for req in request_result.scalars().all()}

    notes_by_request: dict[UUID, list[Note]] = defaultdict(list)
    for note in notes:
        if note.request_id:
            notes_by_request[note.request_id].append(note)

    results: list[DetailedRequestData] = []
    for req_id in request_ids:
        req_notes = notes_by_request.get(req_id, [])
        req_obj = requests_by_id.get(req_id)

        content: str | None = None
        content_type: str | None = None
        if req_obj:
            content = req_obj.content
            if req_obj.message_archive:
                content_type = req_obj.message_archive.content_type

        classifications = [n.classification for n in req_notes]
        ratings_per_note = [[r.helpfulness_level for r in n.ratings] for n in req_notes]

        classification_diversity = _compute_classification_diversity(classifications)
        rating_spread = _compute_rating_spread(ratings_per_note)
        variance_score = round((classification_diversity + rating_spread) / 2.0, 4)

        results.append(
            DetailedRequestData(
                request_id=str(req_id),
                content=content,
                content_type=content_type,
                note_count=len(req_notes),
                variance_score=variance_score,
            )
        )

    results.sort(key=lambda r: r.variance_score, reverse=True)
    return results


async def compute_timeline(
    simulation_run_id: UUID,
    db: AsyncSession,
    bucket_size: str = "auto",
) -> TimelineAttributes:
    instances = await _get_agent_instances(simulation_run_id, db)
    user_profile_ids = [i.user_profile_id for i in instances]

    if not user_profile_ids:
        return TimelineAttributes(
            bucket_size=bucket_size, buckets=[], total_notes=0, total_ratings=0
        )

    run_result = await db.execute(
        select(SimulationRun).where(SimulationRun.id == simulation_run_id)
    )
    run = run_result.scalar_one()

    if bucket_size == "auto":
        duration = (run.completed_at or run.updated_at or run.created_at) - run.created_at
        bucket_size = "minute" if duration.total_seconds() < 3600 else "hour"

    if bucket_size not in ("minute", "hour"):
        raise ValueError(f"Invalid bucket_size: {bucket_size!r}. Must be 'minute' or 'hour'.")

    note_trunc = func.date_trunc(bucket_size, Note.created_at)
    note_rows = await db.execute(
        select(
            note_trunc.label("bucket"),
            Note.status,
            func.count().label("cnt"),
        )
        .where(Note.author_id.in_(user_profile_ids))
        .where(Note.deleted_at.is_(None))
        .group_by("bucket", Note.status)
        .order_by("bucket")
    )

    rating_trunc = func.date_trunc(bucket_size, Rating.created_at)
    rating_rows = await db.execute(
        select(
            rating_trunc.label("bucket"),
            Rating.helpfulness_level,
            func.count().label("cnt"),
        )
        .where(Rating.rater_id.in_(user_profile_ids))
        .group_by("bucket", Rating.helpfulness_level)
        .order_by("bucket")
    )

    buckets_map: dict[str, TimelineBucketData] = {}
    total_notes = 0
    for row in note_rows:
        ts = row.bucket.isoformat()
        if ts not in buckets_map:
            buckets_map[ts] = TimelineBucketData(timestamp=ts)
        buckets_map[ts].notes_by_status[row.status] = row.cnt
        total_notes += row.cnt

    total_ratings = 0
    for row in rating_rows:
        ts = row.bucket.isoformat()
        if ts not in buckets_map:
            buckets_map[ts] = TimelineBucketData(timestamp=ts)
        buckets_map[ts].ratings_by_level[row.helpfulness_level] = row.cnt
        total_ratings += row.cnt

    return TimelineAttributes(
        bucket_size=bucket_size,
        buckets=sorted(buckets_map.values(), key=lambda b: b.timestamp),
        total_notes=total_notes,
        total_ratings=total_ratings,
    )
