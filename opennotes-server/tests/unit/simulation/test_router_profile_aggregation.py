from unittest.mock import MagicMock
from uuid import uuid4


def _make_instance(*, agent_profile_id=None, state="active", deleted_at=None, turn_count=5):
    inst = MagicMock()
    inst.agent_profile_id = agent_profile_id or uuid4()
    inst.state = state
    inst.deleted_at = deleted_at
    inst.turn_count = turn_count
    return inst


def _count_active_agents(instances):
    active_profile_ids = {
        inst.agent_profile_id
        for inst in instances
        if inst.state == "active" and inst.deleted_at is None
    }
    return len(active_profile_ids)


class TestProgressCountsActiveByProfile:
    def test_two_instances_same_profile_counts_as_one(self):
        profile_id = uuid4()
        inst1 = _make_instance(agent_profile_id=profile_id)
        inst2 = _make_instance(agent_profile_id=profile_id)
        assert _count_active_agents([inst1, inst2]) == 1

    def test_two_instances_different_profiles_counts_as_two(self):
        inst1 = _make_instance(agent_profile_id=uuid4())
        inst2 = _make_instance(agent_profile_id=uuid4())
        assert _count_active_agents([inst1, inst2]) == 2

    def test_deleted_instance_not_counted(self):
        profile_id = uuid4()
        active = _make_instance(agent_profile_id=profile_id)
        deleted = _make_instance(agent_profile_id=uuid4(), deleted_at="2026-01-01T00:00:00Z")
        assert _count_active_agents([active, deleted]) == 1

    def test_inactive_instance_not_counted(self):
        profile_id = uuid4()
        active = _make_instance(agent_profile_id=profile_id, state="active")
        stopped = _make_instance(agent_profile_id=uuid4(), state="stopped")
        assert _count_active_agents([active, stopped]) == 1

    def test_empty_instances(self):
        assert _count_active_agents([]) == 0

    def test_all_deleted(self):
        inst = _make_instance(deleted_at="2026-01-01T00:00:00Z")
        assert _count_active_agents([inst]) == 0
