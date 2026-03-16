from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _make_agent_instance(profile_id=None, agent_name="TestAgent", turn_count=10):
    inst = MagicMock()
    inst.id = uuid4()
    inst.user_profile_id = profile_id or uuid4()
    inst.turn_count = turn_count
    inst.agent_profile = MagicMock()
    inst.agent_profile.name = agent_name
    return inst


def _make_rating(helpfulness_level="HELPFUL"):
    r = MagicMock()
    r.id = uuid4()
    r.helpfulness_level = helpfulness_level
    return r


def _make_note(author_id=None, request_id=None, classification="NOT_MISLEADING", ratings=None):
    n = MagicMock()
    n.id = uuid4()
    n.author_id = author_id or uuid4()
    n.request_id = request_id
    n.classification = classification
    n.deleted_at = None
    n.ratings = ratings or []
    return n


def _make_request(request_id, content_text=None, content_url=None, content_type="text"):
    req = MagicMock()
    req.request_id = request_id
    ma = MagicMock()
    ma.content_type = content_type
    if content_type == "text":
        ma.get_content.return_value = content_text
        req.content = content_text
    else:
        ma.get_content.return_value = content_url
        req.content = content_url
    req.message_archive = ma
    return req


@pytest.mark.unit
class TestClassificationDiversity:
    def test_single_classification_returns_zero(self):
        from src.simulation.analysis import _compute_classification_diversity

        result = _compute_classification_diversity(["NOT_MISLEADING"])
        assert result == 0.0

    def test_uniform_classifications_returns_zero(self):
        from src.simulation.analysis import _compute_classification_diversity

        result = _compute_classification_diversity(
            ["NOT_MISLEADING", "NOT_MISLEADING", "NOT_MISLEADING"]
        )
        assert result == 0.0

    def test_even_split_returns_half(self):
        from src.simulation.analysis import _compute_classification_diversity

        result = _compute_classification_diversity(
            ["NOT_MISLEADING", "MISINFORMED_OR_POTENTIALLY_MISLEADING"]
        )
        assert result == 0.5

    def test_two_thirds_split(self):
        from src.simulation.analysis import _compute_classification_diversity

        result = _compute_classification_diversity(
            [
                "NOT_MISLEADING",
                "NOT_MISLEADING",
                "MISINFORMED_OR_POTENTIALLY_MISLEADING",
            ]
        )
        assert abs(result - (1.0 / 3.0)) < 0.01

    def test_empty_returns_zero(self):
        from src.simulation.analysis import _compute_classification_diversity

        result = _compute_classification_diversity([])
        assert result == 0.0


@pytest.mark.unit
class TestRatingSpread:
    def test_no_ratings_returns_zero(self):
        from src.simulation.analysis import _compute_rating_spread

        result = _compute_rating_spread([])
        assert result == 0.0

    def test_single_rating_per_note_returns_zero(self):
        from src.simulation.analysis import _compute_rating_spread

        result = _compute_rating_spread([["HELPFUL"], ["NOT_HELPFUL"]])
        assert result == 0.0

    def test_unanimous_ratings_returns_zero(self):
        from src.simulation.analysis import _compute_rating_spread

        result = _compute_rating_spread([["HELPFUL", "HELPFUL"], ["NOT_HELPFUL", "NOT_HELPFUL"]])
        assert result == 0.0

    def test_mixed_ratings_returns_positive(self):
        from src.simulation.analysis import _compute_rating_spread

        result = _compute_rating_spread([["HELPFUL", "NOT_HELPFUL"]])
        assert result == 0.5


