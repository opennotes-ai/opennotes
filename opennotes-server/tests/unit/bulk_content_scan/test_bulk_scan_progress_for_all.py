"""BulkScanProgressEvent schema validation tests.

Validates field constraints, defaults, serialization, and boundary conditions
for BulkScanProgressEvent and MessageScoreInfo schemas.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError


class TestMessageScoreInfoValidation:
    """Field-level validation for MessageScoreInfo."""

    def test_required_fields_present(self):
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="111",
            channel_id="222",
            similarity_score=0.5,
            threshold=0.6,
            is_flagged=False,
        )
        assert info.message_id == "111"
        assert info.channel_id == "222"
        assert info.similarity_score == 0.5
        assert info.threshold == 0.6
        assert info.is_flagged is False

    def test_similarity_score_lower_bound(self):
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="1",
            channel_id="2",
            similarity_score=0.0,
            threshold=0.5,
            is_flagged=False,
        )
        assert info.similarity_score == 0.0

    def test_similarity_score_upper_bound(self):
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="1",
            channel_id="2",
            similarity_score=1.0,
            threshold=0.5,
            is_flagged=True,
        )
        assert info.similarity_score == 1.0

    def test_similarity_score_below_zero_rejected(self):
        from src.events.schemas import MessageScoreInfo

        with pytest.raises(ValidationError):
            MessageScoreInfo(
                message_id="1",
                channel_id="2",
                similarity_score=-0.1,
                threshold=0.5,
                is_flagged=False,
            )

    def test_similarity_score_above_one_rejected(self):
        from src.events.schemas import MessageScoreInfo

        with pytest.raises(ValidationError):
            MessageScoreInfo(
                message_id="1",
                channel_id="2",
                similarity_score=1.01,
                threshold=0.5,
                is_flagged=False,
            )

    def test_threshold_boundary_zero(self):
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="1",
            channel_id="2",
            similarity_score=0.5,
            threshold=0.0,
            is_flagged=True,
        )
        assert info.threshold == 0.0

    def test_threshold_boundary_one(self):
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="1",
            channel_id="2",
            similarity_score=0.5,
            threshold=1.0,
            is_flagged=False,
        )
        assert info.threshold == 1.0

    def test_threshold_out_of_range_rejected(self):
        from src.events.schemas import MessageScoreInfo

        with pytest.raises(ValidationError):
            MessageScoreInfo(
                message_id="1",
                channel_id="2",
                similarity_score=0.5,
                threshold=1.5,
                is_flagged=False,
            )

    def test_optional_moderation_fields_default_none(self):
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="1",
            channel_id="2",
            similarity_score=0.5,
            threshold=0.6,
            is_flagged=False,
        )
        assert info.matched_claim is None
        assert info.moderation_flagged is None
        assert info.moderation_categories is None
        assert info.moderation_scores is None

    def test_moderation_fields_populated(self):
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="1",
            channel_id="2",
            similarity_score=0.9,
            threshold=0.6,
            is_flagged=True,
            matched_claim="Earth is flat",
            moderation_flagged=True,
            moderation_categories={"violence": False, "hate": True},
            moderation_scores={"violence": 0.01, "hate": 0.85},
        )
        assert info.moderation_flagged is True
        assert info.moderation_categories["hate"] is True
        assert info.moderation_scores["hate"] == 0.85

    def test_missing_required_field_rejected(self):
        from src.events.schemas import MessageScoreInfo

        with pytest.raises(ValidationError):
            MessageScoreInfo(
                message_id="1",
                channel_id="2",
                similarity_score=0.5,
            )

    def test_json_roundtrip(self):
        from src.events.schemas import MessageScoreInfo

        info = MessageScoreInfo(
            message_id="msg_abc",
            channel_id="ch_xyz",
            similarity_score=0.72,
            threshold=0.60,
            is_flagged=True,
            matched_claim="test claim",
        )
        json_str = info.model_dump_json()
        restored = MessageScoreInfo.model_validate_json(json_str)
        assert restored == info


class TestBulkScanProgressEventValidation:
    """Field-level validation for BulkScanProgressEvent."""

    def _make_event(self, **overrides):
        from src.events.schemas import BulkScanProgressEvent

        defaults = {
            "event_id": "evt_test",
            "scan_id": uuid4(),
            "community_server_id": uuid4(),
            "platform_community_server_id": "123456789",
            "batch_number": 1,
            "messages_in_batch": 10,
            "threshold_used": 0.60,
        }
        defaults.update(overrides)
        return BulkScanProgressEvent(**defaults)

    def test_event_type_is_bulk_scan_progress(self):
        from src.events.schemas import EventType

        event = self._make_event()
        assert event.event_type == EventType.BULK_SCAN_PROGRESS
        assert event.event_type.value == "bulk_scan.progress"

    def test_required_fields(self):
        event = self._make_event()
        assert event.batch_number == 1
        assert event.messages_in_batch == 10
        assert event.threshold_used == 0.60

    def test_default_values(self):
        event = self._make_event()
        assert event.messages_processed == 0
        assert event.messages_skipped == 0
        assert event.channel_ids == []
        assert event.message_scores == []
        assert event.version == "1.0"

    def test_batch_number_must_be_positive(self):
        with pytest.raises(ValidationError):
            self._make_event(batch_number=0)

    def test_batch_number_negative_rejected(self):
        with pytest.raises(ValidationError):
            self._make_event(batch_number=-1)

    def test_messages_in_batch_zero_allowed(self):
        event = self._make_event(messages_in_batch=0)
        assert event.messages_in_batch == 0

    def test_messages_in_batch_negative_rejected(self):
        with pytest.raises(ValidationError):
            self._make_event(messages_in_batch=-1)

    def test_threshold_used_boundaries(self):
        event_low = self._make_event(threshold_used=0.0)
        assert event_low.threshold_used == 0.0

        event_high = self._make_event(threshold_used=1.0)
        assert event_high.threshold_used == 1.0

    def test_threshold_used_out_of_range(self):
        with pytest.raises(ValidationError):
            self._make_event(threshold_used=1.5)

        with pytest.raises(ValidationError):
            self._make_event(threshold_used=-0.1)

    def test_with_message_scores(self):
        from src.events.schemas import MessageScoreInfo

        scores = [
            MessageScoreInfo(
                message_id="m1",
                channel_id="c1",
                similarity_score=0.8,
                threshold=0.6,
                is_flagged=True,
                matched_claim="claim text",
            ),
            MessageScoreInfo(
                message_id="m2",
                channel_id="c1",
                similarity_score=0.3,
                threshold=0.6,
                is_flagged=False,
            ),
        ]
        event = self._make_event(message_scores=scores)
        assert len(event.message_scores) == 2
        assert event.message_scores[0].is_flagged is True
        assert event.message_scores[1].is_flagged is False

    def test_with_channel_ids(self):
        event = self._make_event(channel_ids=["ch1", "ch2", "ch3"])
        assert event.channel_ids == ["ch1", "ch2", "ch3"]

    def test_messages_processed_and_skipped(self):
        event = self._make_event(
            messages_processed=42,
            messages_skipped=8,
        )
        assert event.messages_processed == 42
        assert event.messages_skipped == 8

    def test_messages_processed_negative_rejected(self):
        with pytest.raises(ValidationError):
            self._make_event(messages_processed=-1)

    def test_messages_skipped_negative_rejected(self):
        with pytest.raises(ValidationError):
            self._make_event(messages_skipped=-1)

    def test_scan_id_is_uuid(self):
        scan_id = uuid4()
        event = self._make_event(scan_id=scan_id)
        assert event.scan_id == scan_id

    def test_community_server_id_is_uuid(self):
        cs_id = uuid4()
        event = self._make_event(community_server_id=cs_id)
        assert event.community_server_id == cs_id

    def test_json_serialization_roundtrip(self):
        from src.events.schemas import BulkScanProgressEvent, MessageScoreInfo

        scan_id = uuid4()
        community_server_id = uuid4()
        event = self._make_event(
            scan_id=scan_id,
            community_server_id=community_server_id,
            batch_number=3,
            messages_in_batch=25,
            messages_processed=100,
            messages_skipped=5,
            channel_ids=["ch_a", "ch_b"],
            message_scores=[
                MessageScoreInfo(
                    message_id="msg1",
                    channel_id="ch_a",
                    similarity_score=0.72,
                    threshold=0.60,
                    is_flagged=True,
                    matched_claim="some claim",
                ),
            ],
            threshold_used=0.60,
        )

        json_str = event.model_dump_json()
        restored = BulkScanProgressEvent.model_validate_json(json_str)
        assert restored.scan_id == scan_id
        assert restored.batch_number == 3
        assert len(restored.message_scores) == 1
        assert restored.message_scores[0].matched_claim == "some claim"

    def test_event_has_timestamp(self):
        from datetime import datetime

        event = self._make_event()
        assert isinstance(event.timestamp, datetime)

    def test_event_has_metadata_dict(self):
        event = self._make_event()
        assert isinstance(event.metadata, dict)

    def test_in_event_union(self):
        from src.events.schemas import BulkScanProgressEvent, EventUnion

        assert BulkScanProgressEvent in EventUnion.__args__

    def test_missing_scan_id_rejected(self):
        from src.events.schemas import BulkScanProgressEvent

        with pytest.raises(ValidationError):
            BulkScanProgressEvent(
                event_id="evt_test",
                community_server_id=uuid4(),
                platform_community_server_id="123",
                batch_number=1,
                messages_in_batch=10,
                threshold_used=0.6,
            )

    def test_missing_threshold_used_rejected(self):
        from src.events.schemas import BulkScanProgressEvent

        with pytest.raises(ValidationError):
            BulkScanProgressEvent(
                event_id="evt_test",
                scan_id=uuid4(),
                community_server_id=uuid4(),
                platform_community_server_id="123",
                batch_number=1,
                messages_in_batch=10,
            )
