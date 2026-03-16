from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.simulation.analysis import (
    build_profile_aggregation_map,
    compute_agent_behavior_metrics,
    compute_agent_profiles,
    compute_consensus_metrics,
    compute_detailed_notes,
    compute_note_quality,
    compute_rating_distribution,
    compute_request_variance,
    group_instances_by_profile,
)


def _make_instance(
    *,
    agent_profile_id=None,
    user_profile_id=None,
    turn_count=5,
    state="idle",
    name="Agent",
    personality="nice",
    model_name="gpt-4",
    memory_compaction_strategy="sliding_window",
):
    agent_profile_id = agent_profile_id or uuid4()
    user_profile_id = user_profile_id or uuid4()
    inst = MagicMock()
    inst.id = uuid4()
    inst.agent_profile_id = agent_profile_id
    inst.user_profile_id = user_profile_id
    inst.turn_count = turn_count
    inst.state = state
    inst.simulation_run_id = uuid4()
    profile = MagicMock()
    profile.name = name
    profile.personality = personality
    profile.short_description = None
    profile.model_name = model_name
    profile.memory_compaction_strategy = memory_compaction_strategy
    inst.agent_profile = profile
    return inst


def _scalars_all(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def _rows_all(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


class TestBuildProfileAggregationMap:
    def test_single_instance_per_profile(self):
        profile_id = uuid4()
        inst = MagicMock()
        inst.user_profile_id = uuid4()
        inst.agent_profile_id = profile_id
        inst.turn_count = 5
        result = build_profile_aggregation_map([inst])
        assert result[inst.user_profile_id] == profile_id

    def test_multi_instance_same_profile(self):
        profile_id = uuid4()
        inst1 = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_id, turn_count=10)
        inst2 = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_id, turn_count=5)
        result = build_profile_aggregation_map([inst1, inst2])
        assert result[inst1.user_profile_id] == profile_id
        assert result[inst2.user_profile_id] == profile_id
        assert len(result) == 2

    def test_zero_activity_filtered(self):
        inst = MagicMock(user_profile_id=uuid4(), agent_profile_id=uuid4(), turn_count=0)
        result = build_profile_aggregation_map([inst])
        assert inst.user_profile_id not in result
        assert len(result) == 0

    def test_empty_list(self):
        result = build_profile_aggregation_map([])
        assert result == {}

    def test_mixed_zero_and_nonzero(self):
        profile_a = uuid4()
        inst_active = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_a, turn_count=3)
        inst_zero = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_a, turn_count=0)
        result = build_profile_aggregation_map([inst_active, inst_zero])
        assert inst_active.user_profile_id in result
        assert inst_zero.user_profile_id not in result
        assert len(result) == 1


class TestGroupInstancesByProfile:
    def test_groups_by_profile_id(self):
        profile_a = uuid4()
        profile_b = uuid4()
        inst1 = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_a, turn_count=10)
        inst2 = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_a, turn_count=5)
        inst3 = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_b, turn_count=8)
        result = group_instances_by_profile([inst1, inst2, inst3])
        assert len(result[profile_a]) == 2
        assert len(result[profile_b]) == 1

    def test_excludes_zero_activity(self):
        profile_a = uuid4()
        inst_active = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_a, turn_count=5)
        inst_zero = MagicMock(user_profile_id=uuid4(), agent_profile_id=profile_a, turn_count=0)
        result = group_instances_by_profile([inst_active, inst_zero])
        assert len(result[profile_a]) == 1
        assert inst_active in result[profile_a]

    def test_empty_list(self):
        result = group_instances_by_profile([])
        assert result == {}


