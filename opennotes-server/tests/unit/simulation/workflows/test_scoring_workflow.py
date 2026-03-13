from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dbos._error import DBOSQueueDeduplicatedError, DBOSWorkflowConflictIDError


def _run_coro(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_mock_session_ctx(session):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _patch_run_sync():
    return patch(
        "src.simulation.workflows.scoring_workflow.run_sync",
        side_effect=_run_coro,
    )


def _patch_session(mock_session_ctx):
    return patch(
        "src.database.get_session_maker",
        return_value=lambda: mock_session_ctx,
    )


def _make_fake_dbos_dispatch_environment():
    dispatch_state = {"workflow_id": None, "deduplication_id": None}
    active_deduplication_ids: set[str] = set()
    seen_workflow_ids: set[str] = set()

    @contextmanager
    def fake_set_workflow_id(workflow_id: str):
        previous_workflow_id = dispatch_state["workflow_id"]
        dispatch_state["workflow_id"] = workflow_id
        try:
            yield MagicMock()
        finally:
            dispatch_state["workflow_id"] = previous_workflow_id

    @contextmanager
    def fake_set_enqueue_options(*, deduplication_id: str):
        previous_deduplication_id = dispatch_state["deduplication_id"]
        dispatch_state["deduplication_id"] = deduplication_id
        try:
            yield MagicMock()
        finally:
            dispatch_state["deduplication_id"] = previous_deduplication_id

    def enqueue(*_args, **_kwargs):
        workflow_id = dispatch_state["workflow_id"]
        deduplication_id = dispatch_state["deduplication_id"]
        assert workflow_id is not None
        assert deduplication_id is not None

        if workflow_id in seen_workflow_ids:
            raise DBOSWorkflowConflictIDError(workflow_id)
        if deduplication_id in active_deduplication_ids:
            raise DBOSQueueDeduplicatedError(
                workflow_id,
                "community_scoring",
                deduplication_id,
            )

        seen_workflow_ids.add(workflow_id)
        active_deduplication_ids.add(deduplication_id)

        handle = MagicMock()
        handle.get_workflow_id.return_value = workflow_id
        return handle

    return {
        "active_deduplication_ids": active_deduplication_ids,
        "enqueue": enqueue,
        "set_enqueue_options": fake_set_enqueue_options,
        "set_workflow_id": fake_set_workflow_id,
    }


class TestWorkflowNameConstants:
    def test_workflow_name_matches_qualname(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            SCORE_COMMUNITY_SERVER_WORKFLOW_NAME,
            score_community_server,
        )

        assert score_community_server.__qualname__ == SCORE_COMMUNITY_SERVER_WORKFLOW_NAME

    def test_workflow_name_is_string(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            SCORE_COMMUNITY_SERVER_WORKFLOW_NAME,
        )

        assert isinstance(SCORE_COMMUNITY_SERVER_WORKFLOW_NAME, str)
        assert len(SCORE_COMMUNITY_SERVER_WORKFLOW_NAME) > 0


class TestRunCommunityScoringStep:
    def test_calls_score_community_server_notes(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            run_community_scoring_step,
        )

        cs_id = uuid4()
        mock_result = MagicMock()
        mock_result.community_server_id = cs_id
        mock_result.unscored_notes_processed = 5
        mock_result.rescored_notes_processed = 3
        mock_result.total_scores_computed = 8
        mock_result.tier_name = "Standard"
        mock_result.scorer_type = "BayesianAverageScorer"

        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch(
                "src.simulation.scoring_integration.score_community_server_notes",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_score,
        ):
            result = run_community_scoring_step.__wrapped__(str(cs_id))

        mock_score.assert_called_once()
        assert result["community_server_id"] == str(cs_id)
        assert result["unscored_notes_processed"] == 5
        assert result["rescored_notes_processed"] == 3
        assert result["total_scores_computed"] == 8
        assert result["tier_name"] == "Standard"
        assert result["scorer_type"] == "BayesianAverageScorer"

    def test_returns_serializable_dict(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            run_community_scoring_step,
        )

        cs_id = uuid4()
        mock_result = MagicMock()
        mock_result.community_server_id = cs_id
        mock_result.unscored_notes_processed = 0
        mock_result.rescored_notes_processed = 0
        mock_result.total_scores_computed = 0
        mock_result.tier_name = "Minimal"
        mock_result.scorer_type = "none"

        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch(
                "src.simulation.scoring_integration.score_community_server_notes",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            result = run_community_scoring_step.__wrapped__(str(cs_id))

        assert isinstance(result, dict)
        expected_keys = {
            "community_server_id",
            "unscored_notes_processed",
            "rescored_notes_processed",
            "total_scores_computed",
            "tier_name",
            "scorer_type",
        }
        assert set(result.keys()) == expected_keys


class TestRunCommunityScoringStepErrorPropagation:
    def test_exception_propagates_through_step(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            run_community_scoring_step,
        )

        cs_id = uuid4()
        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch(
                "src.simulation.scoring_integration.score_community_server_notes",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Database connection lost"),
            ),
            pytest.raises(RuntimeError, match="Database connection lost"),
        ):
            run_community_scoring_step.__wrapped__(str(cs_id))

    def test_value_error_propagates_through_step(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            run_community_scoring_step,
        )

        cs_id = uuid4()
        mock_session = AsyncMock()
        mock_session_ctx = _make_mock_session_ctx(mock_session)

        with (
            _patch_run_sync(),
            _patch_session(mock_session_ctx),
            patch(
                "src.simulation.scoring_integration.score_community_server_notes",
                new_callable=AsyncMock,
                side_effect=ValueError("Invalid community server"),
            ),
            pytest.raises(ValueError, match="Invalid community server"),
        ):
            run_community_scoring_step.__wrapped__(str(cs_id))


class TestScoreCommunityServerWorkflow:
    def test_workflow_calls_step_and_returns_result(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            score_community_server,
        )

        cs_id = str(uuid4())
        expected_result = {
            "community_server_id": cs_id,
            "unscored_notes_processed": 10,
            "rescored_notes_processed": 5,
            "total_scores_computed": 15,
            "tier_name": "Standard",
            "scorer_type": "BayesianAverageScorer",
        }

        with patch(
            "src.simulation.workflows.scoring_workflow.run_community_scoring_step",
            return_value=expected_result,
        ) as mock_step:
            result = score_community_server.__wrapped__(cs_id)

        mock_step.assert_called_once_with(cs_id)
        assert result == expected_result
        assert result["total_scores_computed"] == 15


class TestDispatchCommunityScoring:
    @pytest.mark.asyncio
    async def test_dispatch_uses_stable_deduplication_id_per_community(self) -> None:
        from src.simulation.workflows.scoring_workflow import dispatch_community_scoring

        cs_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = f"score-community-{cs_id}-1709000000"
        captured_dedup_ids: list[str] = []

        def capture_enqueue_options(*, deduplication_id: str):
            captured_dedup_ids.append(deduplication_id)
            return MagicMock()

        with (
            patch(
                "src.simulation.workflows.scoring_workflow.community_scoring_queue"
            ) as mock_queue,
            patch("dbos.SetWorkflowID"),
            patch("dbos.SetEnqueueOptions", side_effect=capture_enqueue_options),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            mock_queue.enqueue.return_value = mock_handle
            await dispatch_community_scoring(cs_id)

        assert captured_dedup_ids == [f"score-community-{cs_id}"]

    @pytest.mark.asyncio
    async def test_dispatch_creates_workflow_id_with_temporal_component(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            dispatch_community_scoring,
            score_community_server,
        )

        cs_id = uuid4()
        expected_timestamp_ns = 1709000000000000000

        captured_wf_id = None
        mock_handle = MagicMock()

        def capture_set_wf_id(wf_id):
            nonlocal captured_wf_id
            captured_wf_id = wf_id
            mock_handle.get_workflow_id.return_value = wf_id
            return MagicMock()

        with (
            patch(
                "src.simulation.workflows.scoring_workflow.community_scoring_queue"
            ) as mock_queue,
            patch("dbos.SetWorkflowID", side_effect=capture_set_wf_id),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
            patch(
                "src.simulation.workflows.scoring_workflow.time.time_ns",
                return_value=expected_timestamp_ns,
            ),
        ):
            mock_queue.enqueue.return_value = mock_handle
            wf_id = await dispatch_community_scoring(cs_id)

        prefix = f"score-community-{cs_id}-"
        assert wf_id == f"{prefix}{expected_timestamp_ns}"
        assert captured_wf_id == wf_id

        mock_queue.enqueue.assert_called_once_with(score_community_server, str(cs_id))

    @pytest.mark.asyncio
    async def test_dispatch_uses_correct_workflow_name(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            dispatch_community_scoring,
            score_community_server,
        )

        cs_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = f"score-community-{cs_id}"

        with (
            patch(
                "src.simulation.workflows.scoring_workflow.community_scoring_queue"
            ) as mock_queue,
            patch("dbos.SetWorkflowID"),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            mock_queue.enqueue.return_value = mock_handle
            await dispatch_community_scoring(cs_id)

        mock_queue.enqueue.assert_called_once_with(score_community_server, str(cs_id))

    @pytest.mark.asyncio
    async def test_dispatch_successive_calls_produce_different_workflow_ids(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            dispatch_community_scoring,
        )

        cs_id = uuid4()
        captured_ids: list[str] = []

        mock_handle = MagicMock()

        def capture_set_wf_id(wf_id):
            captured_ids.append(wf_id)
            mock_handle.get_workflow_id.return_value = wf_id
            return MagicMock()

        with (
            patch(
                "src.simulation.workflows.scoring_workflow.community_scoring_queue"
            ) as mock_queue,
            patch("dbos.SetWorkflowID", side_effect=capture_set_wf_id),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
            patch(
                "src.simulation.workflows.scoring_workflow.time.time_ns",
                side_effect=[1000000000, 1000000001],
            ),
        ):
            mock_queue.enqueue.return_value = mock_handle
            await dispatch_community_scoring(cs_id)
            await dispatch_community_scoring(cs_id)

        assert len(captured_ids) == 2
        assert captured_ids[0] != captured_ids[1]
        assert captured_ids[0] == f"score-community-{cs_id}-1000000000"
        assert captured_ids[1] == f"score-community-{cs_id}-1000000001"

    @pytest.mark.asyncio
    async def test_completed_same_second_rerun_uses_new_workflow_id(self) -> None:
        from src.simulation.workflows.scoring_workflow import dispatch_community_scoring

        cs_id = uuid4()
        fake_dbos = _make_fake_dbos_dispatch_environment()

        with (
            patch(
                "src.simulation.workflows.scoring_workflow.community_scoring_queue.enqueue",
                side_effect=fake_dbos["enqueue"],
            ),
            patch("dbos.SetWorkflowID", side_effect=fake_dbos["set_workflow_id"]),
            patch(
                "dbos.SetEnqueueOptions",
                side_effect=fake_dbos["set_enqueue_options"],
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
            patch(
                "src.simulation.workflows.scoring_workflow.time.time",
                return_value=1000000,
            ),
            patch(
                "src.simulation.workflows.scoring_workflow.time.time_ns",
                side_effect=[1000000000000000000, 1000000000000000001],
            ),
        ):
            first_workflow_id = await dispatch_community_scoring(cs_id)
            fake_dbos["active_deduplication_ids"].clear()
            second_workflow_id = await dispatch_community_scoring(cs_id)

        assert first_workflow_id != second_workflow_id

    @pytest.mark.asyncio
    async def test_in_flight_duplicate_dispatch_raises_queue_deduplication_error(self) -> None:
        from src.simulation.workflows.scoring_workflow import dispatch_community_scoring

        cs_id = uuid4()
        fake_dbos = _make_fake_dbos_dispatch_environment()

        with (
            patch(
                "src.simulation.workflows.scoring_workflow.community_scoring_queue.enqueue",
                side_effect=fake_dbos["enqueue"],
            ),
            patch("dbos.SetWorkflowID", side_effect=fake_dbos["set_workflow_id"]),
            patch(
                "dbos.SetEnqueueOptions",
                side_effect=fake_dbos["set_enqueue_options"],
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
            patch(
                "src.simulation.workflows.scoring_workflow.time.time",
                return_value=1000000,
            ),
            patch(
                "src.simulation.workflows.scoring_workflow.time.time_ns",
                side_effect=[1000000000000000000, 1000000000000000001],
            ),
        ):
            await dispatch_community_scoring(cs_id)
            with pytest.raises(DBOSQueueDeduplicatedError):
                await dispatch_community_scoring(cs_id)
