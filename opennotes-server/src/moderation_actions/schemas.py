from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import field_validator

from src.common.base_schemas import StrictInputSchema, TimestampSchema
from src.moderation_actions.models import ActionState, ActionTier, ActionType, ReviewGroup

VALID_TRANSITIONS: dict[ActionState, set[ActionState]] = {
    ActionState.PROPOSED: {ActionState.APPLIED, ActionState.UNDER_REVIEW, ActionState.DISMISSED},
    ActionState.APPLIED: {ActionState.RETRO_REVIEW, ActionState.OVERTURNED},
    ActionState.RETRO_REVIEW: {ActionState.CONFIRMED, ActionState.OVERTURNED},
    ActionState.CONFIRMED: set(),
    ActionState.OVERTURNED: {ActionState.SCAN_EXEMPT},
    ActionState.SCAN_EXEMPT: {ActionState.PROPOSED},
    ActionState.UNDER_REVIEW: {ActionState.APPLIED, ActionState.DISMISSED},
    ActionState.DISMISSED: set(),
}


def is_valid_transition(from_state: ActionState, to_state: ActionState) -> bool:
    return to_state in VALID_TRANSITIONS.get(from_state, set())


class ModerationActionCreate(StrictInputSchema):
    request_id: UUID
    note_id: UUID | None = None
    community_server_id: UUID
    action_type: ActionType
    action_tier: ActionTier
    action_state: ActionState = ActionState.PROPOSED
    classifier_evidence: dict[str, Any]
    review_group: ReviewGroup
    applied_at: datetime | None = None

    @field_validator("classifier_evidence")
    @classmethod
    def validate_classifier_evidence(cls, v: dict[str, Any]) -> dict[str, Any]:
        missing = [key for key in ("labels", "scores") if key not in v]
        if missing:
            raise ValueError(f"classifier_evidence missing required keys: {missing}")
        return v


class ModerationActionRead(TimestampSchema):
    id: UUID
    request_id: UUID
    note_id: UUID | None
    community_server_id: UUID
    action_type: str
    action_tier: str
    action_state: str
    review_group: str
    classifier_evidence: dict[str, Any]
    platform_action_id: str | None
    scan_exempt_content_hash: str | None
    overturned_reason: str | None
    applied_at: datetime | None
    confirmed_at: datetime | None
    overturned_at: datetime | None


class ModerationActionUpdate(StrictInputSchema):
    action_state: ActionState
    platform_action_id: str | None = None
    scan_exempt_content_hash: str | None = None
    overturned_reason: str | None = None
