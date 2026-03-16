from unittest.mock import MagicMock
from uuid import uuid4

from src.simulation.analysis import build_profile_aggregation_map, group_instances_by_profile


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
