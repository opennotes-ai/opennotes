from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest


def _make_agent_instance(
    instance_id: UUID | None = None,
    profile_id: UUID | None = None,
    agent_profile_id: UUID | None = None,
    agent_name: str = "TestAgent",
    personality: str = "A default personality",
    short_description: str | None = None,
    turn_count: int = 0,
    state: str = "active",
) -> MagicMock:
    inst = MagicMock()
    inst.id = instance_id or uuid4()
    inst.user_profile_id = profile_id or uuid4()
    inst.agent_profile_id = agent_profile_id or uuid4()
    inst.agent_profile = MagicMock()
    inst.agent_profile.name = agent_name
    inst.agent_profile.personality = personality
    inst.agent_profile.short_description = short_description
    inst.turn_count = turn_count
    inst.state = state
    return inst


def _make_note(
    note_id: UUID | None = None,
    author_id: UUID | None = None,
    request_id: str | None = None,
    classification: str = "NOT_MISLEADING",
    status: str = "NEEDS_MORE_RATINGS",
    helpfulness_score: float = 0,
    ratings: list | None = None,
    created_at: datetime | None = None,
    message_metadata: dict | None = None,
) -> MagicMock:
    note = MagicMock()
    note.id = note_id or uuid4()
    note.author_id = author_id or uuid4()
    note.request_id = request_id
    note.summary = "Test summary"
    note.classification = classification
    note.status = status
    note.helpfulness_score = helpfulness_score
    note.ratings = ratings or []
    note.created_at = created_at or datetime(2026, 1, 1, tzinfo=UTC)
    note.deleted_at = None
    if message_metadata is not None:
        note.request = MagicMock()
        note.request.message_archive = MagicMock()
        note.request.message_archive.message_metadata = message_metadata
    else:
        note.request = None
    return note


def _make_rating(
    rater_id: UUID | None = None,
    helpfulness_level: str = "HELPFUL",
    created_at: datetime | None = None,
) -> MagicMock:
    rating = MagicMock()
    rating.id = uuid4()
    rating.rater_id = rater_id or uuid4()
    rating.helpfulness_level = helpfulness_level
    rating.created_at = created_at or datetime(2026, 1, 2, tzinfo=UTC)
    rating.rater = MagicMock()
    return rating


