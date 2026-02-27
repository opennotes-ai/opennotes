from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.notes.scoring_schemas import NoteScoreResponse, ScoreConfidence
from src.simulation.scoring_integration import (
    SCORING_BATCH_SIZE,
    CommunityServerScoringResult,
    score_community_server_notes,
)


def _make_note(
    *,
    note_id: UUID | None = None,
    community_server_id: UUID | None = None,
    status: str = "NEEDS_MORE_RATINGS",
    ratings: list | None = None,
) -> MagicMock:
    note = MagicMock()
    note.id = note_id or uuid4()
    note.community_server_id = community_server_id or uuid4()
    note.status = status
    note.deleted_at = None
    note.ratings = ratings if ratings is not None else []
    note.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    note.created_at = datetime(2024, 12, 1, tzinfo=UTC)
    note.request = None
    return note


def _make_rating(*, created_at: datetime | None = None) -> MagicMock:
    rating = MagicMock()
    rating.id = uuid4()
    rating.created_at = created_at or datetime(2025, 1, 1, tzinfo=UTC)
    rating.helpfulness_level = "HELPFUL"
    return rating


def _make_score_response(
    note_id: UUID, score: float = 0.7, rating_count: int = 5
) -> NoteScoreResponse:
    return NoteScoreResponse(
        note_id=note_id,
        score=score,
        confidence=ScoreConfidence.STANDARD,
        algorithm="bayesian_average_tier0",
        rating_count=rating_count,
        tier=0,
        tier_name="Minimal",
        calculated_at=datetime(2025, 1, 2, tzinfo=UTC),
        content=None,
    )


def _mock_db_for_community_scoring(
    note_count: int,
    unscored_notes: list,
    rescore_notes: list,
) -> AsyncMock:
    """Build a mock db whose execute side_effects match the call pattern.

    Call pattern per pass:
    - Empty pass: 1 call (select returns empty -> break)
    - Non-empty pass with < SCORING_BATCH_SIZE notes: 2 calls (select, update)
      The batch loop breaks after update because len(batch) < SCORING_BATCH_SIZE.

    After both passes: 1 call for request completion update.
    """
    db = AsyncMock()

    count_result = MagicMock()
    count_result.scalar.return_value = note_count

    empty_batch = MagicMock()
    empty_batch.scalars.return_value.all.return_value = []

    update_result = MagicMock()
    request_update_result = MagicMock()

    side_effects = [count_result]

    if unscored_notes:
        unscored_batch = MagicMock()
        unscored_batch.scalars.return_value.all.return_value = unscored_notes
        side_effects.append(unscored_batch)
        side_effects.append(update_result)
    else:
        side_effects.append(empty_batch)

    if rescore_notes:
        rescore_batch = MagicMock()
        rescore_batch.scalars.return_value.all.return_value = rescore_notes
        side_effects.append(rescore_batch)
        side_effects.append(MagicMock())
    else:
        side_effects.append(empty_batch)

    side_effects.append(request_update_result)

    db.execute = AsyncMock(side_effect=side_effects)
    db.commit = AsyncMock()

    return db