@pytest.mark.unit
class TestComputeRequestVariance:
    @pytest.mark.asyncio
    async def test_empty_instances_returns_empty(self):
        from src.simulation.analysis import compute_request_variance

        mock_db = AsyncMock()
        with patch("src.simulation.analysis._get_agent_instances", return_value=[]):
            result = await compute_request_variance(uuid4(), mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_single_request_with_no_variance(self):
        from src.simulation.analysis import compute_request_variance

        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id)

        note = _make_note(
            author_id=profile_id,
            request_id="req-1",
            classification="NOT_MISLEADING",
            ratings=[_make_rating("HELPFUL")],
        )
        req = _make_request("req-1", content_text="Some claim text")

        mock_db = AsyncMock()
        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]
        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        req_scalars = MagicMock()
        req_scalars.all.return_value = [req]
        req_result = MagicMock()
        req_result.scalars.return_value = req_scalars

        mock_db.execute = AsyncMock(side_effect=[notes_result, req_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result = await compute_request_variance(uuid4(), mock_db)

        assert len(result) == 1
        assert result[0].request_id == "req-1"
        assert result[0].variance_score == 0.0
        assert result[0].content == "Some claim text"
        assert result[0].note_count == 1

    @pytest.mark.asyncio
    async def test_request_with_mixed_classifications(self):
        from src.simulation.analysis import compute_request_variance

        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id)

        note1 = _make_note(
            author_id=profile_id,
            request_id="req-1",
            classification="NOT_MISLEADING",
            ratings=[],
        )
        note2 = _make_note(
            author_id=profile_id,
            request_id="req-1",
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            ratings=[],
        )
        req = _make_request("req-1", content_text="Controversial claim")

        mock_db = AsyncMock()
        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note1, note2]
        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        req_scalars = MagicMock()
        req_scalars.all.return_value = [req]
        req_result = MagicMock()
        req_result.scalars.return_value = req_scalars

        mock_db.execute = AsyncMock(side_effect=[notes_result, req_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result = await compute_request_variance(uuid4(), mock_db)

        assert len(result) == 1
        assert result[0].variance_score > 0
        assert result[0].note_count == 2

    @pytest.mark.asyncio
    async def test_sorted_by_variance_descending(self):
        from src.simulation.analysis import compute_request_variance

        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id)

        note_low = _make_note(
            author_id=profile_id,
            request_id="req-low",
            classification="NOT_MISLEADING",
            ratings=[],
        )
        note_high1 = _make_note(
            author_id=profile_id,
            request_id="req-high",
            classification="NOT_MISLEADING",
            ratings=[_make_rating("HELPFUL"), _make_rating("NOT_HELPFUL")],
        )
        note_high2 = _make_note(
            author_id=profile_id,
            request_id="req-high",
            classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
            ratings=[_make_rating("NOT_HELPFUL")],
        )

        req_low = _make_request("req-low", content_text="Simple claim")
        req_high = _make_request("req-high", content_text="Contested claim")

        mock_db = AsyncMock()
        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note_low, note_high1, note_high2]
        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        req_scalars = MagicMock()
        req_scalars.all.return_value = [req_low, req_high]
        req_result = MagicMock()
        req_result.scalars.return_value = req_scalars

        mock_db.execute = AsyncMock(side_effect=[notes_result, req_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result = await compute_request_variance(uuid4(), mock_db)

        assert len(result) == 2
        assert result[0].request_id == "req-high"
        assert result[1].request_id == "req-low"
        assert result[0].variance_score > result[1].variance_score

    @pytest.mark.asyncio
    async def test_includes_content_type(self):
        from src.simulation.analysis import compute_request_variance

        profile_id = uuid4()
        inst = _make_agent_instance(profile_id=profile_id)

        note = _make_note(author_id=profile_id, request_id="req-url")
        req = _make_request(
            "req-url", content_url="https://example.com/image.png", content_type="image"
        )

        mock_db = AsyncMock()
        notes_scalars = MagicMock()
        notes_scalars.all.return_value = [note]
        notes_result = MagicMock()
        notes_result.scalars.return_value = notes_scalars

        req_scalars = MagicMock()
        req_scalars.all.return_value = [req]
        req_result = MagicMock()
        req_result.scalars.return_value = req_scalars

        mock_db.execute = AsyncMock(side_effect=[notes_result, req_result])

        with patch("src.simulation.analysis._get_agent_instances", return_value=[inst]):
            result = await compute_request_variance(uuid4(), mock_db)

        assert result[0].content_type == "image"
        assert result[0].content == "https://example.com/image.png"
