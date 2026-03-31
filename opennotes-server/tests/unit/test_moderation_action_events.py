import json
from uuid import uuid4

import pytest

from src.events.schemas import (
    EventType,
    EventUnion,
    ModerationActionAppliedEvent,
    ModerationActionConfirmedEvent,
    ModerationActionDismissedEvent,
    ModerationActionOverturnedEvent,
    ModerationActionProposedEvent,
    ModerationActionRetroReviewStartedEvent,
)

ACTION_ID = uuid4()
REQUEST_ID = uuid4()
COMMUNITY_SERVER_ID = uuid4()


def make_proposed() -> dict:
    return {
        "event_id": "test-event-id",
        "action_id": ACTION_ID,
        "request_id": REQUEST_ID,
        "action_type": "ban",
        "action_tier": "tier_1",
        "classifier_evidence": {"score": 0.95, "labels": ["spam"]},
        "review_group": "mod_team",
        "community_server_id": COMMUNITY_SERVER_ID,
    }


def make_applied() -> dict:
    return {
        "event_id": "test-event-id",
        "action_id": ACTION_ID,
        "request_id": REQUEST_ID,
        "action_type": "ban",
        "platform_action_id": "plat-123",
        "community_server_id": COMMUNITY_SERVER_ID,
    }


def make_retro_review_started() -> dict:
    return {
        "event_id": "test-event-id",
        "action_id": ACTION_ID,
        "request_id": REQUEST_ID,
        "action_type": "ban",
        "community_server_id": COMMUNITY_SERVER_ID,
    }


def make_confirmed() -> dict:
    return {
        "event_id": "test-event-id",
        "action_id": ACTION_ID,
        "request_id": REQUEST_ID,
        "action_type": "ban",
        "community_server_id": COMMUNITY_SERVER_ID,
    }


def make_overturned() -> dict:
    return {
        "event_id": "test-event-id",
        "action_id": ACTION_ID,
        "request_id": REQUEST_ID,
        "action_type": "ban",
        "overturned_reason": "Insufficient evidence",
        "community_server_id": COMMUNITY_SERVER_ID,
    }


def make_dismissed() -> dict:
    return {
        "event_id": "test-event-id",
        "action_id": ACTION_ID,
        "request_id": REQUEST_ID,
        "action_type": "ban",
        "community_server_id": COMMUNITY_SERVER_ID,
    }


class TestEventTypeEnum:
    def test_proposed_enum_entry(self):
        assert EventType.MODERATION_ACTION_PROPOSED == "moderation_action.proposed"

    def test_applied_enum_entry(self):
        assert EventType.MODERATION_ACTION_APPLIED == "moderation_action.applied"

    def test_retro_review_started_enum_entry(self):
        assert (
            EventType.MODERATION_ACTION_RETRO_REVIEW_STARTED
            == "moderation_action.retro_review_started"
        )

    def test_confirmed_enum_entry(self):
        assert EventType.MODERATION_ACTION_CONFIRMED == "moderation_action.confirmed"

    def test_overturned_enum_entry(self):
        assert EventType.MODERATION_ACTION_OVERTURNED == "moderation_action.overturned"

    def test_dismissed_enum_entry(self):
        assert EventType.MODERATION_ACTION_DISMISSED == "moderation_action.dismissed"


