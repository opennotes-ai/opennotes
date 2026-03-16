from __future__ import annotations

from uuid import uuid4

import pyarrow as pa

from src.simulation.scoring_integration import _build_profile_remap, _remap_tables


class TestBuildProfileRemap:
    def test_maps_user_profile_to_agent_profile(self):
        profile_a = uuid4()
        user1, user2 = uuid4(), uuid4()

        instances = [
            _fake_instance(user1, profile_a, turn_count=10),
            _fake_instance(user2, profile_a, turn_count=5),
        ]

        remap = _build_profile_remap(instances)
        assert remap == {str(user1): str(profile_a), str(user2): str(profile_a)}

    def test_skips_zero_turn_instances(self):
        profile_a = uuid4()
        user1, user2 = uuid4(), uuid4()

        instances = [
            _fake_instance(user1, profile_a, turn_count=10),
            _fake_instance(user2, profile_a, turn_count=0),
        ]

        remap = _build_profile_remap(instances)
        assert str(user1) in remap
        assert str(user2) not in remap

    def test_empty_instances(self):
        remap = _build_profile_remap([])
        assert remap == {}


class TestRemapTables:
    def test_remaps_rater_id_and_author_id(self):
        profile_a = uuid4()
        user1, user2 = uuid4(), uuid4()
        note_id = uuid4()

        remap = {str(user1): str(profile_a), str(user2): str(profile_a)}

        ratings_table = pa.table(
            {
                "id": [str(uuid4()), str(uuid4())],
                "note_id": [str(note_id), str(note_id)],
                "rater_id": [str(user1), str(user2)],
                "helpfulness_level": ["HELPFUL", "NOT_HELPFUL"],
                "created_at": [None, None],
            }
        )

        notes_table = pa.table(
            {
                "id": [str(note_id)],
                "author_id": [str(user1)],
                "classification": ["MISINFORMATION"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [None],
            }
        )

        new_ratings, new_notes, _participants = _remap_tables(ratings_table, notes_table, remap)

        rater_ids = new_ratings.column("rater_id").to_pylist()
        assert all(rid == str(profile_a) for rid in rater_ids), (
            f"Expected all rater_ids to be {profile_a}, got {rater_ids}"
        )

        author_ids = new_notes.column("author_id").to_pylist()
        assert all(aid == str(profile_a) for aid in author_ids), (
            f"Expected all author_ids to be {profile_a}, got {author_ids}"
        )

    def test_participant_ids_use_agent_profile_ids(self):
        profile_a = uuid4()
        profile_b = uuid4()
        user1, user2 = uuid4(), uuid4()

        remap = {str(user1): str(profile_a), str(user2): str(profile_b)}

        ratings_table = pa.table(
            {
                "id": [str(uuid4())],
                "note_id": [str(uuid4())],
                "rater_id": [str(user1)],
                "helpfulness_level": ["HELPFUL"],
                "created_at": [None],
            }
        )

        notes_table = pa.table(
            {
                "id": [str(uuid4())],
                "author_id": [str(user2)],
                "classification": ["MISINFORMATION"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [None],
            }
        )

        _, _, participants = _remap_tables(ratings_table, notes_table, remap)

        participant_list = participants.to_pylist()
        assert str(profile_a) in participant_list
        assert str(profile_b) in participant_list
        assert str(user1) not in participant_list
        assert str(user2) not in participant_list

    def test_unmapped_ids_pass_through(self):
        unmapped_user = uuid4()

        ratings_table = pa.table(
            {
                "id": [str(uuid4())],
                "note_id": [str(uuid4())],
                "rater_id": [str(unmapped_user)],
                "helpfulness_level": ["HELPFUL"],
                "created_at": [None],
            }
        )

        notes_table = pa.table(
            {
                "id": [str(uuid4())],
                "author_id": [str(unmapped_user)],
                "classification": ["MISINFORMATION"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [None],
            }
        )

        new_ratings, new_notes, _ = _remap_tables(ratings_table, notes_table, {})

        assert new_ratings.column("rater_id").to_pylist() == [str(unmapped_user)]
        assert new_notes.column("author_id").to_pylist() == [str(unmapped_user)]

    def test_multi_instance_same_profile_deduplicates(self):
        profile_a = uuid4()
        user1, user2 = uuid4(), uuid4()

        remap = {str(user1): str(profile_a), str(user2): str(profile_a)}

        ratings_table = pa.table(
            {
                "id": [str(uuid4()), str(uuid4())],
                "note_id": [str(uuid4()), str(uuid4())],
                "rater_id": [str(user1), str(user2)],
                "helpfulness_level": ["HELPFUL", "NOT_HELPFUL"],
                "created_at": [None, None],
            }
        )

        notes_table = pa.table(
            {
                "id": [str(uuid4())],
                "author_id": [str(user1)],
                "classification": ["MISINFORMATION"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [None],
            }
        )

        new_ratings, new_notes, participants = _remap_tables(ratings_table, notes_table, remap)

        rater_ids = new_ratings.column("rater_id").to_pylist()
        assert all(rid == str(profile_a) for rid in rater_ids)

        author_ids = new_notes.column("author_id").to_pylist()
        assert all(aid == str(profile_a) for aid in author_ids)

        participant_list = participants.to_pylist()
        assert participant_list.count(str(profile_a)) == 1

    def test_empty_remap_preserves_original(self):
        user1 = uuid4()
        note_id = uuid4()

        ratings_table = pa.table(
            {
                "id": [str(uuid4())],
                "note_id": [str(note_id)],
                "rater_id": [str(user1)],
                "helpfulness_level": ["HELPFUL"],
                "created_at": [None],
            }
        )

        notes_table = pa.table(
            {
                "id": [str(note_id)],
                "author_id": [str(user1)],
                "classification": ["MISINFORMATION"],
                "status": ["NEEDS_MORE_RATINGS"],
                "created_at": [None],
            }
        )

        new_ratings, new_notes, participants = _remap_tables(ratings_table, notes_table, {})

        assert new_ratings.column("rater_id").to_pylist() == [str(user1)]
        assert new_notes.column("author_id").to_pylist() == [str(user1)]
        assert str(user1) in participants.to_pylist()


def _fake_instance(user_profile_id, agent_profile_id, turn_count=10):
    class FakeInstance:
        pass

    inst = FakeInstance()
    inst.user_profile_id = user_profile_id
    inst.agent_profile_id = agent_profile_id
    inst.turn_count = turn_count
    return inst