class TestComputeAgentProfilesAggregation:
    @pytest.mark.asyncio
    async def test_groups_instances_by_profile(self):
        profile_id = uuid4()
        inst1 = _make_instance(agent_profile_id=profile_id, turn_count=10, name="Alice")
        inst2 = _make_instance(agent_profile_id=profile_id, turn_count=5, name="Alice")

        mem = MagicMock()
        mem.agent_instance_id = inst1.id
        mem.token_count = 500
        mem.recent_actions = ["rate"]
        mem.compaction_strategy = "sliding_window"
        mem.message_history = [{"role": "user", "content": "hi"}]

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([inst1, inst2]),
                _scalars_all([mem]),
            ]
        )

        result = await compute_agent_profiles(uuid4(), db)

        assert len(result) == 1
        assert result[0].agent_profile_id == str(profile_id)
        assert result[0].turn_count == 15

    @pytest.mark.asyncio
    async def test_uses_latest_instance_memory(self):
        profile_id = uuid4()
        inst1 = _make_instance(agent_profile_id=profile_id, turn_count=3)
        inst2 = _make_instance(agent_profile_id=profile_id, turn_count=10)

        mem1 = MagicMock()
        mem1.agent_instance_id = inst1.id
        mem1.token_count = 100
        mem1.recent_actions = ["old_action"]
        mem1.compaction_strategy = "old"
        mem1.message_history = [{"role": "user", "content": "old"}]

        mem2 = MagicMock()
        mem2.agent_instance_id = inst2.id
        mem2.token_count = 500
        mem2.recent_actions = ["new_action"]
        mem2.compaction_strategy = "new"
        mem2.message_history = [{"role": "user", "content": "new"}]

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([inst1, inst2]),
                _scalars_all([mem1, mem2]),
            ]
        )

        result = await compute_agent_profiles(uuid4(), db)

        assert len(result) == 1
        assert result[0].token_count == 500
        assert result[0].recent_actions == ["new_action"]

    @pytest.mark.asyncio
    async def test_filters_zero_activity(self):
        profile_id = uuid4()
        inst_active = _make_instance(agent_profile_id=profile_id, turn_count=5)
        inst_zero = _make_instance(agent_profile_id=profile_id, turn_count=0)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([inst_active, inst_zero]),
                _scalars_all([]),
            ]
        )

        result = await compute_agent_profiles(uuid4(), db)

        assert len(result) == 1
        assert result[0].turn_count == 5


class TestComputeRatingDistributionAggregation:
    @pytest.mark.asyncio
    async def test_aggregates_ratings_by_profile(self):
        profile_id = uuid4()
        inst1 = _make_instance(agent_profile_id=profile_id, turn_count=5, name="Bob")
        inst2 = _make_instance(agent_profile_id=profile_id, turn_count=3, name="Bob")

        overall_rows = [("HELPFUL", 5), ("NOT_HELPFUL", 2)]
        per_agent_rows = [
            (inst1.user_profile_id, "HELPFUL", 3),
            (inst1.user_profile_id, "NOT_HELPFUL", 1),
            (inst2.user_profile_id, "HELPFUL", 2),
            (inst2.user_profile_id, "NOT_HELPFUL", 1),
        ]

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _rows_all(overall_rows),
                _rows_all(per_agent_rows),
            ]
        )

        result = await compute_rating_distribution(uuid4(), [inst1, inst2], db)

        assert len(result.per_agent) == 1
        agent_data = result.per_agent[0]
        assert agent_data.agent_profile_id == str(profile_id)
        assert agent_data.distribution["HELPFUL"] == 5
        assert agent_data.distribution["NOT_HELPFUL"] == 2
        assert agent_data.total == 7

    @pytest.mark.asyncio
    async def test_filters_zero_activity(self):
        profile_id = uuid4()
        inst_active = _make_instance(agent_profile_id=profile_id, turn_count=5, name="Bob")
        inst_zero = _make_instance(agent_profile_id=profile_id, turn_count=0, name="Bob")

        overall_rows = [("HELPFUL", 3)]
        per_agent_rows = [
            (inst_active.user_profile_id, "HELPFUL", 3),
        ]

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _rows_all(overall_rows),
                _rows_all(per_agent_rows),
            ]
        )

        result = await compute_rating_distribution(uuid4(), [inst_active, inst_zero], db)

        assert len(result.per_agent) == 1


