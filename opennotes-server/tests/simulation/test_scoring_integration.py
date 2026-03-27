from __future__ import annotations

import logging
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.notes.scoring.tier_config import ScoringTier
from src.notes.scoring_schemas import NoteScoreResponse, ScoreConfidence
from src.simulation.scoring_integration import (
    SCORING_BATCH_SIZE,
    CoverageResult,
    ScoringMetrics,
    ScoringRunResult,
    _build_profile_remap,
    _maybe_persist_snapshot,
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


def _mock_db_for_trigger(run, note_count, notes, agent_count=3):
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = note_count

    batch_result = MagicMock()
    batch_scalars = MagicMock()
    batch_scalars.all.return_value = notes
    batch_result.scalars.return_value = batch_scalars

    update_result = MagicMock()
    request_update_result = MagicMock()
    request_revert_result = MagicMock()

    agent_count_result = MagicMock()
    agent_count_result.scalar.return_value = agent_count

    note_count_result = MagicMock()
    note_count_result.scalar.return_value = note_count

    platform_result = MagicMock()
    platform_result.scalar_one_or_none.return_value = "playground"

    db.execute = AsyncMock(
        side_effect=[
            count_result,
            batch_result,
            update_result,
            request_update_result,
            request_revert_result,
            agent_count_result,
            note_count_result,
            platform_result,
        ]
    )
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

    agent_count_result = MagicMock()
    agent_count_result.scalar.return_value = 0

    note_count_result = MagicMock()
    note_count_result.scalar.return_value = 0

    db.execute = AsyncMock(side_effect=[count_result, agent_count_result, note_count_result])
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

    db = _mock_db_for_trigger(run, 5, [note])

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
    mock_factory.get_scorer.assert_called_once_with(
        str(cs_id), 5, data_provider=None, community_id=str(cs_id), ratings_density=None
    )
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

    db = _mock_db_for_trigger(run, 10, [note])

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
async def test_update_run_metrics_includes_agent_and_note_count():
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

    db = _mock_db_for_trigger(run, 10, [note])

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

    assert "agent_count" in run.metrics, f"metrics keys: {list(run.metrics.keys())}"
    assert "note_count" in run.metrics, f"metrics keys: {list(run.metrics.keys())}"
    assert isinstance(run.metrics["agent_count"], int)
    assert isinstance(run.metrics["note_count"], int)
    assert run.metrics["note_count"] == 10


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_run_metrics_zero_notes_includes_counts():
    run = _make_run()
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = 0
    db.execute = AsyncMock(return_value=count_result)
    db.commit = AsyncMock()

    result = await trigger_scoring_for_simulation(run.id, db)

    assert result.note_count == 0
    assert "agent_count" in run.metrics, f"metrics keys: {list(run.metrics.keys())}"
    assert "note_count" in run.metrics, f"metrics keys: {list(run.metrics.keys())}"
    assert run.metrics["note_count"] == 0
    assert run.metrics["agent_count"] == 0


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

    db = _mock_db_for_trigger(run, 5, [note])

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
    assert db.execute.call_count == 8


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

    db = _mock_db_for_trigger(run, 3, [note])

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

    db = _mock_db_for_trigger(run, 50, [note])

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

    db = _mock_db_for_trigger(run, 2, [note1, note2])

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
@pytest.mark.asyncio
async def test_trigger_scoring_batch_update_uses_case():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    note1 = _make_note(community_server_id=cs_id)
    note2 = _make_note(community_server_id=cs_id)

    responses = [
        NoteScoreResponse(
            note_id=note1.id,
            score=0.9,
            confidence=ScoreConfidence.STANDARD,
            algorithm="bayesian_average_tier0",
            rating_count=6,
            tier=0,
            tier_name="Minimal",
            calculated_at=None,
            content=None,
        ),
        NoteScoreResponse(
            note_id=note2.id,
            score=0.3,
            confidence=ScoreConfidence.STANDARD,
            algorithm="bayesian_average_tier0",
            rating_count=6,
            tier=0,
            tier_name="Minimal",
            calculated_at=None,
            content=None,
        ),
    ]

    db = _mock_db_for_trigger(run, 2, [note1, note2])

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            side_effect=responses,
        ),
    ):
        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock()
        mock_factory_cls.return_value = mock_factory

        result = await trigger_scoring_for_simulation(run.id, db)

    assert result.scores_computed == 2
    assert db.execute.call_count == 8