class TestScoreCommunityServerNotes:
    @pytest.mark.asyncio
    async def test_empty_community_returns_zero_counts(self) -> None:
        cs_id = uuid4()
        db = _mock_db_for_community_scoring(note_count=0, unscored_notes=[], rescore_notes=[])
        db.execute = AsyncMock(side_effect=[MagicMock(scalar=MagicMock(return_value=0))])

        result = await score_community_server_notes(cs_id, db)

        assert isinstance(result, CommunityServerScoringResult)
        assert result.community_server_id == cs_id
        assert result.unscored_notes_processed == 0
        assert result.rescored_notes_processed == 0
        assert result.total_scores_computed == 0
        assert result.scorer_type == "none"

    @pytest.mark.asyncio
    async def test_unscored_notes_with_enough_ratings_get_scored(self) -> None:
        cs_id = uuid4()
        note1 = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note2 = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        ratings = [_make_rating() for _ in range(5)]
        note1.ratings = ratings
        note2.ratings = ratings

        db = _mock_db_for_community_scoring(
            note_count=10,
            unscored_notes=[note1, note2],
            rescore_notes=[],
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ) as mock_calc,
            patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        ):
            mock_scorer = MagicMock()
            mock_factory_cls.return_value.get_scorer.return_value = mock_scorer

            mock_calc.side_effect = [
                _make_score_response(note1.id, score=0.7, rating_count=5),
                _make_score_response(note2.id, score=0.3, rating_count=5),
            ]

            result = await score_community_server_notes(cs_id, db)

        assert result.unscored_notes_processed == 2
        assert result.rescored_notes_processed == 0
        assert result.total_scores_computed == 2
        assert mock_calc.call_count == 2

    @pytest.mark.asyncio
    async def test_already_scored_notes_get_rescored(self) -> None:
        cs_id = uuid4()
        note_crh = _make_note(community_server_id=cs_id, status="CURRENTLY_RATED_HELPFUL")
        note_crh.ratings = [_make_rating() for _ in range(6)]

        db = _mock_db_for_community_scoring(
            note_count=5,
            unscored_notes=[],
            rescore_notes=[note_crh],
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ) as mock_calc,
            patch("src.simulation.scoring_integration.ScorerFactory"),
        ):
            mock_calc.return_value = _make_score_response(note_crh.id, score=0.8, rating_count=6)

            result = await score_community_server_notes(cs_id, db)

        assert result.unscored_notes_processed == 0
        assert result.rescored_notes_processed == 1
        assert result.total_scores_computed == 1

    @pytest.mark.asyncio
    async def test_both_passes_process_notes(self) -> None:
        cs_id = uuid4()
        unscored = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        unscored.ratings = [_make_rating() for _ in range(5)]
        already_scored = _make_note(community_server_id=cs_id, status="CURRENTLY_RATED_NOT_HELPFUL")
        already_scored.ratings = [_make_rating() for _ in range(7)]

        db = _mock_db_for_community_scoring(
            note_count=20,
            unscored_notes=[unscored],
            rescore_notes=[already_scored],
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ) as mock_calc,
            patch("src.simulation.scoring_integration.ScorerFactory"),
        ):
            mock_calc.side_effect = [
                _make_score_response(unscored.id, score=0.6, rating_count=5),
                _make_score_response(already_scored.id, score=0.4, rating_count=7),
            ]

            result = await score_community_server_notes(cs_id, db)

        assert result.unscored_notes_processed == 1
        assert result.rescored_notes_processed == 1
        assert result.total_scores_computed == 2

    @pytest.mark.asyncio
    async def test_result_includes_tier_and_scorer_info(self) -> None:
        cs_id = uuid4()
        db = _mock_db_for_community_scoring(
            note_count=50,
            unscored_notes=[],
            rescore_notes=[],
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ),
            patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory_cls,
        ):
            mock_scorer = MagicMock()
            type(mock_scorer).__name__ = "BayesianAverageScorerAdapter"
            mock_factory_cls.return_value.get_scorer.return_value = mock_scorer

            result = await score_community_server_notes(cs_id, db)

        assert result.tier_name == "Minimal"
        assert result.scorer_type == "BayesianAverageScorerAdapter"

    @pytest.mark.asyncio
    async def test_scoring_error_on_single_note_does_not_abort(self) -> None:
        cs_id = uuid4()
        note_bad = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note_bad.ratings = [_make_rating() for _ in range(5)]
        note_ok = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note_ok.ratings = [_make_rating() for _ in range(5)]

        db = _mock_db_for_community_scoring(
            note_count=10,
            unscored_notes=[note_bad, note_ok],
            rescore_notes=[],
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ) as mock_calc,
            patch("src.simulation.scoring_integration.ScorerFactory"),
        ):
            mock_calc.side_effect = [
                RuntimeError("scoring failed"),
                _make_score_response(note_ok.id, score=0.6, rating_count=5),
            ]

            result = await score_community_server_notes(cs_id, db)

        assert result.total_scores_computed == 1
        assert result.unscored_notes_processed == 1

    @pytest.mark.asyncio
    async def test_commits_at_end(self) -> None:
        cs_id = uuid4()
        db = _mock_db_for_community_scoring(
            note_count=5,
            unscored_notes=[],
            rescore_notes=[],
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ),
            patch("src.simulation.scoring_integration.ScorerFactory"),
        ):
            await score_community_server_notes(cs_id, db)

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unscored_multi_batch_scores_all_notes(self) -> None:
        """All unscored notes must be scored even when count > SCORING_BATCH_SIZE.

        After batch 1 is scored, those notes leave the NEEDS_MORE_RATINGS
        result set (status changes to CRH/CRNH).  With offset=0 the next
        query correctly returns the remaining unscored notes.  With the
        old offset-increment logic the query would skip past them.
        """
        cs_id = uuid4()
        total_unscored = SCORING_BATCH_SIZE + 50
        all_notes = [
            _make_note(
                community_server_id=cs_id,
                status="NEEDS_MORE_RATINGS",
                ratings=[_make_rating() for _ in range(5)],
            )
            for _ in range(total_unscored)
        ]

        scored_ids: set[UUID] = set()

        def _execute_side_effect(stmt: object, *_a: object, **_kw: object) -> MagicMock:
            nonlocal scored_ids

            is_update = hasattr(stmt, "is_dml") and stmt.is_dml
            if is_update:
                return MagicMock()

            has_limit = hasattr(stmt, "_limit_clause") and stmt._limit_clause is not None
            has_offset = hasattr(stmt, "_offset_clause") and stmt._offset_clause is not None

            if has_limit and has_offset:
                offset_val = 0
                try:
                    offset_val = int(stmt._offset_clause.value)
                except Exception:
                    pass

                remaining = [n for n in all_notes if n.id not in scored_ids]
                page = remaining[offset_val : offset_val + SCORING_BATCH_SIZE]

                for note in page:
                    scored_ids.add(note.id)

                res = MagicMock()
                res.scalars.return_value.all.return_value = page
                return res

            res = MagicMock()
            res.scalar.return_value = total_unscored
            return res

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_execute_side_effect)
        db.commit = AsyncMock()

        score_responses = {
            note.id: _make_score_response(note.id, score=0.7, rating_count=5) for note in all_notes
        }

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ) as mock_calc,
            patch("src.simulation.scoring_integration.ScorerFactory"),
        ):
            mock_calc.side_effect = lambda note, *_a, **_kw: score_responses[note.id]

            result = await score_community_server_notes(cs_id, db)

        assert result.unscored_notes_processed == total_unscored
        assert result.total_scores_computed >= total_unscored
        assert mock_calc.call_count >= total_unscored
