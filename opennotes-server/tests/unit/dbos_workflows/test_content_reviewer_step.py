"""Tests for content_reviewer_step DBOS step.

Tests the content_reviewer_step that replaces relevance_filter_step in the
content scan workflow. Also verifies _run_batch_scan_steps dispatches to
content_reviewer_step.

Test structure mirrors test_content_scan_workflow.py: __wrapped__ is used to
bypass DBOS decorators, all external services are mocked.

Patch targets for local imports inside content_reviewer_step function body:
- ContentReviewerService: src.bulk_content_scan.content_reviewer_agent.ContentReviewerService
- ModerationPolicyEvaluator: src.bulk_content_scan.policy_evaluator.ModerationPolicyEvaluator
- BulkContentScanService: src.bulk_content_scan.service.BulkContentScanService
- _get_llm_service: src.dbos_workflows.content_monitoring_workflows._get_llm_service
- EmbeddingService: src.fact_checking.embedding_service.EmbeddingService
- get_flashpoint_service: src.bulk_content_scan.flashpoint_service.get_flashpoint_service
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


def _make_mock_session_stack():
    """Build mock Redis connection and session context manager."""
    mock_redis = AsyncMock()
    mock_session = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session_maker = MagicMock(return_value=mock_session_ctx)
    return mock_redis, mock_session, mock_session_maker


def _make_scan_candidate_dict(
    message_id: str = "msg-1",
    scan_type: str = "similarity",
    score: float = 0.85,
    community_server_id: str | None = None,
) -> dict:
    return {
        "message": {
            "message_id": message_id,
            "channel_id": "chan-1",
            "content": "test content",
            "author_id": "author-1",
            "author_username": "testuser",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "community_server_id": community_server_id or str(uuid4()),
            "attachment_urls": None,
            "embed_content": None,
        },
        "scan_type": scan_type,
        "match_data": {
            "scan_type": "similarity",
            "score": score,
            "matched_claim": "test claim",
            "matched_source": "https://example.com",
            "fact_check_item_id": None,
        },
        "score": score,
        "matched_content": "test claim",
        "matched_source": "https://example.com",
    }


def _base_patches(
    mock_redis: AsyncMock,
    mock_session_maker: MagicMock,
    load_return=None,
    load_side_effect=None,
    scan_inactive: bool = False,
    skip_terminal: bool = False,
):
    """Return list of patch() context managers for the shared infrastructure mocks."""
    patches = [
        patch("src.config.get_settings", return_value=MagicMock(REDIS_URL="redis://test")),
        patch(
            "src.cache.redis_client.get_shared_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ),
        patch("src.database.get_session_maker", return_value=mock_session_maker),
        patch(
            "src.dbos_workflows.content_scan_workflow._scan_is_inactive_async",
            new_callable=AsyncMock,
            return_value=scan_inactive,
        ),
        patch(
            "src.dbos_workflows.content_monitoring_workflows._get_llm_service",
            return_value=MagicMock(),
        ),
        patch(
            "src.fact_checking.embedding_service.EmbeddingService",
            return_value=MagicMock(),
        ),
        patch(
            "src.bulk_content_scan.flashpoint_service.get_flashpoint_service",
            return_value=MagicMock(),
        ),
    ]
    if load_side_effect is not None:
        if isinstance(load_side_effect, list):
            load_mock = AsyncMock(side_effect=load_side_effect)
            patches.append(
                patch(
                    "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                    new=load_mock,
                )
            )
        else:
            patches.append(
                patch(
                    "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                    new_callable=AsyncMock,
                    side_effect=load_side_effect,
                )
            )
    elif load_return is not None:
        patches.append(
            patch(
                "src.dbos_workflows.content_scan_workflow.load_messages_from_redis",
                new_callable=AsyncMock,
                return_value=load_return,
            )
        )
    if not scan_inactive:
        patches.append(
            patch(
                "src.dbos_workflows.content_scan_workflow._skip_step_persist_if_scan_terminal",
                new_callable=AsyncMock,
                return_value=skip_terminal,
            )
        )
    return patches


class TestContentReviewerStep:
    """Tests for content_reviewer_step DBOS step."""

    def test_empty_candidates_returns_zero_flagged(self) -> None:
        """When no candidates are found in Redis, returns {flagged_count: 0, errors: 0}."""
        from src.dbos_workflows.content_scan_workflow import content_reviewer_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        mock_redis, _, mock_session_maker = _make_mock_session_stack()

        patches = _base_patches(mock_redis, mock_session_maker, load_return=[], scan_inactive=False)

        with (
            patch.multiple(*patches)
            if False
            else None or __import__("contextlib").ExitStack() as stack
        ):
            for p in patches:
                stack.enter_context(p)
            result = content_reviewer_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                similarity_candidates_key="",
                flashpoint_candidates_key="",
            )

        assert result == {"flagged_count": 0, "errors": 0, "policy_decisions": []}

    def test_similarity_candidates_produce_flagged_count(self) -> None:
        """Candidates from similarity scan produce flagged_count via ContentReviewerService."""
        from src.bulk_content_scan.schemas import ContentModerationClassificationResult
        from src.dbos_workflows.content_scan_workflow import content_reviewer_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        mock_redis, _, mock_session_maker = _make_mock_session_stack()

        candidate_dict = _make_scan_candidate_dict(message_id="msg-42")

        mock_classification = MagicMock(spec=ContentModerationClassificationResult)
        mock_classification.confidence = 0.9
        mock_classification.category_labels = {"misinformation": True}
        mock_classification.category_scores = None
        mock_classification.recommended_action = "hide"
        mock_classification.action_tier = "tier_1_immediate"
        mock_classification.explanation = "Matches known claim"

        mock_policy_decision = MagicMock()
        mock_policy_decision.action_tier = MagicMock(value="tier_1_immediate")
        mock_policy_decision.action_type = MagicMock(value="hide")
        mock_policy_decision.review_group = MagicMock(value="staff")
        mock_policy_decision.reason = "Tier 1 triggered"

        mock_reviewer_service = MagicMock()
        mock_reviewer_service.classify = AsyncMock(return_value=mock_classification)

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(return_value=mock_policy_decision)

        mock_service = MagicMock()
        mock_service.append_flagged_result = AsyncMock()

        patches = _base_patches(mock_redis, mock_session_maker, load_return=[candidate_dict])

        with __import__("contextlib").ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.content_reviewer_agent.ContentReviewerService",
                    return_value=mock_reviewer_service,
                )
            )
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.policy_evaluator.ModerationPolicyEvaluator",
                    return_value=mock_evaluator,
                )
            )
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.service.BulkContentScanService",
                    return_value=mock_service,
                )
            )
            result = content_reviewer_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                similarity_candidates_key="sim-key",
                flashpoint_candidates_key="",
            )

        assert result["flagged_count"] == 1
        assert result["errors"] == 0
        assert len(result["policy_decisions"]) == 1
        mock_reviewer_service.classify.assert_awaited_once()
        mock_evaluator.evaluate.assert_called_once()
        mock_service.append_flagged_result.assert_awaited_once()

    def test_evidence_from_both_steps_aggregated_per_message(self) -> None:
        """Similarity + flashpoint candidates for SAME message_id yield one agent call with all evidence."""
        from src.bulk_content_scan.schemas import ContentModerationClassificationResult
        from src.dbos_workflows.content_scan_workflow import content_reviewer_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        mock_redis, _, mock_session_maker = _make_mock_session_stack()

        sim_candidate = _make_scan_candidate_dict(message_id="msg-1", scan_type="similarity")
        fp_candidate = {
            **_make_scan_candidate_dict(message_id="msg-1", scan_type="conversation_flashpoint"),
            "match_data": {
                "scan_type": "conversation_flashpoint",
                "derailment_score": 72,
                "risk_level": "Hostile",
                "reasoning": "escalating conflict",
                "context_messages": 5,
            },
        }

        mock_classification = MagicMock(spec=ContentModerationClassificationResult)
        mock_classification.confidence = 0.8
        mock_classification.category_labels = {"harassment": True}
        mock_classification.category_scores = None
        mock_classification.recommended_action = "review"
        mock_classification.action_tier = "tier_2_consensus"
        mock_classification.explanation = "Flashpoint detected"

        mock_policy_decision = MagicMock()
        mock_policy_decision.action_tier = MagicMock(value="tier_2_consensus")
        mock_policy_decision.action_type = MagicMock(value="hide")
        mock_policy_decision.review_group = MagicMock(value="community")
        mock_policy_decision.reason = "Tier 2 triggered"

        mock_reviewer_service = MagicMock()
        mock_reviewer_service.classify = AsyncMock(return_value=mock_classification)

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(return_value=mock_policy_decision)

        mock_service = MagicMock()
        mock_service.append_flagged_result = AsyncMock()

        both_candidates = [sim_candidate, fp_candidate]

        patches = _base_patches(mock_redis, mock_session_maker, load_return=both_candidates)

        with __import__("contextlib").ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.content_reviewer_agent.ContentReviewerService",
                    return_value=mock_reviewer_service,
                )
            )
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.policy_evaluator.ModerationPolicyEvaluator",
                    return_value=mock_evaluator,
                )
            )
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.service.BulkContentScanService",
                    return_value=mock_service,
                )
            )
            result = content_reviewer_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                similarity_candidates_key="sim-key",
                flashpoint_candidates_key="",
            )

        assert result["flagged_count"] == 1
        mock_reviewer_service.classify.assert_awaited_once()
        classify_call = mock_reviewer_service.classify.call_args
        assert len(classify_call.kwargs["pre_computed_evidence"]) == 2

    def test_terminal_scan_check_skips_processing(self) -> None:
        """If scan is inactive/terminal, step returns early without calling the agent."""
        from src.dbos_workflows.content_scan_workflow import content_reviewer_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        mock_redis, _, mock_session_maker = _make_mock_session_stack()

        candidate_dict = _make_scan_candidate_dict()

        mock_reviewer_service = MagicMock()
        mock_reviewer_service.classify = AsyncMock()

        patches = _base_patches(
            mock_redis,
            mock_session_maker,
            load_return=[candidate_dict],
            scan_inactive=True,
        )

        with __import__("contextlib").ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.content_reviewer_agent.ContentReviewerService",
                    return_value=mock_reviewer_service,
                )
            )
            result = content_reviewer_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                similarity_candidates_key="sim-key",
                flashpoint_candidates_key="",
            )

        assert result == {"flagged_count": 0, "errors": 0, "policy_decisions": []}
        mock_reviewer_service.classify.assert_not_awaited()

    def test_post_classify_terminal_check_skips_persistence(self) -> None:
        """If scan goes terminal after classification, results are not persisted."""
        from src.bulk_content_scan.schemas import ContentModerationClassificationResult
        from src.dbos_workflows.content_scan_workflow import content_reviewer_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        mock_redis, _, mock_session_maker = _make_mock_session_stack()

        candidate_dict = _make_scan_candidate_dict()

        mock_classification = MagicMock(spec=ContentModerationClassificationResult)
        mock_classification.confidence = 0.9
        mock_classification.category_labels = {"misinformation": True}
        mock_classification.category_scores = None
        mock_classification.recommended_action = "hide"
        mock_classification.action_tier = "tier_1_immediate"
        mock_classification.explanation = "Matches known claim"

        mock_policy_decision = MagicMock()
        mock_policy_decision.action_tier = MagicMock(value="tier_1_immediate")
        mock_policy_decision.action_type = MagicMock(value="hide")
        mock_policy_decision.review_group = MagicMock(value="staff")
        mock_policy_decision.reason = "Tier 1 triggered"

        mock_reviewer_service = MagicMock()
        mock_reviewer_service.classify = AsyncMock(return_value=mock_classification)

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(return_value=mock_policy_decision)

        mock_service = MagicMock()
        mock_service.append_flagged_result = AsyncMock()

        patches = _base_patches(
            mock_redis,
            mock_session_maker,
            load_return=[candidate_dict],
            skip_terminal=True,
        )

        with __import__("contextlib").ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.content_reviewer_agent.ContentReviewerService",
                    return_value=mock_reviewer_service,
                )
            )
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.policy_evaluator.ModerationPolicyEvaluator",
                    return_value=mock_evaluator,
                )
            )
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.service.BulkContentScanService",
                    return_value=mock_service,
                )
            )
            result = content_reviewer_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                similarity_candidates_key="sim-key",
                flashpoint_candidates_key="",
            )

        assert result == {"flagged_count": 0, "errors": 0, "policy_decisions": []}
        mock_service.append_flagged_result.assert_not_awaited()

    def test_redis_key_expiry_logs_warning_and_continues(self) -> None:
        """If Redis key has expired, logs warning and increments errors."""
        from src.dbos_workflows.content_scan_workflow import content_reviewer_step

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        mock_redis, _, mock_session_maker = _make_mock_session_stack()

        patches = _base_patches(
            mock_redis,
            mock_session_maker,
            load_side_effect=ValueError("key expired"),
        )

        with __import__("contextlib").ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = content_reviewer_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                similarity_candidates_key="sim-key",
                flashpoint_candidates_key="",
            )

        assert result["flagged_count"] == 0
        assert result["errors"] == 1

    def test_policy_decisions_included_in_output(self) -> None:
        """Policy decisions are serialized and returned in step output."""
        from src.bulk_content_scan.policy_evaluator import PolicyDecision
        from src.bulk_content_scan.schemas import ContentModerationClassificationResult
        from src.dbos_workflows.content_scan_workflow import content_reviewer_step
        from src.moderation_actions.models import ActionTier, ActionType, ReviewGroup

        scan_id = str(uuid4())
        community_server_id = str(uuid4())
        mock_redis, _, mock_session_maker = _make_mock_session_stack()

        candidate_dict = _make_scan_candidate_dict(message_id="msg-77")

        mock_classification = MagicMock(spec=ContentModerationClassificationResult)
        mock_classification.confidence = 0.95
        mock_classification.category_labels = {"violence": True}
        mock_classification.category_scores = None
        mock_classification.recommended_action = "hide"
        mock_classification.action_tier = "tier_1_immediate"
        mock_classification.explanation = "Violent content detected"

        real_decision = PolicyDecision(
            action_tier=ActionTier.TIER_1_IMMEDIATE,
            action_type=ActionType.HIDE,
            review_group=ReviewGroup.STAFF,
            reason="Tier 1 auto-action triggered by label 'violence'",
        )

        mock_reviewer_service = MagicMock()
        mock_reviewer_service.classify = AsyncMock(return_value=mock_classification)

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(return_value=real_decision)

        mock_service = MagicMock()
        mock_service.append_flagged_result = AsyncMock()

        patches = _base_patches(mock_redis, mock_session_maker, load_return=[candidate_dict])

        with __import__("contextlib").ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.content_reviewer_agent.ContentReviewerService",
                    return_value=mock_reviewer_service,
                )
            )
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.policy_evaluator.ModerationPolicyEvaluator",
                    return_value=mock_evaluator,
                )
            )
            stack.enter_context(
                patch(
                    "src.bulk_content_scan.service.BulkContentScanService",
                    return_value=mock_service,
                )
            )
            result = content_reviewer_step.__wrapped__(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                similarity_candidates_key="sim-key",
                flashpoint_candidates_key="",
            )

        assert result["flagged_count"] == 1
        assert len(result["policy_decisions"]) == 1
        decision = result["policy_decisions"][0]
        assert decision["message_id"] == "msg-77"
        assert decision["action_tier"] == "tier_1_immediate"
        assert decision["action_type"] == "hide"
        assert decision["review_group"] == "staff"
        assert "reason" in decision


class TestRunBatchScanStepsDispatch:
    """Tests that _run_batch_scan_steps dispatches to content_reviewer_step."""

    def test_run_batch_scan_steps_calls_content_reviewer_step(self) -> None:
        """_run_batch_scan_steps dispatches to content_reviewer_step, not relevance_filter_step."""
        from src.dbos_workflows.content_scan_workflow import _run_batch_scan_steps

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        mock_similarity_result = {
            "similarity_candidates_key": "sim-key-1",
            "candidate_count": 3,
        }
        mock_flashpoint_result = {
            "flashpoint_candidates_key": "fp-key-1",
            "candidate_count": 2,
        }
        mock_reviewer_result = {
            "flagged_count": 2,
            "errors": 0,
            "policy_decisions": [],
        }

        with __import__("contextlib").ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.similarity_scan_step",
                    return_value=mock_similarity_result,
                )
            )
            stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.flashpoint_scan_step",
                    return_value=mock_flashpoint_result,
                )
            )
            mock_reviewer = stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.content_reviewer_step",
                    return_value=mock_reviewer_result,
                )
            )
            mock_relevance = stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.relevance_filter_step",
                )
            )

            flagged_count, errors = _run_batch_scan_steps(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                filtered_messages_key="filtered-key",
                context_maps_key="context-key",
                scan_types=["similarity", "conversation_flashpoint"],
                step_errors=[],
            )

        assert flagged_count == 2
        assert errors == 0
        mock_reviewer.assert_called_once_with(
            scan_id=scan_id,
            community_server_id=community_server_id,
            batch_number=1,
            similarity_candidates_key="sim-key-1",
            flashpoint_candidates_key="fp-key-1",
        )
        mock_relevance.assert_not_called()

    def test_run_batch_scan_steps_does_not_call_relevance_filter_step(self) -> None:
        """Ensures relevance_filter_step is NOT called (it is deprecated)."""
        from src.dbos_workflows.content_scan_workflow import _run_batch_scan_steps

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        with __import__("contextlib").ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.similarity_scan_step",
                    return_value={"similarity_candidates_key": "", "candidate_count": 0},
                )
            )
            stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.flashpoint_scan_step",
                    return_value={"flashpoint_candidates_key": "", "candidate_count": 0},
                )
            )
            stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.content_reviewer_step",
                    return_value={"flagged_count": 0, "errors": 0, "policy_decisions": []},
                )
            )
            mock_relevance = stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.relevance_filter_step",
                )
            )

            _run_batch_scan_steps(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                filtered_messages_key="filtered-key",
                context_maps_key="context-key",
                scan_types=["similarity"],
                step_errors=[],
            )

        mock_relevance.assert_not_called()

    def test_content_reviewer_step_error_is_handled_gracefully(self) -> None:
        """Errors from content_reviewer_step are caught and appended to step_errors."""
        from src.dbos_workflows.content_scan_workflow import _run_batch_scan_steps

        scan_id = str(uuid4())
        community_server_id = str(uuid4())

        with __import__("contextlib").ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.similarity_scan_step",
                    return_value={"similarity_candidates_key": "sim-key", "candidate_count": 1},
                )
            )
            stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.flashpoint_scan_step",
                    return_value={"flashpoint_candidates_key": "", "candidate_count": 0},
                )
            )
            stack.enter_context(
                patch(
                    "src.dbos_workflows.content_scan_workflow.content_reviewer_step",
                    side_effect=RuntimeError("LLM service unavailable"),
                )
            )

            flagged_count, errors = _run_batch_scan_steps(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=1,
                filtered_messages_key="filtered-key",
                context_maps_key="context-key",
                scan_types=["similarity"],
                step_errors=[],
            )

        assert flagged_count == 0
        assert errors == 1
