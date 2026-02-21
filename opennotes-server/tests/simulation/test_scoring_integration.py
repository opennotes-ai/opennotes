from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.notes.scoring.tier_config import ScoringTier
from src.notes.scoring_schemas import NoteScoreResponse, ScoreConfidence
from src.simulation.scoring_integration import (
    CoverageResult,
    ScoringMetrics,
    ScoringRunResult,
    check_scoring_coverage,
    get_scoring_metrics,
    trigger_scoring_for_simulation,
)


def _make_run(community_server_id=None, metrics=None):
    run = MagicMock()
    run.id = uuid4()
    run.community_server_id = community_server_id or uuid4()
    run.metrics = metrics if metrics is not None else {}
    return run


def _make_note(note_id=None, community_server_id=None, ratings=None, status="NEEDS_MORE_RATINGS"):
    note = MagicMock()
    note.id = note_id or uuid4()
    note.community_server_id = community_server_id or uuid4()
    note.ratings = ratings or []
    note.status = status
    note.helpfulness_score = 0
    note.updated_at = None
    note.created_at = MagicMock()
    note.request = None
    return note


def _make_rating(helpfulness_level="HELPFUL"):
    rating = MagicMock()
    rating.helpfulness_level = helpfulness_level
    return rating


def _mock_db_for_trigger(run, note_count, notes):
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = note_count

    notes_result = MagicMock()
    notes_scalars = MagicMock()
    notes_scalars.all.return_value = notes
    notes_result.scalars.return_value = notes_scalars

    db.execute = AsyncMock(side_effect=[count_result, notes_result, None])
    db.commit = AsyncMock()
    return db


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_with_no_notes():
    run = _make_run()
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = 0
    db.execute = AsyncMock(return_value=count_result)
    db.commit = AsyncMock()

    result = await trigger_scoring_for_simulation(run.id, db)

    assert result.scores_computed == 0
    assert result.tier == ScoringTier.MINIMAL
    assert result.scorer_type == "none"
    assert result.note_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_not_found():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await trigger_scoring_for_simulation(uuid4(), db)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_uses_existing_pipeline():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    ratings = [_make_rating("HELPFUL") for _ in range(6)]
    note = _make_note(community_server_id=cs_id, ratings=ratings)

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.85,
        confidence=ScoreConfidence.STANDARD,
        algorithm="bayesian_average_tier0",
        rating_count=6,
        tier=0,
        tier_name="Minimal",
        calculated_at=None,
        content=None,
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = 5

    notes_result = MagicMock()
    notes_scalars = MagicMock()
    notes_scalars.all.return_value = [note]
    notes_result.scalars.return_value = notes_scalars

    update_result = MagicMock()

    db.execute = AsyncMock(side_effect=[count_result, notes_result, update_result])
    db.commit = AsyncMock()

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ) as mock_calc,
    ):
        mock_factory = MagicMock()
        mock_scorer = MagicMock()
        mock_factory.get_scorer.return_value = mock_scorer
        mock_factory_cls.return_value = mock_factory

        result = await trigger_scoring_for_simulation(run.id, db)

    assert result.scores_computed == 1
    assert result.tier == ScoringTier.MINIMAL
    assert result.note_count == 5
    mock_factory.get_scorer.assert_called_once_with(str(cs_id), 5)
    mock_calc.assert_called_once_with(note, 5, mock_scorer)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_updates_run_metrics():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id, metrics={})
    note = _make_note(community_server_id=cs_id, ratings=[_make_rating()])

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.7,
        confidence=ScoreConfidence.PROVISIONAL,
        algorithm="bayesian_average_tier0",
        rating_count=1,
        tier=0,
        tier_name="Minimal",
        calculated_at=None,
        content=None,
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = 10

    notes_result = MagicMock()
    notes_scalars = MagicMock()
    notes_scalars.all.return_value = [note]
    notes_result.scalars.return_value = notes_scalars

    db.execute = AsyncMock(side_effect=[count_result, notes_result, MagicMock()])
    db.commit = AsyncMock()

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ),
    ):
        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock(
            __class__=type("BayesianAverageScorerAdapter", (), {})
        )
        mock_factory_cls.return_value = mock_factory

        await trigger_scoring_for_simulation(run.id, db)

    assert run.metrics["scores_computed"] == 1
    assert run.metrics["last_scoring_tier"] == "minimal"
    assert "minimal" in run.metrics["tiers_reached"]
    assert len(run.metrics["scorers_used"]) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_status_helpful():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    ratings = [_make_rating("HELPFUL") for _ in range(6)]
    note = _make_note(community_server_id=cs_id, ratings=ratings)

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.9,
        confidence=ScoreConfidence.STANDARD,
        algorithm="bayesian_average_tier0",
        rating_count=6,
        tier=0,
        tier_name="Minimal",
        calculated_at=None,
        content=None,
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = 5

    notes_result = MagicMock()
    notes_scalars = MagicMock()
    notes_scalars.all.return_value = [note]
    notes_result.scalars.return_value = notes_scalars

    db.execute = AsyncMock(side_effect=[count_result, notes_result, MagicMock()])
    db.commit = AsyncMock()

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ),
    ):
        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock()
        mock_factory_cls.return_value = mock_factory

        result = await trigger_scoring_for_simulation(run.id, db)

    assert result.scores_computed == 1
    update_call = db.execute.call_args_list[2]
    assert update_call is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_status_not_helpful():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    note = _make_note(community_server_id=cs_id, ratings=[_make_rating("NOT_HELPFUL")] * 6)

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.2,
        confidence=ScoreConfidence.STANDARD,
        algorithm="bayesian_average_tier0",
        rating_count=6,
        tier=0,
        tier_name="Minimal",
        calculated_at=None,
        content=None,
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = 3

    notes_result = MagicMock()
    notes_scalars = MagicMock()
    notes_scalars.all.return_value = [note]
    notes_result.scalars.return_value = notes_scalars

    db.execute = AsyncMock(side_effect=[count_result, notes_result, MagicMock()])
    db.commit = AsyncMock()

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ),
    ):
        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock()
        mock_factory_cls.return_value = mock_factory

        result = await trigger_scoring_for_simulation(run.id, db)

    assert result.scores_computed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_accumulates_metrics():
    cs_id = uuid4()
    existing_metrics = {
        "scores_computed": 10,
        "tiers_reached": ["minimal"],
        "scorers_used": ["BayesianAverageScorerAdapter"],
        "tier_distribution": {"minimal": 10},
        "scorer_breakdown": {"BayesianAverageScorerAdapter": 10},
    }
    run = _make_run(community_server_id=cs_id, metrics=existing_metrics)
    note = _make_note(community_server_id=cs_id, ratings=[_make_rating()])

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.6,
        confidence=ScoreConfidence.PROVISIONAL,
        algorithm="bayesian_average_tier0",
        rating_count=1,
        tier=0,
        tier_name="Minimal",
        calculated_at=None,
        content=None,
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = 50

    notes_result = MagicMock()
    notes_scalars = MagicMock()
    notes_scalars.all.return_value = [note]
    notes_result.scalars.return_value = notes_scalars

    db.execute = AsyncMock(side_effect=[count_result, notes_result, MagicMock()])
    db.commit = AsyncMock()

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ),
    ):
        mock_factory = MagicMock()
        mock_scorer = MagicMock()
        type(mock_scorer).__name__ = "BayesianAverageScorerAdapter"
        mock_factory.get_scorer.return_value = mock_scorer
        mock_factory_cls.return_value = mock_factory

        await trigger_scoring_for_simulation(run.id, db)

    assert run.metrics["scores_computed"] == 11
    assert run.metrics["tier_distribution"]["minimal"] == 11
    assert run.metrics["scorer_breakdown"]["BayesianAverageScorerAdapter"] == 11
    assert len(run.metrics["tiers_reached"]) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_coverage_all_target_tiers_reached():
    run = _make_run(
        metrics={
            "tiers_reached": ["minimal", "limited"],
            "scorers_used": ["BayesianAverageScorerAdapter", "MFCoreScorerAdapter"],
        }
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    scoring_config = {"target_tiers": ["minimal", "limited"]}
    result = await check_scoring_coverage(run.id, scoring_config, db)

    assert result.all_targets_met is True
    assert result.missing_tiers == []
    assert set(result.scorers_exercised) == {"BayesianAverageScorerAdapter", "MFCoreScorerAdapter"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_coverage_missing_tiers():
    run = _make_run(
        metrics={
            "tiers_reached": ["minimal"],
            "scorers_used": ["BayesianAverageScorerAdapter"],
        }
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    scoring_config = {"target_tiers": ["minimal", "limited", "basic"]}
    result = await check_scoring_coverage(run.id, scoring_config, db)

    assert result.all_targets_met is False
    assert "limited" in result.missing_tiers
    assert "basic" in result.missing_tiers
    assert "minimal" not in result.missing_tiers


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_coverage_empty_metrics():
    run = _make_run(metrics={})
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    scoring_config = {"target_tiers": ["minimal"]}
    result = await check_scoring_coverage(run.id, scoring_config, db)

    assert result.all_targets_met is False
    assert result.missing_tiers == ["minimal"]
    assert result.scorers_exercised == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_coverage_no_target_tiers():
    run = _make_run(metrics={"tiers_reached": ["minimal"]})
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    scoring_config = {"target_tiers": []}
    result = await check_scoring_coverage(run.id, scoring_config, db)

    assert result.all_targets_met is True
    assert result.missing_tiers == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_coverage_not_found():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await check_scoring_coverage(uuid4(), {}, db)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_coverage_bayesian_and_mf_exercised():
    run = _make_run(
        metrics={
            "tiers_reached": ["minimal", "limited"],
            "scorers_used": ["BayesianAverageScorerAdapter", "MFCoreScorerAdapter"],
        }
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    scoring_config = {"target_tiers": ["minimal", "limited"]}
    result = await check_scoring_coverage(run.id, scoring_config, db)

    assert "BayesianAverageScorerAdapter" in result.scorers_exercised
    assert "MFCoreScorerAdapter" in result.scorers_exercised
    assert len(result.scorers_exercised) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_metrics_returns_tier_distribution():
    run = _make_run(
        metrics={
            "scores_computed": 250,
            "last_scoring_tier": "limited",
            "tier_distribution": {"minimal": 150, "limited": 100},
            "scorer_breakdown": {"BayesianAverageScorerAdapter": 150, "MFCoreScorerAdapter": 100},
        }
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    status_rows = [("NEEDS_MORE_RATINGS", 50), ("CURRENTLY_RATED_HELPFUL", 200)]
    status_result = MagicMock()
    status_result.all.return_value = status_rows
    db.execute = AsyncMock(return_value=status_result)

    result = await get_scoring_metrics(run.id, db)

    assert isinstance(result, ScoringMetrics)
    assert result.total_scores_computed == 250
    assert result.current_tier == "limited"
    assert result.tier_distribution == {"minimal": 150, "limited": 100}
    assert result.notes_by_status["NEEDS_MORE_RATINGS"] == 50
    assert result.notes_by_status["CURRENTLY_RATED_HELPFUL"] == 200


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_metrics_includes_scorer_breakdown():
    run = _make_run(
        metrics={
            "scores_computed": 300,
            "last_scoring_tier": "limited",
            "tier_distribution": {"minimal": 100, "limited": 200},
            "scorer_breakdown": {"BayesianAverageScorerAdapter": 100, "MFCoreScorerAdapter": 200},
        }
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    status_result = MagicMock()
    status_result.all.return_value = []
    db.execute = AsyncMock(return_value=status_result)

    result = await get_scoring_metrics(run.id, db)

    assert result.scorer_breakdown["BayesianAverageScorerAdapter"] == 100
    assert result.scorer_breakdown["MFCoreScorerAdapter"] == 200


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_metrics_empty():
    run = _make_run(metrics={})

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    status_result = MagicMock()
    status_result.all.return_value = []
    db.execute = AsyncMock(return_value=status_result)

    result = await get_scoring_metrics(run.id, db)

    assert result.total_scores_computed == 0
    assert result.current_tier == "minimal"
    assert result.tier_distribution == {}
    assert result.scorer_breakdown == {}
    assert result.notes_by_status == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_metrics_not_found():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await get_scoring_metrics(uuid4(), db)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_handles_scoring_error_gracefully():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    note1 = _make_note(community_server_id=cs_id, ratings=[_make_rating()])
    note2 = _make_note(community_server_id=cs_id, ratings=[_make_rating()])

    good_response = NoteScoreResponse(
        note_id=note2.id,
        score=0.6,
        confidence=ScoreConfidence.PROVISIONAL,
        algorithm="bayesian_average_tier0",
        rating_count=1,
        tier=0,
        tier_name="Minimal",
        calculated_at=None,
        content=None,
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = 2

    notes_result = MagicMock()
    notes_scalars = MagicMock()
    notes_scalars.all.return_value = [note1, note2]
    notes_result.scalars.return_value = notes_scalars

    db.execute = AsyncMock(side_effect=[count_result, notes_result, MagicMock()])
    db.commit = AsyncMock()

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("scoring failed"), good_response],
        ),
    ):
        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock()
        mock_factory_cls.return_value = mock_factory

        result = await trigger_scoring_for_simulation(run.id, db)

    assert result.scores_computed == 1


@pytest.mark.unit
def test_scoring_run_result_dataclass():
    result = ScoringRunResult(
        scores_computed=10,
        tier=ScoringTier.LIMITED,
        tier_name="Limited",
        scorer_type="MFCoreScorerAdapter",
        note_count=250,
    )
    assert result.scores_computed == 10
    assert result.tier == ScoringTier.LIMITED
    assert result.tier_name == "Limited"
    assert result.scorer_type == "MFCoreScorerAdapter"
    assert result.note_count == 250


@pytest.mark.unit
def test_coverage_result_dataclass():
    result = CoverageResult(
        all_targets_met=False,
        target_tiers=["minimal", "limited"],
        reached_tiers=["minimal"],
        missing_tiers=["limited"],
        scorers_exercised=["BayesianAverageScorerAdapter"],
    )
    assert result.all_targets_met is False
    assert "limited" in result.missing_tiers


@pytest.mark.unit
def test_scoring_metrics_dataclass():
    result = ScoringMetrics(
        total_scores_computed=100,
        current_tier="minimal",
        tier_distribution={"minimal": 100},
        scorer_breakdown={"BayesianAverageScorerAdapter": 100},
        notes_by_status={"NEEDS_MORE_RATINGS": 50, "CURRENTLY_RATED_HELPFUL": 50},
    )
    assert result.total_scores_computed == 100
    assert result.notes_by_status["CURRENTLY_RATED_HELPFUL"] == 50
