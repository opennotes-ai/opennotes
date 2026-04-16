"""Tests for action_bridge - ModerationAction creation from PolicyDecision.

TDD: RED -> GREEN -> REFACTOR
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pendulum
import pytest
from sqlalchemy.exc import IntegrityError

from src.bulk_content_scan.policy_evaluator import PolicyDecision
from src.bulk_content_scan.schemas import (
    ContentModerationClassificationResult,
    SimilarityMatch,
)
from src.moderation_actions.models import ActionState, ActionTier, ActionType, ReviewGroup

pytestmark = pytest.mark.unit


_SENTINEL: dict = {}


def _make_classification(
    category_labels: dict[str, bool] | None = None,
    category_scores: dict[str, float] | None = _SENTINEL,  # type: ignore[assignment]
    confidence: float = 0.95,
    explanation: str = "test classification",
) -> ContentModerationClassificationResult:
    resolved_scores: dict[str, float] | None = (
        {"harassment": 0.95} if category_scores is _SENTINEL else category_scores
    )
    return ContentModerationClassificationResult(
        confidence=confidence,
        category_labels=category_labels or {"harassment": True},
        category_scores=resolved_scores,
        explanation=explanation,
    )


def _make_tier1_decision() -> PolicyDecision:
    return PolicyDecision(
        action_tier=ActionTier.TIER_1_IMMEDIATE,
        action_type=ActionType.HIDE,
        review_group=ReviewGroup.STAFF,
        reason="Tier 1 auto-action triggered by label 'harassment'",
    )


def _make_tier2_decision() -> PolicyDecision:
    return PolicyDecision(
        action_tier=ActionTier.TIER_2_CONSENSUS,
        action_type=ActionType.HIDE,
        review_group=ReviewGroup.TRUSTED,
        reason="Tier 2 consensus review triggered by label 'harassment'",
    )


def _make_pass_decision() -> PolicyDecision:
    return PolicyDecision(
        action_tier=None,
        action_type=None,
        review_group=None,
        reason="No configured threshold exceeded; no action required",
    )


def _make_content_item():
    from src.bulk_content_scan.schemas import ContentItem

    return ContentItem(
        content_id="discord_msg_123",
        platform="discord",
        content_text="This is test content",
        author_id="user_456",
        timestamp=pendulum.now("UTC"),
        channel_id="channel_789",
        community_server_id="server_abc",
    )


def _make_mock_action(
    action_id: UUID | None = None,
    request_id: UUID | None = None,
    community_server_id: UUID | None = None,
    action_state: str = ActionState.PROPOSED,
    action_type: str = ActionType.HIDE,
    action_tier: str = ActionTier.TIER_1_IMMEDIATE,
    review_group: str = ReviewGroup.STAFF,
    classifier_evidence: dict[str, Any] | None = None,
) -> MagicMock:
    action = MagicMock()
    action.id = action_id or uuid4()
    action.request_id = request_id or uuid4()
    action.community_server_id = community_server_id or uuid4()
    action.action_state = action_state
    action.action_type = action_type
    action.action_tier = action_tier
    action.review_group = review_group
    action.classifier_evidence = classifier_evidence or {
        "labels": {"harassment": True},
        "scores": {"harassment": 0.95},
    }
    action.applied_at = None
    return action


class TestCreateModerationActionFromPolicy:
    """Tests for create_moderation_action_from_policy."""

    @pytest.mark.asyncio
    async def test_tier1_decision_creates_action_with_applied_state(self):
        """Tier 1 decision creates ModerationAction with APPLIED state."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        mock_action = _make_mock_action(
            request_id=request_id,
            community_server_id=community_server_id,
            action_state=ActionState.APPLIED,
        )

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
                return_value=mock_action,
            ) as mock_create,
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert result is not None
        assert newly_created is True
        call_args = mock_create.call_args
        create_data = call_args[1]["data"] if "data" in call_args[1] else call_args[0][1]
        assert create_data.action_state == ActionState.APPLIED

    @pytest.mark.asyncio
    async def test_tier1_decision_sets_applied_at(self):
        """Tier 1 decision creates ModerationAction with applied_at set."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        mock_action = _make_mock_action(action_state=ActionState.APPLIED)

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
                return_value=mock_action,
            ) as mock_create,
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        call_args = mock_create.call_args
        applied_at = call_args[1].get("applied_at") if call_args[1] else None
        assert applied_at is not None

    @pytest.mark.asyncio
    async def test_tier2_decision_creates_action_with_proposed_state(self):
        """Tier 2 decision creates ModerationAction with PROPOSED state."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier2_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        mock_action = _make_mock_action(
            action_state=ActionState.PROPOSED,
            action_tier=ActionTier.TIER_2_CONSENSUS,
        )

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
                return_value=mock_action,
            ) as mock_create,
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert result is not None
        assert newly_created is True
        call_args = mock_create.call_args
        create_data = call_args[1]["data"] if "data" in call_args[1] else call_args[0][1]
        assert create_data.action_state == ActionState.PROPOSED

    @pytest.mark.asyncio
    async def test_tier2_decision_does_not_set_applied_at(self):
        """Tier 2 decision does not set applied_at."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier2_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        mock_action = _make_mock_action(action_state=ActionState.PROPOSED)

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
                return_value=mock_action,
            ) as mock_create,
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        call_args = mock_create.call_args
        applied_at = call_args[1].get("applied_at") if call_args[1] else None
        assert applied_at is None

    @pytest.mark.asyncio
    async def test_pass_decision_returns_none(self):
        """Pass decision (action_tier=None) creates no ModerationAction, returns None."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_pass_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        with patch(
            "src.bulk_content_scan.action_bridge.create_moderation_action",
            new_callable=AsyncMock,
        ) as mock_create:
            result, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert result is None
        assert newly_created is False
        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_classifier_evidence_has_required_labels_key(self):
        """classifier_evidence must contain top-level 'labels' key."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification(
            category_labels={"harassment": True, "spam": False},
            category_scores={"harassment": 0.95, "spam": 0.10},
        )
        content_item = _make_content_item()

        mock_action = _make_mock_action()
        captured_evidence: dict[str, Any] = {}

        async def capture_create(db, data, **kwargs):
            captured_evidence.update(data.classifier_evidence)
            return mock_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=capture_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert "labels" in captured_evidence
        assert captured_evidence["labels"] == {"harassment": True, "spam": False}

    @pytest.mark.asyncio
    async def test_classifier_evidence_has_required_scores_key(self):
        """classifier_evidence must contain top-level 'scores' key."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification(
            category_labels={"harassment": True},
            category_scores={"harassment": 0.95},
        )
        content_item = _make_content_item()

        mock_action = _make_mock_action()
        captured_evidence: dict[str, Any] = {}

        async def capture_create(db, data, **kwargs):
            captured_evidence.update(data.classifier_evidence)
            return mock_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=capture_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert "scores" in captured_evidence
        assert captured_evidence["scores"] == {"harassment": 0.95}

    @pytest.mark.asyncio
    async def test_classifier_evidence_includes_metadata_with_explanation(self):
        """classifier_evidence metadata should include explanation from classification."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification(explanation="Detected harassment pattern")
        content_item = _make_content_item()

        mock_action = _make_mock_action()
        captured_evidence: dict[str, Any] = {}

        async def capture_create(db, data, **kwargs):
            captured_evidence.update(data.classifier_evidence)
            return mock_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=capture_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert "metadata" in captured_evidence
        assert captured_evidence["metadata"]["explanation"] == "Detected harassment pattern"
        assert captured_evidence["metadata"]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_classifier_evidence_includes_pre_computed_evidence(self):
        """classifier_evidence metadata should include pre_computed_evidence."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        pre_computed = [
            SimilarityMatch(
                score=0.85,
                matched_claim="test claim",
                matched_source="https://example.com",
                fact_check_item_id=uuid4(),
            )
        ]

        mock_action = _make_mock_action()
        captured_evidence: dict[str, Any] = {}

        async def capture_create(db, data, **kwargs):
            captured_evidence.update(data.classifier_evidence)
            return mock_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=capture_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
                pre_computed_evidence=pre_computed,
            )

        assert "metadata" in captured_evidence
        evidence_list = captured_evidence["metadata"]["pre_computed_evidence"]
        assert len(evidence_list) == 1
        assert evidence_list[0]["scan_type"] == "similarity"

    @pytest.mark.asyncio
    async def test_classifier_evidence_empty_pre_computed_evidence_when_none(self):
        """pre_computed_evidence defaults to empty list when not provided."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        mock_action = _make_mock_action()
        captured_evidence: dict[str, Any] = {}

        async def capture_create(db, data, **kwargs):
            captured_evidence.update(data.classifier_evidence)
            return mock_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=capture_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert captured_evidence["metadata"]["pre_computed_evidence"] == []

    @pytest.mark.asyncio
    async def test_request_fk_linked_correctly(self):
        """ModerationAction should be linked to the provided request_id."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        mock_action = _make_mock_action(request_id=request_id)
        captured_data = {}

        async def capture_create(db, data, **kwargs):
            captured_data["data"] = data
            return mock_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=capture_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert result is not None
        assert newly_created is True
        assert captured_data["data"].request_id == request_id

    @pytest.mark.asyncio
    async def test_community_server_id_passed_correctly(self):
        """ModerationAction should use the provided community_server_id."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        mock_action = _make_mock_action(community_server_id=community_server_id)
        captured_data = {}

        async def capture_create(db, data, **kwargs):
            captured_data["data"] = data
            return mock_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=capture_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert captured_data["data"].community_server_id == community_server_id

    @pytest.mark.asyncio
    async def test_idempotent_duplicate_call_returns_existing_action(self):
        """Duplicate call with same request_id+tier returns existing action without re-creating."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        existing_action = _make_mock_action(
            request_id=request_id,
            action_state=ActionState.APPLIED,
        )

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=existing_action,
            ),
        ):
            result, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert result is existing_action
        assert newly_created is False
        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_scores_defaults_to_empty_dict_when_none(self):
        """scores defaults to empty dict when classification.category_scores is None."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification(category_scores=None)
        content_item = _make_content_item()

        mock_action = _make_mock_action()
        captured_evidence: dict[str, Any] = {}

        async def capture_create(db, data, **kwargs):
            captured_evidence.update(data.classifier_evidence)
            return mock_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=capture_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert captured_evidence["scores"] == {}


class TestEmitPlatformActionEvent:
    """Tests for emit_platform_action_event."""

    @pytest.mark.asyncio
    async def test_tier1_action_emits_nats_event(self):
        """Tier 1 APPLIED action emits a platform action NATS event."""
        from src.bulk_content_scan.action_bridge import emit_platform_action_event

        mock_publisher = AsyncMock()
        mock_publisher.publish_moderation_action_applied = AsyncMock(return_value="event_id_123")

        content_item = _make_content_item()
        action = _make_mock_action(
            action_state=ActionState.APPLIED,
            action_tier=ActionTier.TIER_1_IMMEDIATE,
        )

        await emit_platform_action_event(
            publisher=mock_publisher,
            moderation_action=action,
            content_item=content_item,
        )

        mock_publisher.publish_moderation_action_applied.assert_called_once()

    @pytest.mark.asyncio
    async def test_tier1_event_includes_action_id_and_request_id(self):
        """Platform action event contains action_id and request_id."""
        from src.bulk_content_scan.action_bridge import emit_platform_action_event

        mock_publisher = AsyncMock()
        mock_publisher.publish_moderation_action_applied = AsyncMock(return_value="event_id_123")

        content_item = _make_content_item()
        action_id = uuid4()
        request_id = uuid4()
        community_server_id = uuid4()
        action = _make_mock_action(
            action_id=action_id,
            request_id=request_id,
            community_server_id=community_server_id,
            action_state=ActionState.APPLIED,
            action_tier=ActionTier.TIER_1_IMMEDIATE,
        )

        await emit_platform_action_event(
            publisher=mock_publisher,
            moderation_action=action,
            content_item=content_item,
        )

        call_kwargs = mock_publisher.publish_moderation_action_applied.call_args
        assert call_kwargs is not None
        kwargs = call_kwargs[1] if call_kwargs[1] else {}
        args = call_kwargs[0] if call_kwargs[0] else ()

        all_args = dict(
            zip(
                ["action_id", "request_id", "action_type", "community_server_id"],
                args,
                strict=False,
            )
        )
        all_args.update(kwargs)

        assert all_args.get("action_id") == action_id
        assert all_args.get("request_id") == request_id
        assert all_args.get("community_server_id") == community_server_id

    @pytest.mark.asyncio
    async def test_emit_does_not_call_proposed_event(self):
        """emit_platform_action_event should not call publish_moderation_action_proposed."""
        from src.bulk_content_scan.action_bridge import emit_platform_action_event

        mock_publisher = AsyncMock()
        mock_publisher.publish_moderation_action_applied = AsyncMock(return_value="event_id_123")
        mock_publisher.publish_moderation_action_proposed = AsyncMock()

        content_item = _make_content_item()
        action = _make_mock_action(
            action_state=ActionState.APPLIED,
            action_tier=ActionTier.TIER_1_IMMEDIATE,
        )

        await emit_platform_action_event(
            publisher=mock_publisher,
            moderation_action=action,
            content_item=content_item,
        )

        mock_publisher.publish_moderation_action_proposed.assert_not_called()


class TestIntegrityErrorHandling:
    """Tests for IntegrityError handling in create_moderation_action_from_policy (AC-4)."""

    @pytest.mark.asyncio
    async def test_integrity_error_returns_existing_action(self):
        """IntegrityError on duplicate insert falls back to fetching existing row."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        existing_action = _make_mock_action(
            request_id=request_id,
            action_state=ActionState.APPLIED,
        )

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
                side_effect=IntegrityError("duplicate key", {}, None),
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                side_effect=[None, existing_action],
            ),
        ):
            result, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert result is existing_action
        assert newly_created is False
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_integrity_error_calls_rollback_before_refetch(self):
        """After IntegrityError, session is rolled back before re-fetching."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        rollback_order = []

        async def track_rollback():
            rollback_order.append("rollback")

        mock_session.rollback = AsyncMock(side_effect=track_rollback)

        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        existing_action = _make_mock_action(request_id=request_id)

        fetch_calls = []

        async def track_fetch(session, rid, tier):
            call_index = len(fetch_calls)
            fetch_calls.append(("fetch", call_index))
            return None if call_index == 0 else existing_action

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
                side_effect=IntegrityError("duplicate key", {}, None),
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                side_effect=track_fetch,
            ),
        ):
            result, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert result is existing_action
        assert newly_created is False
        assert rollback_order == ["rollback"]

    @pytest.mark.asyncio
    async def test_idempotency_second_call_same_request_id_and_tier(self):
        """Calling action_bridge twice with same request_id + action_tier returns the same row."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        created_action = _make_mock_action(
            request_id=request_id,
            action_state=ActionState.APPLIED,
        )

        call_count = 0

        async def stateful_create(db, data, **kwargs):
            nonlocal call_count
            if call_count == 0:
                call_count += 1
                return created_action
            raise IntegrityError("duplicate key", {}, None)

        fetch_results = [None, None, created_action]
        fetch_index = 0

        async def stateful_fetch(session, rid, tier):
            nonlocal fetch_index
            result = fetch_results[min(fetch_index, len(fetch_results) - 1)]
            fetch_index += 1
            return result

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                side_effect=stateful_create,
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                side_effect=stateful_fetch,
            ),
        ):
            first, first_new = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )
            second, second_new = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert first is created_action
        assert second is created_action
        assert first_new is True
        assert second_new is False