@pytest.mark.unit
def test_scoring_batch_size_constant():
    assert SCORING_BATCH_SIZE == 100


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_transitions_requests_for_helpful_notes():
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

    batch_result = MagicMock()
    batch_scalars = MagicMock()
    batch_scalars.all.return_value = [note]
    batch_result.scalars.return_value = batch_scalars

    note_update_result = MagicMock()
    request_update_result = MagicMock()
    request_revert_result = MagicMock()
    agent_count_result_a = MagicMock()
    agent_count_result_a.scalar.return_value = 3
    note_count_requery_a = MagicMock()
    note_count_requery_a.scalar.return_value = 5
    platform_result = MagicMock()
    platform_result.scalar_one_or_none.return_value = "playground"

    db.execute = AsyncMock(
        side_effect=[
            count_result,
            batch_result,
            note_update_result,
            request_update_result,
            request_revert_result,
            agent_count_result_a,
            note_count_requery_a,
            platform_result,
        ]
    )
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

        await trigger_scoring_for_simulation(run.id, db)

    assert db.execute.call_count == 8

    request_update_stmt = db.execute.call_args_list[3][0][0]
    compiled = request_update_stmt.compile(compile_kwargs={"literal_binds": True})
    sql_str = str(compiled)

    assert "requests" in sql_str, f"SQL: {sql_str}"
    assert "COMPLETED" in sql_str, f"SQL: {sql_str}"
    assert "PENDING" in sql_str, f"SQL: {sql_str}"
    assert "request_id" in sql_str, f"SQL: {sql_str}"
    assert "note_id" in sql_str, f"SQL: {sql_str}"
    assert "CURRENTLY_RATED_HELPFUL" in sql_str, f"SQL: {sql_str}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_no_request_transition_when_not_helpful():
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

    batch_result = MagicMock()
    batch_scalars = MagicMock()
    batch_scalars.all.return_value = [note]
    batch_result.scalars.return_value = batch_scalars

    note_update_result = MagicMock()
    request_update_result = MagicMock()
    request_revert_result = MagicMock()
    agent_count_result_b = MagicMock()
    agent_count_result_b.scalar.return_value = 2
    note_count_requery_b = MagicMock()
    note_count_requery_b.scalar.return_value = 3
    platform_result = MagicMock()
    platform_result.scalar_one_or_none.return_value = "playground"

    db.execute = AsyncMock(
        side_effect=[
            count_result,
            batch_result,
            note_update_result,
            request_update_result,
            request_revert_result,
            agent_count_result_b,
            note_count_requery_b,
            platform_result,
        ]
    )
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
    assert db.execute.call_count == 8

    request_update_stmt = db.execute.call_args_list[3][0][0]
    compiled = request_update_stmt.compile(compile_kwargs={"literal_binds": True})
    sql_str = str(compiled)

    assert "requests" in sql_str
    assert "COMPLETED" in sql_str
    assert "CURRENTLY_RATED_HELPFUL" in sql_str


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_no_request_transition_for_needs_more_ratings():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    note = _make_note(community_server_id=cs_id, ratings=[_make_rating("HELPFUL")])

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.8,
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

    batch_result = MagicMock()
    batch_scalars = MagicMock()
    batch_scalars.all.return_value = [note]
    batch_result.scalars.return_value = batch_scalars

    note_update_result = MagicMock()
    request_update_result = MagicMock()
    request_revert_result = MagicMock()
    agent_count_result_c = MagicMock()
    agent_count_result_c.scalar.return_value = 1
    note_count_requery_c = MagicMock()
    note_count_requery_c.scalar.return_value = 2
    platform_result = MagicMock()
    platform_result.scalar_one_or_none.return_value = "playground"

    db.execute = AsyncMock(
        side_effect=[
            count_result,
            batch_result,
            note_update_result,
            request_update_result,
            request_revert_result,
            agent_count_result_c,
            note_count_requery_c,
            platform_result,
        ]
    )
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
    assert db.execute.call_count == 8

    request_update_stmt = db.execute.call_args_list[3][0][0]
    compiled = request_update_stmt.compile(compile_kwargs={"literal_binds": True})
    sql_str = str(compiled)

    assert "requests" in sql_str
    assert "COMPLETED" in sql_str
    assert "CURRENTLY_RATED_HELPFUL" in sql_str