@pytest.mark.unit
class TestComputeDetailedNotes:
    @pytest.mark.asyncio
    async def test_empty_instances_returns_empty(self):
        from src.simulation.analysis import compute_detailed_notes

        mock_db = AsyncMock()
        sim_id = uuid4()

        with patch("src.simulation.analysis._get_agent_instances", return_value=[]):
            result, total = await compute_detailed_notes(sim_id, mock_db)

        assert result == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_returns_notes_with_author_info(self):
        from src.simulation.analysis import compute_detailed_notes

        sim_id = uuid4()
        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id, agent_name="Agent Alpha")

        note = _make_note(
            author_id=profile_id,
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            status="CURRENTLY_RATED_HELPFUL",
            helpfulness_score=75,
        )

        mock_db = AsyncMock()

        count_scalar = MagicMock()
        count_scalar.scalar.return_value = 1

        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]

        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        mock_db.execute = AsyncMock(side_effect=[count_scalar, notes_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result, total = await compute_detailed_notes(sim_id, mock_db)

        assert total == 1
        assert len(result) == 1
        assert result[0].author_agent_name == "Agent Alpha"
        assert result[0].author_agent_profile_id == str(inst.agent_profile_id)
        assert result[0].classification == "MISINFORMED_OR_POTENTIALLY_MISLEADING"
        assert result[0].helpfulness_score == 75

    @pytest.mark.asyncio
    async def test_maps_rater_to_agent_instance(self):
        from src.simulation.analysis import compute_detailed_notes

        sim_id = uuid4()
        author_profile_id = uuid4()
        rater_profile_id = uuid4()

        author_inst = _make_agent_instance(profile_id=author_profile_id, agent_name="Author Agent")
        rater_inst = _make_agent_instance(profile_id=rater_profile_id, agent_name="Rater Agent")

        rating = _make_rating(
            rater_id=rater_profile_id,
            helpfulness_level="NOT_HELPFUL",
        )

        note = _make_note(
            author_id=author_profile_id,
            ratings=[rating],
        )

        mock_db = AsyncMock()

        count_scalar = MagicMock()
        count_scalar.scalar.return_value = 1

        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]

        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        mock_db.execute = AsyncMock(side_effect=[count_scalar, notes_result])

        with patch(
            "src.simulation.analysis._get_agent_instances",
            return_value=[author_inst, rater_inst],
        ):
            result, total = await compute_detailed_notes(sim_id, mock_db)

        assert total == 1
        assert len(result) == 1
        assert len(result[0].ratings) == 1
        assert result[0].ratings[0].rater_agent_name == "Rater Agent"
        assert result[0].ratings[0].rater_agent_profile_id == str(rater_inst.agent_profile_id)
        assert result[0].ratings[0].helpfulness_level == "NOT_HELPFUL"

    @pytest.mark.asyncio
    async def test_unknown_rater_gets_unknown_name(self):
        from src.simulation.analysis import compute_detailed_notes

        sim_id = uuid4()
        author_profile_id = uuid4()
        unknown_rater_id = uuid4()

        author_inst = _make_agent_instance(profile_id=author_profile_id, agent_name="Author")

        rating = _make_rating(rater_id=unknown_rater_id)
        note = _make_note(author_id=author_profile_id, ratings=[rating])

        mock_db = AsyncMock()

        count_scalar = MagicMock()
        count_scalar.scalar.return_value = 1

        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]

        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        mock_db.execute = AsyncMock(side_effect=[count_scalar, notes_result])

        with patch(
            "src.simulation.analysis._get_agent_instances",
            return_value=[author_inst],
        ):
            result, _total = await compute_detailed_notes(sim_id, mock_db)

        assert result[0].ratings[0].rater_agent_name == "Unknown"
        assert result[0].ratings[0].rater_agent_profile_id == ""

    @pytest.mark.asyncio
    async def test_includes_request_id(self):
        from src.simulation.analysis import compute_detailed_notes

        sim_id = uuid4()
        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id)

        note = _make_note(author_id=profile_id, request_id="req-42")

        mock_db = AsyncMock()

        count_scalar = MagicMock()
        count_scalar.scalar.return_value = 1

        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]

        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        mock_db.execute = AsyncMock(side_effect=[count_scalar, notes_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result, _total = await compute_detailed_notes(sim_id, mock_db)

        assert result[0].request_id == "req-42"

    @pytest.mark.asyncio
    async def test_pagination_offset_and_limit(self):
        from src.simulation.analysis import compute_detailed_notes

        sim_id = uuid4()
        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id)

        note = _make_note(author_id=profile_id)

        mock_db = AsyncMock()

        count_scalar = MagicMock()
        count_scalar.scalar.return_value = 50

        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]

        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        mock_db.execute = AsyncMock(side_effect=[count_scalar, notes_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result, total = await compute_detailed_notes(sim_id, mock_db, offset=10, limit=5)

        assert total == 50
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_includes_message_metadata(self):
        from src.simulation.analysis import compute_detailed_notes

        sim_id = uuid4()
        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id)

        metadata = {"source_url": "https://example.com/article", "platform": "discord"}
        note = _make_note(
            author_id=profile_id,
            request_id="req-meta",
            message_metadata=metadata,
        )

        mock_db = AsyncMock()

        count_scalar = MagicMock()
        count_scalar.scalar.return_value = 1

        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]

        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        mock_db.execute = AsyncMock(side_effect=[count_scalar, notes_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result, _total = await compute_detailed_notes(sim_id, mock_db)

        assert result[0].message_metadata == metadata
        assert result[0].message_metadata["source_url"] == "https://example.com/article"

    @pytest.mark.asyncio
    async def test_message_metadata_none_when_no_request(self):
        from src.simulation.analysis import compute_detailed_notes

        sim_id = uuid4()
        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id)

        note = _make_note(author_id=profile_id)

        mock_db = AsyncMock()

        count_scalar = MagicMock()
        count_scalar.scalar.return_value = 1

        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]

        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        mock_db.execute = AsyncMock(side_effect=[count_scalar, notes_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result, _total = await compute_detailed_notes(sim_id, mock_db)

        assert result[0].message_metadata is None


@pytest.mark.unit
class TestComputeAgentBehaviorMetrics:
    @pytest.mark.asyncio
    async def test_includes_personality(self):
        from src.simulation.analysis import compute_agent_behavior_metrics

        profile_id = uuid4()
        inst = _make_agent_instance(
            profile_id=profile_id,
            agent_name="Skeptic Agent",
            personality="A skeptical fact-checker who questions everything.",
            turn_count=3,
            state="active",
        )

        mock_db = AsyncMock()

        notes_count = MagicMock()
        notes_count.all.return_value = []

        ratings_count = MagicMock()
        ratings_count.all.return_value = []

        ratings_trend = MagicMock()
        ratings_trend.all.return_value = []

        memories_scalars = MagicMock()
        memories_scalars.all.return_value = []
        memories_result = MagicMock()
        memories_result.scalars.return_value = memories_scalars

        mock_db.execute = AsyncMock(
            side_effect=[notes_count, ratings_count, ratings_trend, memories_result]
        )

        result = await compute_agent_behavior_metrics([inst], mock_db)

        assert len(result) == 1
        assert result[0].personality == "A skeptical fact-checker who questions everything."

    @pytest.mark.asyncio
    async def test_personality_empty_when_no_profile(self):
        from src.simulation.analysis import compute_agent_behavior_metrics

        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id, turn_count=1)
        inst.agent_profile = None

        mock_db = AsyncMock()

        notes_count = MagicMock()
        notes_count.all.return_value = []

        ratings_count = MagicMock()
        ratings_count.all.return_value = []

        ratings_trend = MagicMock()
        ratings_trend.all.return_value = []

        memories_scalars = MagicMock()
        memories_scalars.all.return_value = []
        memories_result = MagicMock()
        memories_result.scalars.return_value = memories_scalars

        mock_db.execute = AsyncMock(
            side_effect=[notes_count, ratings_count, ratings_trend, memories_result]
        )

        result = await compute_agent_behavior_metrics([inst], mock_db)

        assert len(result) == 1
        assert result[0].personality == ""