class TestNewlyCreatedFlag:
    """Tests for AC#4 and AC#5: newly_created flag semantics."""

    @pytest.mark.asyncio
    async def test_precheck_returns_newly_created_false(self):
        """Pre-check path (existing row found before insert) returns newly_created=False (AC#4)."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        existing_action = _make_mock_action(
            request_id=request_id,
            action_state=ActionState.APPLIED,
        )

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                return_value=existing_action,
            ),
        ):
            action, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert action is existing_action
        assert newly_created is False
        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_integrity_error_returns_newly_created_false(self):
        """IntegrityError recovery path returns newly_created=False (AC#5)."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_tier1_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        existing_action = _make_mock_action(
            request_id=request_id,
            action_state=ActionState.APPLIED,
        )

        with (
            patch(
                "src.bulk_content_scan.action_bridge.create_moderation_action",
                new_callable=AsyncMock,
                side_effect=IntegrityError("duplicate key", {}, None),
            ),
            patch(
                "src.bulk_content_scan.action_bridge._fetch_existing_action",
                new_callable=AsyncMock,
                side_effect=[None, existing_action],
            ),
        ):
            action, newly_created = await create_moderation_action_from_policy(
                session=mock_session,
                policy_decision=decision,
                classification=classification,
                content_item=content_item,
                request_id=request_id,
                community_server_id=community_server_id,
            )

        assert action is existing_action
        assert newly_created is False

    @pytest.mark.asyncio
    async def test_pass_decision_returns_newly_created_false(self):
        """Pass decision (action_tier=None) returns (None, False)."""
        from src.bulk_content_scan.action_bridge import create_moderation_action_from_policy

        mock_session = AsyncMock()
        request_id = uuid4()
        community_server_id = uuid4()
        decision = _make_pass_decision()
        classification = _make_classification()
        content_item = _make_content_item()

        action, newly_created = await create_moderation_action_from_policy(
            session=mock_session,
            policy_decision=decision,
            classification=classification,
            content_item=content_item,
            request_id=request_id,
            community_server_id=community_server_id,
        )

        assert action is None
        assert newly_created is False
