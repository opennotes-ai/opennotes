from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


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
    async def test_dispatch_creates_correct_workflow_id(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            dispatch_community_scoring,
        )

        cs_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.workflow_id = f"score-community-{cs_id}"

        mock_client = MagicMock()
        mock_client.enqueue.return_value = mock_handle

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            wf_id = await dispatch_community_scoring(cs_id)

        assert wf_id == f"score-community-{cs_id}"
        mock_client.enqueue.assert_called_once()

        call_args = mock_client.enqueue.call_args
        options = call_args[0][0]
        assert options["queue_name"] == "community_scoring"
        assert options["workflow_id"] == f"score-community-{cs_id}"
        assert options["deduplication_id"] == f"score-community-{cs_id}"
        assert call_args[0][1] == str(cs_id)

    @pytest.mark.asyncio
    async def test_dispatch_uses_correct_workflow_name(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            SCORE_COMMUNITY_SERVER_WORKFLOW_NAME,
            dispatch_community_scoring,
        )

        cs_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.workflow_id = f"score-community-{cs_id}"

        mock_client = MagicMock()
        mock_client.enqueue.return_value = mock_handle

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            await dispatch_community_scoring(cs_id)

        call_args = mock_client.enqueue.call_args
        options = call_args[0][0]
        assert options["workflow_name"] == SCORE_COMMUNITY_SERVER_WORKFLOW_NAME

    @pytest.mark.asyncio
    async def test_dispatch_idempotent_workflow_id(self) -> None:
        from src.simulation.workflows.scoring_workflow import (
            dispatch_community_scoring,
        )

        cs_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.workflow_id = f"score-community-{cs_id}"

        mock_client = MagicMock()
        mock_client.enqueue.return_value = mock_handle

        with (
            patch(
                "src.dbos_workflows.config.get_dbos_client",
                return_value=mock_client,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *args: fn(*args)),
        ):
            await dispatch_community_scoring(cs_id)
            await dispatch_community_scoring(cs_id)

        call1_options = mock_client.enqueue.call_args_list[0].args[0]
        call2_options = mock_client.enqueue.call_args_list[1].args[0]
        assert call1_options["workflow_id"] == call2_options["workflow_id"]
        assert call1_options["deduplication_id"] == call2_options["deduplication_id"]
