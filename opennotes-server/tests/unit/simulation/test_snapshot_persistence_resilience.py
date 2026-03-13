from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.notes.scoring_schemas import NoteScoreResponse, ScoreConfidence
from src.simulation.scoring_integration import (
    score_community_server_notes,
    trigger_scoring_for_simulation,
)


def _make_note(*, community_server_id=None, status="NEEDS_MORE_RATINGS", ratings=None):
    note = MagicMock()
    note.id = uuid4()
    note.community_server_id = community_server_id or uuid4()
    note.status = status
    note.deleted_at = None
    note.ratings = ratings if ratings is not None else []
    note.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    note.created_at = datetime(2024, 12, 1, tzinfo=UTC)
    note.request = None
    return note


def _make_rating():
    rating = MagicMock()
    rating.id = uuid4()
    rating.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    rating.helpfulness_level = "HELPFUL"
    return rating


def _make_score_response(note_id, score=0.7, rating_count=5):
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


def _mock_db_for_community_scoring(note_count, unscored_notes, rescore_notes):
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

    if unscored_notes or rescore_notes:
        platform_result = MagicMock()
        platform_result.scalar_one_or_none.return_value = "discord"
        side_effects.append(platform_result)

    db.execute = AsyncMock(side_effect=side_effects)
    db.commit = AsyncMock()

    return db


class _CompletedFuture:
    def add_done_callback(self, callback):
        callback(self)

    def exception(self):
        return None


class _ImmediateExecutorLoop:
    def __init__(self, events: list[str]):
        self._events = events

    def run_in_executor(self, _executor, fn, *args):
        self._events.append("upload")
        fn(*args)
        return _CompletedFuture()


class _FakeMFCoreScorerAdapter:
    def __init__(self, factors: dict[str, object]):
        self._factors = factors

    def get_last_scoring_factors(self) -> dict[str, object]:
        return self._factors


