"""Unit tests for ModerationAction SQLAlchemy model and enums."""

from uuid import UUID

from src.moderation_actions.models import (
    ActionState,
    ActionTier,
    ActionType,
    ModerationAction,
    ReviewGroup,
)
from src.notes.models import Note  # noqa: F401
from src.notes.note_publisher_models import NotePublisherConfig, NotePublisherPost  # noqa: F401
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile  # noqa: F401


class TestActionStateEnum:
    def test_all_values_present(self):
        expected = {
            "proposed",
            "applied",
            "retro_review",
            "confirmed",
            "overturned",
            "scan_exempt",
            "under_review",
            "dismissed",
        }
        assert {s.value for s in ActionState} == expected

    def test_member_count(self):
        assert len(ActionState) == 8


class TestActionTypeEnum:
    def test_all_values_present(self):
        expected = {"hide", "unhide", "warn", "silence", "delete"}
        assert {t.value for t in ActionType} == expected

    def test_member_count(self):
        assert len(ActionType) == 5


class TestActionTierEnum:
    def test_all_values_present(self):
        expected = {"tier_1_immediate", "tier_2_consensus"}
        assert {t.value for t in ActionTier} == expected

    def test_member_count(self):
        assert len(ActionTier) == 2


class TestReviewGroupEnum:
    def test_all_values_present(self):
        expected = {"community", "trusted", "staff"}
        assert {g.value for g in ReviewGroup} == expected

    def test_member_count(self):
        assert len(ReviewGroup) == 3


class TestModerationActionModel:
    def test_tablename(self):
        assert ModerationAction.__tablename__ == "moderation_actions"

    def test_instantiation_with_required_fields(self):
        community_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        request_id = UUID("018f5e6e-aaaa-7890-abcd-ef1234567890")

        action = ModerationAction(
            request_id=request_id,
            community_server_id=community_id,
            action_type=ActionType.HIDE.value,
            action_tier=ActionTier.TIER_1_IMMEDIATE.value,
            action_state=ActionState.PROPOSED.value,
            review_group=ReviewGroup.COMMUNITY.value,
        )

        assert action.request_id == request_id
        assert action.community_server_id == community_id
        assert action.action_type == ActionType.HIDE.value
        assert action.action_tier == ActionTier.TIER_1_IMMEDIATE.value
        assert action.action_state == ActionState.PROPOSED.value
        assert action.review_group == ReviewGroup.COMMUNITY.value

    def test_nullable_fields_default_to_none(self):
        community_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        request_id = UUID("018f5e6e-aaaa-7890-abcd-ef1234567890")

        action = ModerationAction(
            request_id=request_id,
            community_server_id=community_id,
            action_type=ActionType.WARN.value,
            action_tier=ActionTier.TIER_2_CONSENSUS.value,
            action_state=ActionState.PROPOSED.value,
            review_group=ReviewGroup.STAFF.value,
        )

        assert action.note_id is None
        assert action.platform_action_id is None
        assert action.scan_exempt_content_hash is None
        assert action.overturned_reason is None
        assert action.applied_at is None
        assert action.confirmed_at is None
        assert action.overturned_at is None

    def test_classifier_evidence_accepts_dict(self):
        community_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        request_id = UUID("018f5e6e-aaaa-7890-abcd-ef1234567890")
        evidence = {
            "labels": ["spam", "hate"],
            "scores": [0.95, 0.87],
            "threshold": 0.8,
            "model_version": "v2.1",
        }

        action = ModerationAction(
            request_id=request_id,
            community_server_id=community_id,
            action_type=ActionType.DELETE.value,
            action_tier=ActionTier.TIER_1_IMMEDIATE.value,
            action_state=ActionState.APPLIED.value,
            review_group=ReviewGroup.TRUSTED.value,
            classifier_evidence=evidence,
        )

        assert action.classifier_evidence == evidence
        assert action.classifier_evidence["model_version"] == "v2.1"

    def test_note_id_is_nullable(self):
        community_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        request_id = UUID("018f5e6e-aaaa-7890-abcd-ef1234567890")
        note_id = UUID("018f5e6e-bbbb-7890-abcd-ef1234567890")

        action = ModerationAction(
            request_id=request_id,
            community_server_id=community_id,
            action_type=ActionType.HIDE.value,
            action_tier=ActionTier.TIER_2_CONSENSUS.value,
            action_state=ActionState.CONFIRMED.value,
            review_group=ReviewGroup.COMMUNITY.value,
            note_id=note_id,
        )

        assert action.note_id == note_id

    def test_indexes_defined(self):
        table_args = ModerationAction.__table_args__
        index_names = [idx.name for idx in table_args if hasattr(idx, "name") and idx.name]

        assert "ix_moderation_actions_request_id" in index_names
        assert "ix_moderation_actions_note_id" in index_names
        assert "ix_moderation_actions_community_state" in index_names

    def test_community_state_index_has_correct_columns(self):
        table_args = ModerationAction.__table_args__
        target_index = None

        for idx in table_args:
            if hasattr(idx, "name") and idx.name == "ix_moderation_actions_community_state":
                target_index = idx
                break

        assert target_index is not None
        column_names = [col.name for col in target_index.columns]
        assert column_names == ["community_server_id", "action_state"]

    def test_request_id_not_nullable(self):
        col = ModerationAction.__table__.columns["request_id"]
        assert col.nullable is False

    def test_community_server_id_not_nullable(self):
        col = ModerationAction.__table__.columns["community_server_id"]
        assert col.nullable is False

    def test_action_type_not_nullable(self):
        col = ModerationAction.__table__.columns["action_type"]
        assert col.nullable is False

    def test_action_state_not_nullable(self):
        col = ModerationAction.__table__.columns["action_state"]
        assert col.nullable is False

    def test_action_tier_not_nullable(self):
        col = ModerationAction.__table__.columns["action_tier"]
        assert col.nullable is False

    def test_review_group_not_nullable(self):
        col = ModerationAction.__table__.columns["review_group"]
        assert col.nullable is False

    def test_note_id_column_nullable(self):
        col = ModerationAction.__table__.columns["note_id"]
        assert col.nullable is True

    def test_platform_action_id_nullable(self):
        col = ModerationAction.__table__.columns["platform_action_id"]
        assert col.nullable is True

    def test_has_timestamp_columns(self):
        columns = {c.name for c in ModerationAction.__table__.columns}
        assert "created_at" in columns
        assert "updated_at" in columns