@pytest.mark.unit
@pytest.mark.asyncio
async def test_maybe_persist_snapshot_sentinel_when_no_factors():
    from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

    scorer = MFCoreScorerAdapter()
    assert scorer.get_last_scoring_factors() is None

    cs_id = uuid4()
    db = AsyncMock()

    with patch(
        "src.simulation.scoring_integration.persist_scoring_snapshot", new_callable=AsyncMock
    ) as mock_persist:
        result = await _maybe_persist_snapshot(scorer, cs_id, "limited", "MFCoreScorerAdapter", db)

    assert result is not None
    assert result["sentinel"] is True
    assert result["note_count"] == 0
    assert result["rater_count"] == 0
    assert result["rater_factors"] == []
    assert result["note_factors"] == []
    assert result["global_intercept"] == 0.0
    mock_persist.assert_called_once()
    call_kwargs = mock_persist.call_args[1]
    assert call_kwargs["rater_factors"] == []
    assert call_kwargs["note_factors"] == []
    assert call_kwargs["global_intercept"] == 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_maybe_persist_snapshot_sentinel_logs_warning(caplog):
    from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

    scorer = MFCoreScorerAdapter()
    cs_id = uuid4()
    db = AsyncMock()

    with (
        patch(
            "src.simulation.scoring_integration.persist_scoring_snapshot", new_callable=AsyncMock
        ),
        caplog.at_level(logging.WARNING, logger="src.simulation.scoring_integration"),
    ):
        await _maybe_persist_snapshot(scorer, cs_id, "limited", "MFCoreScorerAdapter", db)

    assert any("no scoring factors" in record.message.lower() for record in caplog.records)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_maybe_persist_snapshot_with_real_factors():
    from src.notes.scoring.mf_scorer_adapter import MFCoreScorerAdapter

    scorer = MFCoreScorerAdapter()
    mock_result = MagicMock()
    mock_result.helpfulnessScores = None
    mock_result.scoredNotes = None
    scorer._last_model_result = mock_result
    scorer._last_int_to_uuid = {}

    cs_id = uuid4()
    db = AsyncMock()

    with patch(
        "src.simulation.scoring_integration.persist_scoring_snapshot", new_callable=AsyncMock
    ) as mock_persist:
        result = await _maybe_persist_snapshot(scorer, cs_id, "limited", "MFCoreScorerAdapter", db)

    assert result is not None
    assert "sentinel" not in result
    mock_persist.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_maybe_persist_snapshot_non_mf_returns_none():
    scorer = MagicMock()
    type(scorer).__name__ = "BayesianAverageScorerAdapter"
    cs_id = uuid4()
    db = AsyncMock()

    result = await _maybe_persist_snapshot(
        scorer, cs_id, "minimal", "BayesianAverageScorerAdapter", db
    )
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_passes_data_provider_for_limited_tier():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    note = _make_note(community_server_id=cs_id, ratings=[_make_rating()])

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.6,
        confidence=ScoreConfidence.PROVISIONAL,
        algorithm="mf_core_stub",
        rating_count=1,
        tier=1,
        tier_name="Limited",
        calculated_at=None,
        content=None,
    )

    db = _mock_db_for_trigger(run, 500, [note])

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ),
        patch(
            "src.simulation.scoring_integration._prefetch_community_data", new_callable=AsyncMock
        ) as mock_prefetch,
    ):
        mock_provider = MagicMock()
        mock_prefetch.return_value = mock_provider

        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock()
        mock_factory_cls.return_value = mock_factory

        await trigger_scoring_for_simulation(run.id, db)

    mock_prefetch.assert_called_once_with(cs_id, db)
    mock_factory.get_scorer.assert_called_once_with(
        str(cs_id), 500, data_provider=mock_provider, community_id=str(cs_id), ratings_density=ANY
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_no_prefetch_for_minimal_tier():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
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

    db = _mock_db_for_trigger(run, 5, [note])

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ),
        patch(
            "src.simulation.scoring_integration._prefetch_community_data", new_callable=AsyncMock
        ) as mock_prefetch,
    ):
        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock(
            __class__=type("BayesianAverageScorerAdapter", (), {})
        )
        mock_factory_cls.return_value = mock_factory

        await trigger_scoring_for_simulation(run.id, db)

    mock_prefetch.assert_not_called()


def _make_instance(user_profile_id=None, agent_profile_id=None, turn_count=1):
    inst = MagicMock()
    inst.user_profile_id = user_profile_id or uuid4()
    inst.agent_profile_id = agent_profile_id or uuid4()
    inst.turn_count = turn_count
    return inst


@pytest.mark.unit
def test_build_profile_remap_aggregate_by_user_profile_returns_empty():
    inst1 = _make_instance(turn_count=5)
    inst2 = _make_instance(turn_count=3)
    result = _build_profile_remap([inst1, inst2], aggregation="aggregate_by_user_profile")
    assert result == {}


@pytest.mark.unit
def test_build_profile_remap_aggregate_by_agent_profile_returns_remap():
    up1, ap1 = uuid4(), uuid4()
    up2, ap2 = uuid4(), uuid4()
    inst1 = _make_instance(user_profile_id=up1, agent_profile_id=ap1, turn_count=2)
    inst2 = _make_instance(user_profile_id=up2, agent_profile_id=ap2, turn_count=1)
    result = _build_profile_remap([inst1, inst2], aggregation="aggregate_by_agent_profile")
    assert result == {str(up1): str(ap1), str(up2): str(ap2)}