class TestModerationActionProposedEvent:
    def test_serializes_correctly(self):
        event = ModerationActionProposedEvent(**make_proposed())
        data = json.loads(event.model_dump_json())
        assert data["event_type"] == "moderation_action.proposed"
        assert data["action_type"] == "ban"
        assert data["action_tier"] == "tier_1"
        assert data["classifier_evidence"] == {"score": 0.95, "labels": ["spam"]}
        assert data["review_group"] == "mod_team"

    def test_default_event_type(self):
        event = ModerationActionProposedEvent(**make_proposed())
        assert event.event_type == EventType.MODERATION_ACTION_PROPOSED

    def test_required_fields_enforced(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ModerationActionProposedEvent(event_id="x")


class TestModerationActionAppliedEvent:
    def test_serializes_correctly(self):
        event = ModerationActionAppliedEvent(**make_applied())
        data = json.loads(event.model_dump_json())
        assert data["event_type"] == "moderation_action.applied"
        assert data["platform_action_id"] == "plat-123"

    def test_platform_action_id_optional(self):
        payload = make_applied()
        del payload["platform_action_id"]
        event = ModerationActionAppliedEvent(**payload)
        assert event.platform_action_id is None

    def test_default_event_type(self):
        event = ModerationActionAppliedEvent(**make_applied())
        assert event.event_type == EventType.MODERATION_ACTION_APPLIED


class TestModerationActionRetroReviewStartedEvent:
    def test_serializes_correctly(self):
        event = ModerationActionRetroReviewStartedEvent(**make_retro_review_started())
        data = json.loads(event.model_dump_json())
        assert data["event_type"] == "moderation_action.retro_review_started"
        assert data["action_type"] == "ban"

    def test_default_event_type(self):
        event = ModerationActionRetroReviewStartedEvent(**make_retro_review_started())
        assert event.event_type == EventType.MODERATION_ACTION_RETRO_REVIEW_STARTED


class TestModerationActionConfirmedEvent:
    def test_serializes_correctly(self):
        event = ModerationActionConfirmedEvent(**make_confirmed())
        data = json.loads(event.model_dump_json())
        assert data["event_type"] == "moderation_action.confirmed"

    def test_default_event_type(self):
        event = ModerationActionConfirmedEvent(**make_confirmed())
        assert event.event_type == EventType.MODERATION_ACTION_CONFIRMED


class TestModerationActionOverturnedEvent:
    def test_serializes_correctly(self):
        event = ModerationActionOverturnedEvent(**make_overturned())
        data = json.loads(event.model_dump_json())
        assert data["event_type"] == "moderation_action.overturned"
        assert data["overturned_reason"] == "Insufficient evidence"

    def test_overturned_reason_optional(self):
        payload = make_overturned()
        del payload["overturned_reason"]
        event = ModerationActionOverturnedEvent(**payload)
        assert event.overturned_reason is None

    def test_default_event_type(self):
        event = ModerationActionOverturnedEvent(**make_overturned())
        assert event.event_type == EventType.MODERATION_ACTION_OVERTURNED


class TestModerationActionDismissedEvent:
    def test_serializes_correctly(self):
        event = ModerationActionDismissedEvent(**make_dismissed())
        data = json.loads(event.model_dump_json())
        assert data["event_type"] == "moderation_action.dismissed"

    def test_default_event_type(self):
        event = ModerationActionDismissedEvent(**make_dismissed())
        assert event.event_type == EventType.MODERATION_ACTION_DISMISSED


class TestEventUnionDiscrimination:
    def _parse(self, payload: dict) -> object:
        from pydantic import TypeAdapter

        adapter = TypeAdapter(EventUnion)
        return adapter.validate_python(payload)

    def test_proposed_parsed_via_union(self):
        payload = {**make_proposed(), "event_type": EventType.MODERATION_ACTION_PROPOSED}
        event = self._parse(payload)
        assert isinstance(event, ModerationActionProposedEvent)

    def test_applied_parsed_via_union(self):
        payload = {**make_applied(), "event_type": EventType.MODERATION_ACTION_APPLIED}
        event = self._parse(payload)
        assert isinstance(event, ModerationActionAppliedEvent)

    def test_retro_review_started_parsed_via_union(self):
        payload = {
            **make_retro_review_started(),
            "event_type": EventType.MODERATION_ACTION_RETRO_REVIEW_STARTED,
        }
        event = self._parse(payload)
        assert isinstance(event, ModerationActionRetroReviewStartedEvent)

    def test_confirmed_parsed_via_union(self):
        payload = {**make_confirmed(), "event_type": EventType.MODERATION_ACTION_CONFIRMED}
        event = self._parse(payload)
        assert isinstance(event, ModerationActionConfirmedEvent)

    def test_overturned_parsed_via_union(self):
        payload = {**make_overturned(), "event_type": EventType.MODERATION_ACTION_OVERTURNED}
        event = self._parse(payload)
        assert isinstance(event, ModerationActionOverturnedEvent)

    def test_dismissed_parsed_via_union(self):
        payload = {**make_dismissed(), "event_type": EventType.MODERATION_ACTION_DISMISSED}
        event = self._parse(payload)
        assert isinstance(event, ModerationActionDismissedEvent)
