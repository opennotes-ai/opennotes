from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pendulum
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.moderation_actions.models import ActionState, ActionTier, ModerationAction
from src.moderation_actions.schemas import (
    ModerationActionCreate,
    ModerationActionUpdate,
    is_valid_transition,
)


async def create_moderation_action(
    db: AsyncSession,
    data: ModerationActionCreate,
    applied_at: datetime | None = None,
) -> ModerationAction:
    action = ModerationAction(
        request_id=data.request_id,
        note_id=data.note_id,
        community_server_id=data.community_server_id,
        action_type=data.action_type,
        action_tier=data.action_tier,
        action_state=data.action_state,
        review_group=data.review_group,
        classifier_evidence=data.classifier_evidence,
        applied_at=applied_at,
    )
    db.add(action)
    await db.commit()
    await db.refresh(action)
    return action


async def get_moderation_action(
    db: AsyncSession,
    action_id: UUID,
) -> ModerationAction | None:
    result = await db.execute(select(ModerationAction).where(ModerationAction.id == action_id))
    return result.scalar_one_or_none()


async def update_moderation_action_state(
    db: AsyncSession,
    action_id: UUID,
    update: ModerationActionUpdate,
) -> ModerationAction:
    action = await get_moderation_action(db, action_id)
    if action is None:
        raise ValueError(f"ModerationAction {action_id} not found")

    current_state = ActionState(action.action_state)
    target_state = ActionState(update.action_state)

    if not is_valid_transition(current_state, target_state):
        raise ValueError(f"Invalid state transition: {current_state.value} -> {target_state.value}")

    action.action_state = target_state.value

    now = pendulum.now("UTC").naive()

    if target_state == ActionState.APPLIED:
        action.applied_at = now
    elif target_state == ActionState.CONFIRMED:
        action.confirmed_at = now
    elif target_state == ActionState.OVERTURNED:
        action.overturned_at = now

    if update.platform_action_id is not None:
        action.platform_action_id = update.platform_action_id
    if update.scan_exempt_content_hash is not None:
        action.scan_exempt_content_hash = update.scan_exempt_content_hash
    if update.overturned_reason is not None:
        action.overturned_reason = update.overturned_reason

    await db.commit()
    await db.refresh(action)
    return action


async def list_moderation_actions(
    db: AsyncSession,
    community_server_id: UUID | None,
    action_state: ActionState | None,
    action_tier: ActionTier | None,
    limit: int,
    offset: int,
    community_server_id__in: list[UUID] | None = None,
) -> list[ModerationAction]:
    query = select(ModerationAction)

    if community_server_id is not None:
        query = query.where(ModerationAction.community_server_id == community_server_id)
    elif community_server_id__in is not None:
        query = query.where(ModerationAction.community_server_id.in_(community_server_id__in))
    if action_state is not None:
        query = query.where(ModerationAction.action_state == action_state.value)
    if action_tier is not None:
        query = query.where(ModerationAction.action_tier == action_tier.value)

    query = query.order_by(ModerationAction.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all())
