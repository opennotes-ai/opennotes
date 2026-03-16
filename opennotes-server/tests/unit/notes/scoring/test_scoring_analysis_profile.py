from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.notes.scoring.analysis import _resolve_note_metadata, _resolve_rater_identities


def _make_sim_agent(agent_id, name, personality):
    agent = MagicMock()
    agent.id = agent_id
    agent.name = name
    agent.personality = personality
    return agent


def _make_sim_agent_instance(user_profile_id, agent_name, personality):
    inst = MagicMock()
    inst.user_profile_id = user_profile_id
    agent_profile = MagicMock()
    agent_profile.name = agent_name
    agent_profile.personality = personality
    inst.agent_profile = agent_profile
    return inst


def _make_note(
    note_id, author_id, status="CURRENTLY_RATED_HELPFUL", classification="NOT_MISLEADING"
):
    note = MagicMock()
    note.id = note_id
    note.status = status
    note.classification = classification
    note.author_id = author_id
    return note


def _mock_db_execute(*results_sequence):
    db = AsyncMock()
    side_effects = []
    for items in results_sequence:
        result = MagicMock()
        result.scalars.return_value.all.return_value = items
        side_effects.append(result)
    db.execute = AsyncMock(side_effect=side_effects)
    return db


class TestResolveRaterIdentitiesNewFormat:
    @pytest.mark.anyio
    async def test_agent_profile_id_resolves_to_agent(self):
        agent_id = uuid4()
        community_id = uuid4()
        agent = _make_sim_agent(agent_id, "Agent_Alpha", "skeptical fact-checker")

        db = _mock_db_execute(
            [agent],
            [],
        )

        result = await _resolve_rater_identities([str(agent_id)], community_id, db)

        assert result[str(agent_id)]["agent_name"] == "Agent_Alpha"
        assert result[str(agent_id)]["personality"] == "skeptical fact-checker"

    @pytest.mark.anyio
    async def test_unknown_id_returns_none_fields(self):
        unknown_id = uuid4()
        community_id = uuid4()

        db = _mock_db_execute(
            [],
            [],
        )

        result = await _resolve_rater_identities([str(unknown_id)], community_id, db)

        assert result[str(unknown_id)]["agent_name"] is None
        assert result[str(unknown_id)]["personality"] is None


class TestResolveRaterIdentitiesLegacyFormat:
    @pytest.mark.anyio
    async def test_user_profile_id_resolves_via_instance(self):
        user_profile_id = uuid4()
        community_id = uuid4()
        inst = _make_sim_agent_instance(user_profile_id, "Agent_Beta", "trusting")

        db = _mock_db_execute(
            [],
            [inst],
        )

        result = await _resolve_rater_identities([str(user_profile_id)], community_id, db)

        assert result[str(user_profile_id)]["agent_name"] == "Agent_Beta"
        assert result[str(user_profile_id)]["personality"] == "trusting"


class TestResolveRaterIdentitiesMixed:
    @pytest.mark.anyio
    async def test_mixed_new_and_legacy_ids(self):
        agent_id = uuid4()
        user_profile_id = uuid4()
        community_id = uuid4()

        agent = _make_sim_agent(agent_id, "Agent_Alpha", "skeptical")
        inst = _make_sim_agent_instance(user_profile_id, "Agent_Beta", "trusting")

        db = _mock_db_execute(
            [agent],
            [inst],
        )

        result = await _resolve_rater_identities(
            [str(agent_id), str(user_profile_id)], community_id, db
        )

        assert result[str(agent_id)]["agent_name"] == "Agent_Alpha"
        assert result[str(user_profile_id)]["agent_name"] == "Agent_Beta"

    @pytest.mark.anyio
    async def test_empty_rater_ids_returns_empty(self):
        result = await _resolve_rater_identities([], uuid4(), AsyncMock())
        assert result == {}

    @pytest.mark.anyio
    async def test_invalid_uuid_returns_none_fields(self):
        db = _mock_db_execute([], [])

        result = await _resolve_rater_identities(["not-a-uuid"], uuid4(), db)

        assert result.get("not-a-uuid", {}).get("agent_name") is None


class TestResolveNoteMetadataAuthorResolution:
    @pytest.mark.anyio
    async def test_author_resolved_via_sim_agent_direct(self):
        note_id = uuid4()
        author_agent_id = uuid4()
        community_id = uuid4()

        note = _make_note(note_id, author_agent_id)
        agent = _make_sim_agent(author_agent_id, "Author_Agent", "analytical")

        db = _mock_db_execute(
            [note],
            [agent],
            [],
        )

        result = await _resolve_note_metadata([str(note_id)], community_id, db)

        assert result[str(note_id)]["author_agent_name"] == "Author_Agent"

    @pytest.mark.anyio
    async def test_author_resolved_via_legacy_instance(self):
        note_id = uuid4()
        author_profile_id = uuid4()
        community_id = uuid4()

        note = _make_note(note_id, author_profile_id)
        inst = _make_sim_agent_instance(author_profile_id, "Legacy_Author", "creative")

        db = _mock_db_execute(
            [note],
            [],
            [inst],
        )

        result = await _resolve_note_metadata([str(note_id)], community_id, db)

        assert result[str(note_id)]["author_agent_name"] == "Legacy_Author"

    @pytest.mark.anyio
    async def test_empty_note_ids_returns_empty(self):
        result = await _resolve_note_metadata([], uuid4(), AsyncMock())
        assert result == {}