class TestSnapshotPersistenceResilience:
    @pytest.mark.asyncio
    async def test_manual_scoring_publishes_history_only_after_commit(self) -> None:
        cs_id = uuid4()
        note = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note.ratings = [_make_rating() for _ in range(5)]
        db = _mock_db_for_community_scoring(note_count=10, unscored_notes=[note], rescore_notes=[])
        events: list[str] = []

        async def track_commit() -> None:
            events.append("commit")

        db.commit = AsyncMock(side_effect=track_commit)

        mock_scorer = _FakeMFCoreScorerAdapter(
            {
                "note_count": 10,
                "rater_count": 5,
                "rater_factors": {"r1": 0.1},
                "note_factors": {str(note.id): 0.2},
                "global_intercept": 0.3,
            }
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
                return_value=_make_score_response(note.id, score=0.8, rating_count=5),
            ),
            patch(
                "src.simulation.scoring_integration.MFCoreScorerAdapter",
                _FakeMFCoreScorerAdapter,
            ),
            patch(
                "src.simulation.scoring_integration.settings.SCORING_HISTORY_BUCKET", "test-bucket"
            ),
            patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory,
            patch(
                "src.simulation.scoring_integration.persist_scoring_snapshot",
                new_callable=AsyncMock,
            ),
            patch(
                "src.simulation.scoring_integration._record_scoring_metrics",
                new_callable=AsyncMock,
                return_value="discord",
            ),
            patch(
                "src.simulation.scoring_integration.upload_scoring_snapshot",
                side_effect=lambda *_args, **_kwargs: None,
            ),
            patch(
                "src.simulation.scoring_integration.asyncio.get_running_loop",
                return_value=_ImmediateExecutorLoop(events),
            ),
        ):
            mock_factory.return_value.get_scorer.return_value = mock_scorer
            await score_community_server_notes(cs_id, db)

        assert events == ["commit", "upload"]

    @pytest.mark.asyncio
    async def test_manual_scoring_skips_history_upload_when_commit_fails(self) -> None:
        cs_id = uuid4()
        note = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note.ratings = [_make_rating() for _ in range(5)]
        db = _mock_db_for_community_scoring(note_count=10, unscored_notes=[note], rescore_notes=[])
        events: list[str] = []

        async def fail_commit() -> None:
            events.append("commit")
            raise RuntimeError("commit failed")

        db.commit = AsyncMock(side_effect=fail_commit)

        mock_scorer = _FakeMFCoreScorerAdapter(
            {
                "note_count": 10,
                "rater_count": 5,
                "rater_factors": {"r1": 0.1},
                "note_factors": {str(note.id): 0.2},
                "global_intercept": 0.3,
            }
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
                return_value=_make_score_response(note.id, score=0.8, rating_count=5),
            ),
            patch(
                "src.simulation.scoring_integration.MFCoreScorerAdapter",
                _FakeMFCoreScorerAdapter,
            ),
            patch(
                "src.simulation.scoring_integration.settings.SCORING_HISTORY_BUCKET", "test-bucket"
            ),
            patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory,
            patch(
                "src.simulation.scoring_integration.persist_scoring_snapshot",
                new_callable=AsyncMock,
            ),
            patch(
                "src.simulation.scoring_integration.upload_scoring_snapshot",
                side_effect=lambda *_args, **_kwargs: None,
            ),
            patch(
                "src.simulation.scoring_integration.asyncio.get_running_loop",
                return_value=_ImmediateExecutorLoop(events),
            ),
        ):
            mock_factory.return_value.get_scorer.return_value = mock_scorer
            with pytest.raises(RuntimeError, match="commit failed"):
                await score_community_server_notes(cs_id, db)

        assert events == ["commit"]

    @pytest.mark.asyncio
    async def test_manual_scoring_raises_when_snapshot_persistence_raises(self) -> None:
        cs_id = uuid4()
        note = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note.ratings = [_make_rating() for _ in range(5)]

        db = _mock_db_for_community_scoring(
            note_count=10,
            unscored_notes=[note],
            rescore_notes=[],
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ) as mock_calc,
            patch("src.simulation.scoring_integration.ScorerFactory"),
            patch(
                "src.simulation.scoring_integration._maybe_persist_snapshot",
                new_callable=AsyncMock,
                side_effect=IntegrityError("duplicate key", params=None, orig=Exception()),
            ),
        ):
            mock_calc.return_value = _make_score_response(note.id, score=0.8, rating_count=5)
            with pytest.raises(IntegrityError):
                await score_community_server_notes(cs_id, db)

        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_snapshot_failure_is_logged_with_community_server_id(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        cs_id = uuid4()
        note = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note.ratings = [_make_rating() for _ in range(5)]

        db = _mock_db_for_community_scoring(
            note_count=10,
            unscored_notes=[note],
            rescore_notes=[],
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ) as mock_calc,
            patch("src.simulation.scoring_integration.ScorerFactory"),
            patch(
                "src.simulation.scoring_integration._maybe_persist_snapshot",
                new_callable=AsyncMock,
                side_effect=IntegrityError("duplicate key", params=None, orig=Exception()),
            ),
            caplog.at_level(logging.ERROR, logger="src.simulation.scoring_integration"),
        ):
            mock_calc.return_value = _make_score_response(note.id, score=0.8, rating_count=5)
            with pytest.raises(IntegrityError):
                await score_community_server_notes(cs_id, db)

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) >= 1
        snapshot_record = error_records[0]
        assert hasattr(snapshot_record, "community_server_id")
        assert snapshot_record.community_server_id == str(cs_id)

    @pytest.mark.asyncio
    async def test_simulation_scoring_raises_when_snapshot_persistence_raises(self) -> None:
        sim_run_id = uuid4()
        cs_id = uuid4()
        note = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note.ratings = [_make_rating() for _ in range(5)]

        run = MagicMock()
        run.community_server_id = cs_id
        run.metrics = {}

        db = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 10

        note_batch = MagicMock()
        note_batch.scalars.return_value.all.return_value = [note]

        empty_batch = MagicMock()
        empty_batch.scalars.return_value.all.return_value = []

        update_result = MagicMock()
        request_update_result = MagicMock()
        platform_result = MagicMock()
        platform_result.scalar_one_or_none.return_value = "discord"

        agent_count_result = MagicMock()
        agent_count_result.scalar.return_value = 3

        note_count_result = MagicMock()
        note_count_result.scalar.return_value = 10

        db.get = AsyncMock(return_value=run)
        db.execute = AsyncMock(
            side_effect=[
                count_result,
                note_batch,
                update_result,
                empty_batch,
                request_update_result,
                platform_result,
                agent_count_result,
                note_count_result,
            ]
        )
        db.commit = AsyncMock()

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
            ) as mock_calc,
            patch("src.simulation.scoring_integration.ScorerFactory"),
            patch(
                "src.simulation.scoring_integration._maybe_persist_snapshot",
                new_callable=AsyncMock,
                side_effect=IntegrityError("duplicate key", params=None, orig=Exception()),
            ),
        ):
            mock_calc.return_value = _make_score_response(note.id, score=0.7, rating_count=5)
            with pytest.raises(IntegrityError):
                await trigger_scoring_for_simulation(sim_run_id, db)

        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_simulation_scoring_publishes_history_only_after_commit(self) -> None:
        sim_run_id = uuid4()
        cs_id = uuid4()
        note = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note.ratings = [_make_rating() for _ in range(5)]
        run = MagicMock()
        run.community_server_id = cs_id
        run.metrics = {}
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 10
        note_batch = MagicMock()
        note_batch.scalars.return_value.all.return_value = [note]
        empty_batch = MagicMock()
        empty_batch.scalars.return_value.all.return_value = []
        update_result = MagicMock()
        request_update_result = MagicMock()
        db.get = AsyncMock(return_value=run)
        db.execute = AsyncMock(
            side_effect=[
                count_result,
                note_batch,
                update_result,
                empty_batch,
                request_update_result,
            ]
        )
        events: list[str] = []

        async def track_commit() -> None:
            events.append("commit")

        db.commit = AsyncMock(side_effect=track_commit)

        mock_scorer = _FakeMFCoreScorerAdapter(
            {
                "note_count": 10,
                "rater_count": 5,
                "rater_factors": {"r1": 0.1},
                "note_factors": {str(note.id): 0.2},
                "global_intercept": 0.3,
            }
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
                return_value=_make_score_response(note.id, score=0.7, rating_count=5),
            ),
            patch(
                "src.simulation.scoring_integration.MFCoreScorerAdapter",
                _FakeMFCoreScorerAdapter,
            ),
            patch(
                "src.simulation.scoring_integration.settings.SCORING_HISTORY_BUCKET", "test-bucket"
            ),
            patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory,
            patch(
                "src.simulation.scoring_integration.persist_scoring_snapshot",
                new_callable=AsyncMock,
            ),
            patch(
                "src.simulation.scoring_integration._add_count_metrics",
                new_callable=AsyncMock,
            ),
            patch(
                "src.simulation.scoring_integration._record_scoring_metrics",
                new_callable=AsyncMock,
            ),
            patch(
                "src.simulation.scoring_integration.upload_scoring_snapshot",
                side_effect=lambda *_args, **_kwargs: None,
            ),
            patch(
                "src.simulation.scoring_integration.asyncio.get_running_loop",
                return_value=_ImmediateExecutorLoop(events),
            ),
        ):
            mock_factory.return_value.get_scorer.return_value = mock_scorer
            await trigger_scoring_for_simulation(sim_run_id, db)

        assert events == ["commit", "upload"]

    @pytest.mark.asyncio
    async def test_simulation_scoring_skips_history_upload_when_commit_fails(self) -> None:
        sim_run_id = uuid4()
        cs_id = uuid4()
        note = _make_note(community_server_id=cs_id, status="NEEDS_MORE_RATINGS")
        note.ratings = [_make_rating() for _ in range(5)]
        run = MagicMock()
        run.community_server_id = cs_id
        run.metrics = {}
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 10
        note_batch = MagicMock()
        note_batch.scalars.return_value.all.return_value = [note]
        empty_batch = MagicMock()
        empty_batch.scalars.return_value.all.return_value = []
        update_result = MagicMock()
        request_update_result = MagicMock()
        db.get = AsyncMock(return_value=run)
        db.execute = AsyncMock(
            side_effect=[
                count_result,
                note_batch,
                update_result,
                empty_batch,
                request_update_result,
            ]
        )
        events: list[str] = []

        async def fail_commit() -> None:
            events.append("commit")
            raise RuntimeError("commit failed")

        db.commit = AsyncMock(side_effect=fail_commit)

        mock_scorer = _FakeMFCoreScorerAdapter(
            {
                "note_count": 10,
                "rater_count": 5,
                "rater_factors": {"r1": 0.1},
                "note_factors": {str(note.id): 0.2},
                "global_intercept": 0.3,
            }
        )

        with (
            patch(
                "src.simulation.scoring_integration.calculate_note_score",
                new_callable=AsyncMock,
                return_value=_make_score_response(note.id, score=0.7, rating_count=5),
            ),
            patch(
                "src.simulation.scoring_integration.MFCoreScorerAdapter",
                _FakeMFCoreScorerAdapter,
            ),
            patch(
                "src.simulation.scoring_integration.settings.SCORING_HISTORY_BUCKET", "test-bucket"
            ),
            patch("src.simulation.scoring_integration.ScorerFactory") as mock_factory,
            patch(
                "src.simulation.scoring_integration.persist_scoring_snapshot",
                new_callable=AsyncMock,
            ),
            patch(
                "src.simulation.scoring_integration._add_count_metrics",
                new_callable=AsyncMock,
            ),
            patch(
                "src.simulation.scoring_integration.upload_scoring_snapshot",
                side_effect=lambda *_args, **_kwargs: None,
            ),
            patch(
                "src.simulation.scoring_integration.asyncio.get_running_loop",
                return_value=_ImmediateExecutorLoop(events),
            ),
        ):
            mock_factory.return_value.get_scorer.return_value = mock_scorer
            with pytest.raises(RuntimeError, match="commit failed"):
                await trigger_scoring_for_simulation(sim_run_id, db)

        assert events == ["commit"]
