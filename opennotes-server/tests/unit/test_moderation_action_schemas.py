"""Unit tests for ModerationAction Pydantic schemas."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.moderation_actions.models import (
    ActionState,
    ActionTier,
    ActionType,
    ReviewGroup,
)
from src.moderation_actions.schemas import (
    ModerationActionCreate,
    ModerationActionRead,
    ModerationActionUpdate,
)

pytestmark = pytest.mark.unit

_VALID_CLASSIFIER_EVIDENCE: dict[str, Any] = {
    "labels": ["spam", "hate_speech"],
    "scores": [0.95, 0.87],
}


class TestModerationActionCreate:
    def _valid_payload(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "request_id": str(uuid4()),
            "note_id": None,
            "community_server_id": str(uuid4()),
            "action_type": ActionType.HIDE,
            "action_tier": ActionTier.TIER_1_IMMEDIATE,
            "review_group": ReviewGroup.COMMUNITY,
            "classifier_evidence": _VALID_CLASSIFIER_EVIDENCE,
        }
        base.update(overrides)
        return base

    def test_valid_create_with_all_required_fields(self):
        schema = ModerationActionCreate(**self._valid_payload())
        assert schema.action_type == ActionType.HIDE
        assert schema.action_tier == ActionTier.TIER_1_IMMEDIATE
        assert schema.action_state == ActionState.PROPOSED

    def test_default_action_state_is_proposed(self):
        schema = ModerationActionCreate(**self._valid_payload())
        assert schema.action_state == ActionState.PROPOSED

    def test_note_id_can_be_none(self):
        schema = ModerationActionCreate(**self._valid_payload(note_id=None))
        assert schema.note_id is None

    def test_note_id_accepts_uuid(self):
        note_id = uuid4()
        schema = ModerationActionCreate(**self._valid_payload(note_id=str(note_id)))
        assert schema.note_id == note_id

    def test_all_action_types_accepted(self):
        for action_type in ActionType:
            schema = ModerationActionCreate(**self._valid_payload(action_type=action_type))
            assert schema.action_type == action_type

    def test_all_action_tiers_accepted(self):
        for tier in ActionTier:
            schema = ModerationActionCreate(**self._valid_payload(action_tier=tier))
            assert schema.action_tier == tier

    def test_all_review_groups_accepted(self):
        for group in ReviewGroup:
            schema = ModerationActionCreate(**self._valid_payload(review_group=group))
            assert schema.review_group == group

    def test_classifier_evidence_missing_labels_raises(self):
        bad_evidence = {"scores": [0.9]}
        with pytest.raises(ValueError, match="labels"):
            ModerationActionCreate(**self._valid_payload(classifier_evidence=bad_evidence))

    def test_classifier_evidence_missing_scores_raises(self):
        bad_evidence = {"labels": ["spam"]}
        with pytest.raises(ValueError, match="scores"):
            ModerationActionCreate(**self._valid_payload(classifier_evidence=bad_evidence))

    def test_classifier_evidence_empty_dict_raises(self):
        with pytest.raises(ValueError, match="labels"):
            ModerationActionCreate(**self._valid_payload(classifier_evidence={}))

    def test_extra_fields_are_forbidden(self):
        with pytest.raises(ValidationError):
            ModerationActionCreate(**self._valid_payload(unexpected_field="bad"))

    def test_whitespace_stripped_from_string_fields(self):
        schema = ModerationActionCreate(**self._valid_payload(action_type="  hide  "))
        assert schema.action_type == ActionType.HIDE


class TestModerationActionRead:
    def _make_read_data(self, **overrides: Any) -> dict[str, Any]:
        import pendulum

        base: dict[str, Any] = {
            "id": uuid4(),
            "request_id": uuid4(),
            "note_id": None,
            "community_server_id": uuid4(),
            "action_type": "hide",
            "action_tier": "tier_1_immediate",
            "action_state": "proposed",
            "review_group": "community",
            "classifier_evidence": _VALID_CLASSIFIER_EVIDENCE,
            "platform_action_id": None,
            "scan_exempt_content_hash": None,
            "overturned_reason": None,
            "applied_at": None,
            "confirmed_at": None,
            "overturned_at": None,
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        base.update(overrides)
        return base

    def test_valid_read_schema(self):
        schema = ModerationActionRead(**self._make_read_data())
        assert isinstance(schema.id, UUID)
        assert schema.action_state == "proposed"

    def test_optional_fields_can_be_none(self):
        schema = ModerationActionRead(**self._make_read_data())
        assert schema.note_id is None
        assert schema.platform_action_id is None
        assert schema.applied_at is None
        assert schema.overturned_reason is None

    def test_read_schema_from_orm_attributes(self):
        from types import SimpleNamespace

        import pendulum

        orm_obj = SimpleNamespace(
            id=uuid4(),
            request_id=uuid4(),
            note_id=None,
            community_server_id=uuid4(),
            action_type="hide",
            action_tier="tier_1_immediate",
            action_state="proposed",
            review_group="community",
            classifier_evidence=_VALID_CLASSIFIER_EVIDENCE,
            platform_action_id=None,
            scan_exempt_content_hash=None,
            overturned_reason=None,
            applied_at=None,
            confirmed_at=None,
            overturned_at=None,
            created_at=pendulum.now("UTC"),
            updated_at=pendulum.now("UTC"),
        )
        schema = ModerationActionRead.model_validate(orm_obj)
        assert schema.action_type == "hide"


class TestModerationActionUpdate:
    def test_valid_update_state_only(self):
        schema = ModerationActionUpdate(action_state=ActionState.APPLIED)
        assert schema.action_state == ActionState.APPLIED
        assert schema.platform_action_id is None
        assert schema.overturned_reason is None

    def test_update_with_platform_action_id(self):
        schema = ModerationActionUpdate(
            action_state=ActionState.APPLIED,
            platform_action_id="platform-123",
        )
        assert schema.platform_action_id == "platform-123"

    def test_update_with_overturned_reason(self):
        schema = ModerationActionUpdate(
            action_state=ActionState.OVERTURNED,
            overturned_reason="False positive",
        )
        assert schema.overturned_reason == "False positive"

    def test_update_with_scan_exempt_hash(self):
        schema = ModerationActionUpdate(
            action_state=ActionState.SCAN_EXEMPT,
            scan_exempt_content_hash="abc123hash",
        )
        assert schema.scan_exempt_content_hash == "abc123hash"

    def test_extra_fields_are_forbidden(self):
        with pytest.raises(ValidationError):
            ModerationActionUpdate(
                action_state=ActionState.APPLIED,
                bogus_field="not_allowed",
            )

    def test_all_action_states_accepted(self):
        for state in ActionState:
            schema = ModerationActionUpdate(action_state=state)
            assert schema.action_state == state
