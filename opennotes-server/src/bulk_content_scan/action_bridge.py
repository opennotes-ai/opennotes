"""Bridge PolicyDecision output to ModerationAction creation.

Tier 1 -> APPLIED + NATS event.
Tier 2 -> PROPOSED (enters existing consensus flow).
Pass   -> no action.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import pendulum
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bulk_content_scan.policy_evaluator import PolicyDecision
from src.bulk_content_scan.schemas import (
    ContentItem,
    ContentModerationClassificationResult,
    OpenAIModerationMatch,
    SimilarityMatch,
)
from src.moderation_actions.crud import create_moderation_action
from src.moderation_actions.models import ActionState, ActionTier, ModerationAction
from src.moderation_actions.schemas import ModerationActionCreate

if TYPE_CHECKING:
    from src.events.publisher import EventPublisher

logger = logging.getLogger(__name__)


async def _fetch_existing_action(
    session: AsyncSession,
    request_id: UUID,
    action_tier: ActionTier,
) -> ModerationAction | None:
    """SELECT existing ModerationAction for idempotency on DBOS retries.

    Uses FOR UPDATE SKIP LOCKED to prevent duplicate creation under
    concurrent DBOS retries or parallel workers.
    """
    result = await session.execute(
        select(ModerationAction)
        .where(
            ModerationAction.request_id == request_id,
            ModerationAction.action_tier == action_tier.value,
        )
        .with_for_update(skip_locked=True)
    )
    return result.scalar_one_or_none()


async def create_moderation_action_from_policy(
    session: AsyncSession,
    policy_decision: PolicyDecision,
    classification: ContentModerationClassificationResult,
    content_item: ContentItem,
    request_id: UUID,
    community_server_id: UUID,
    pre_computed_evidence: list[SimilarityMatch | OpenAIModerationMatch] | None = None,
) -> ModerationAction | None:
    """Create ModerationAction from policy decision. Returns None for pass."""
    if policy_decision.action_tier is None:
        return None

    existing = await _fetch_existing_action(session, request_id, policy_decision.action_tier)
    if existing is not None:
        logger.info(
            "Idempotency guard: ModerationAction already exists for request_id=%s tier=%s",
            request_id,
            policy_decision.action_tier,
        )
        return existing

    classifier_evidence = {
        "labels": classification.category_labels,
        "scores": classification.category_scores or {},
        "metadata": {
            "explanation": classification.explanation,
            "confidence": classification.confidence,
            "pre_computed_evidence": [e.model_dump() for e in (pre_computed_evidence or [])],
        },
    }

    is_tier1 = policy_decision.action_tier == ActionTier.TIER_1_IMMEDIATE
    action_state = ActionState.APPLIED if is_tier1 else ActionState.PROPOSED
    applied_at = pendulum.now("UTC") if is_tier1 else None

    assert policy_decision.action_type is not None
    assert policy_decision.review_group is not None

    create_data = ModerationActionCreate(
        request_id=request_id,
        community_server_id=community_server_id,
        action_type=policy_decision.action_type,
        action_tier=policy_decision.action_tier,
        action_state=action_state,
        review_group=policy_decision.review_group,
        classifier_evidence=classifier_evidence,
    )

    action = await create_moderation_action(session, create_data, applied_at=applied_at)
    logger.info(
        "Created ModerationAction id=%s state=%s tier=%s for request_id=%s",
        action.id,
        action.action_state,
        action.action_tier,
        request_id,
    )
    return action


async def emit_platform_action_event(
    publisher: EventPublisher,
    moderation_action: ModerationAction,
    content_item: ContentItem,
) -> None:
    """Emit NATS event for Tier 1 APPLIED actions so platform plugins can execute."""
    await publisher.publish_moderation_action_applied(
        action_id=moderation_action.id,
        request_id=moderation_action.request_id,
        action_type=str(moderation_action.action_type),
        community_server_id=moderation_action.community_server_id,
    )
    logger.info(
        "Emitted platform action event for action_id=%s content_id=%s platform=%s",
        moderation_action.id,
        content_item.content_id,
        content_item.platform,
    )