class TestComputeAgentBehaviorMetricsAggregation:
    @pytest.mark.asyncio
    async def test_sums_notes_ratings_turns_per_profile(self):
        profile_id = uuid4()
        inst1 = _make_instance(agent_profile_id=profile_id, turn_count=10, name="Carol")
        inst2 = _make_instance(agent_profile_id=profile_id, turn_count=5, name="Carol")

        notes_rows = [
            (inst1.user_profile_id, 3),
            (inst2.user_profile_id, 2),
        ]
        ratings_rows = [
            (inst1.user_profile_id, 7),
            (inst2.user_profile_id, 4),
        ]
        trends_rows = [
            (inst1.user_profile_id, "HELPFUL"),
            (inst1.user_profile_id, "NOT_HELPFUL"),
            (inst2.user_profile_id, "HELPFUL"),
        ]

        mem1 = MagicMock()
        mem1.agent_instance_id = inst1.id
        mem1.recent_actions = ["rate", "rate"]

        mem2 = MagicMock()
        mem2.agent_instance_id = inst2.id
        mem2.recent_actions = ["write_note"]

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _rows_all(notes_rows),
                _rows_all(ratings_rows),
                _rows_all(trends_rows),
                _scalars_all([mem1, mem2]),
            ]
        )

        result = await compute_agent_behavior_metrics([inst1, inst2], db)

        assert len(result) == 1
        behavior = result[0]
        assert behavior.agent_profile_id == str(profile_id)
        assert behavior.notes_written == 5
        assert behavior.ratings_given == 11
        assert behavior.turn_count == 15
        assert behavior.helpfulness_trend == ["HELPFUL", "NOT_HELPFUL", "HELPFUL"]
        assert behavior.action_distribution == {"rate": 2, "write_note": 1}

    @pytest.mark.asyncio
    async def test_filters_zero_activity(self):
        profile_id = uuid4()
        inst_active = _make_instance(agent_profile_id=profile_id, turn_count=5, name="Dan")
        inst_zero = _make_instance(agent_profile_id=profile_id, turn_count=0, name="Dan")

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _rows_all([(inst_active.user_profile_id, 1)]),
                _rows_all([(inst_active.user_profile_id, 2)]),
                _rows_all([]),
                _scalars_all([]),
            ]
        )

        result = await compute_agent_behavior_metrics([inst_active, inst_zero], db)

        assert len(result) == 1
        assert result[0].turn_count == 5


class TestComputeDetailedNotesBugFix:
    @pytest.mark.asyncio
    async def test_rater_uses_agent_profile_id_not_instance_id(self):
        profile_id = uuid4()
        inst = _make_instance(agent_profile_id=profile_id, turn_count=5, name="Eve")

        rating = MagicMock()
        rating.rater_id = inst.user_profile_id
        rating.helpfulness_level = "HELPFUL"
        rating.created_at = MagicMock()

        note = MagicMock()
        note.id = uuid4()
        note.summary = "test"
        note.classification = "MISINFORMED"
        note.status = "NEEDS_MORE_RATINGS"
        note.helpfulness_score = 0.0
        note.author_id = inst.user_profile_id
        note.request_id = None
        note.request = None
        note.created_at = MagicMock()
        note.ratings = [rating]
        note.deleted_at = None

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([inst]),
                _scalar(1),
                _scalars_all([note]),
            ]
        )

        result, _total = await compute_detailed_notes(uuid4(), db)

        assert len(result) == 1
        rating_data = result[0].ratings[0]
        assert rating_data.rater_agent_profile_id == str(profile_id)
        assert rating_data.rater_agent_profile_id != str(inst.id)


class TestComputeNoteQualityFiltersZeroActivity:
    @pytest.mark.asyncio
    async def test_excludes_zero_turn_instances(self):
        inst_active = _make_instance(turn_count=5)
        inst_zero = _make_instance(turn_count=0)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar(0.75),
                _rows_all([("NEEDS_MORE_RATINGS", 2)]),
                _rows_all([("MISINFORMED", 2)]),
            ]
        )

        result = await compute_note_quality([inst_active, inst_zero], db)

        assert result.avg_helpfulness_score == 0.75
        calls = db.execute.call_args_list
        assert len(calls) == 3


class TestComputeConsensusMetricsFiltersZeroActivity:
    @pytest.mark.asyncio
    async def test_excludes_zero_turn_instances(self):
        inst_active = _make_instance(turn_count=5)
        inst_zero = _make_instance(turn_count=0)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _rows_all([]),
                _scalar(0),
            ]
        )

        result = await compute_consensus_metrics([inst_active, inst_zero], db)

        assert result.total_notes_rated == 0


class TestComputeRequestVarianceFiltersZeroActivity:
    @pytest.mark.asyncio
    async def test_excludes_zero_turn_instances(self):
        inst_active = _make_instance(turn_count=5)
        inst_zero = _make_instance(turn_count=0)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all([inst_active, inst_zero]),
                _scalars_all([]),
                _scalars_all([]),
            ]
        )

        result = await compute_request_variance(uuid4(), db)

        assert result == []