@pytest.mark.unit
def test_build_profile_remap_default_aggregation_is_agent_profile():
    up1, ap1 = uuid4(), uuid4()
    inst = _make_instance(user_profile_id=up1, agent_profile_id=ap1, turn_count=1)
    result = _build_profile_remap([inst])
    assert result == {str(up1): str(ap1)}


@pytest.mark.unit
def test_build_profile_remap_skips_zero_turn_count():
    inst = _make_instance(turn_count=0)
    result = _build_profile_remap([inst], aggregation="aggregate_by_agent_profile")
    assert result == {}


def _mock_db_for_limited_tier(run, note_count, notes, agent_count=3):
    db = AsyncMock()
    db.get = AsyncMock(return_value=run)

    count_result = MagicMock()
    count_result.scalar.return_value = note_count

    batch_result = MagicMock()
    batch_scalars = MagicMock()
    batch_scalars.all.return_value = notes
    batch_result.scalars.return_value = batch_scalars

    update_result = MagicMock()
    request_update_1 = MagicMock()
    request_update_2 = MagicMock()

    agent_count_result = MagicMock()
    agent_count_result.scalar.return_value = agent_count

    note_count_result = MagicMock()
    note_count_result.scalar.return_value = note_count

    platform_result = MagicMock()
    platform_result.scalar_one_or_none.return_value = "playground"

    db.execute = AsyncMock(
        side_effect=[
            count_result,
            batch_result,
            update_result,
            request_update_1,
            request_update_2,
            agent_count_result,
            note_count_result,
            platform_result,
        ]
    )
    db.commit = AsyncMock()
    return db


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_passes_aggregation_to_prefetch():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    run.rating_aggregation = "aggregate_by_user_profile"
    note = _make_note(community_server_id=cs_id, ratings=[_make_rating()])

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.6,
        confidence=ScoreConfidence.PROVISIONAL,
        algorithm="mf_core_stub",
        rating_count=1,
        tier=1,
        tier_name="Limited",
        calculated_at=None,
        content=None,
    )

    db = _mock_db_for_limited_tier(run, 500, [note])

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ),
        patch(
            "src.simulation.scoring_integration._prefetch_community_data", new_callable=AsyncMock
        ) as mock_prefetch,
        patch(
            "src.simulation.scoring_integration._query_ratings_density",
            new_callable=AsyncMock,
            return_value={"avg_raters_per_note": 3.0, "avg_ratings_per_rater": 5.0},
        ),
    ):
        mock_provider = MagicMock()
        mock_prefetch.return_value = mock_provider

        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock()
        mock_factory_cls.return_value = mock_factory

        await trigger_scoring_for_simulation(run.id, db)

    mock_prefetch.assert_called_once_with(cs_id, db, aggregation="aggregate_by_user_profile")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_trigger_scoring_passes_agent_aggregation_to_prefetch():
    cs_id = uuid4()
    run = _make_run(community_server_id=cs_id)
    run.rating_aggregation = "aggregate_by_agent_profile"
    note = _make_note(community_server_id=cs_id, ratings=[_make_rating()])

    score_response = NoteScoreResponse(
        note_id=note.id,
        score=0.6,
        confidence=ScoreConfidence.PROVISIONAL,
        algorithm="mf_core_stub",
        rating_count=1,
        tier=1,
        tier_name="Limited",
        calculated_at=None,
        content=None,
    )

    db = _mock_db_for_limited_tier(run, 500, [note])

    with (
        patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        patch(
            "src.simulation.scoring_integration.calculate_note_score",
            new_callable=AsyncMock,
            return_value=score_response,
        ),
        patch(
            "src.simulation.scoring_integration._prefetch_community_data", new_callable=AsyncMock
        ) as mock_prefetch,
        patch(
            "src.simulation.scoring_integration._query_ratings_density",
            new_callable=AsyncMock,
            return_value={"avg_raters_per_note": 3.0, "avg_ratings_per_rater": 5.0},
        ),
    ):
        mock_provider = MagicMock()
        mock_prefetch.return_value = mock_provider

        mock_factory = MagicMock()
        mock_factory.get_scorer.return_value = MagicMock()
        mock_factory_cls.return_value = mock_factory

        await trigger_scoring_for_simulation(run.id, db)

    mock_prefetch.assert_called_once_with(cs_id, db, aggregation="aggregate_by_agent_profile")
