"""Integration tests for conversation flashpoint detection feature."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.bulk_content_scan.scan_types import ALL_SCAN_TYPES, DEFAULT_SCAN_TYPES, ScanType
from src.bulk_content_scan.schemas import (
    ConversationFlashpointMatch,
    FlaggedMessage,
    MatchResult,
)


class TestScanTypeEnum:
    """Integration tests for ScanType enum including CONVERSATION_FLASHPOINT."""

    def test_flashpoint_scan_type_in_enum(self):
        """ScanType enum should include CONVERSATION_FLASHPOINT."""
        assert hasattr(ScanType, "CONVERSATION_FLASHPOINT")
        assert ScanType.CONVERSATION_FLASHPOINT == "conversation_flashpoint"

    def test_flashpoint_in_all_scan_types(self):
        """CONVERSATION_FLASHPOINT should be in ALL_SCAN_TYPES."""
        assert ScanType.CONVERSATION_FLASHPOINT in ALL_SCAN_TYPES

    def test_flashpoint_not_in_default_scan_types(self):
        """CONVERSATION_FLASHPOINT should NOT be in DEFAULT_SCAN_TYPES (phased rollout, opt-in)."""
        assert ScanType.CONVERSATION_FLASHPOINT not in DEFAULT_SCAN_TYPES

    def test_all_enum_values_accounted_for(self):
        """ALL_SCAN_TYPES should contain all ScanType enum values."""
        for scan_type in ScanType:
            assert scan_type in ALL_SCAN_TYPES

    def test_scan_type_is_str_enum(self):
        """ScanType values should be string-serializable."""
        assert str(ScanType.CONVERSATION_FLASHPOINT) == "conversation_flashpoint"
        assert isinstance(ScanType.CONVERSATION_FLASHPOINT, str)


class TestConversationFlashpointMatchSchema:
    """Integration tests for ConversationFlashpointMatch schema validation."""

    def test_valid_schema_creation(self):
        """ConversationFlashpointMatch should accept valid data."""
        match = ConversationFlashpointMatch(
            derailment_score=75,
            reasoning="Escalating tension detected in the exchange",
            context_messages=5,
        )

        assert match.scan_type == "conversation_flashpoint"
        assert match.derailment_score == 75
        assert match.reasoning == "Escalating tension detected in the exchange"
        assert match.context_messages == 5

    def test_scan_type_literal_enforced(self):
        """scan_type should be locked to 'conversation_flashpoint'."""
        match = ConversationFlashpointMatch(
            derailment_score=30,
            reasoning="Normal conversation",
            context_messages=3,
        )

        assert match.scan_type == "conversation_flashpoint"

    def test_derailment_score_range_validation_min(self):
        """derailment_score must be at least 0."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationFlashpointMatch(
                derailment_score=-1,
                reasoning="Test",
                context_messages=0,
            )

        assert "derailment_score" in str(exc_info.value)

    def test_derailment_score_range_validation_max(self):
        """derailment_score must be at most 100."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationFlashpointMatch(
                derailment_score=101,
                reasoning="Test",
                context_messages=0,
            )

        assert "derailment_score" in str(exc_info.value)

    def test_derailment_score_boundary_values(self):
        """Boundary values 0 and 100 should be accepted."""
        match_min = ConversationFlashpointMatch(
            derailment_score=0,
            reasoning="No risk",
            context_messages=0,
        )
        assert match_min.derailment_score == 0

        match_max = ConversationFlashpointMatch(
            derailment_score=100,
            reasoning="Certain derailment",
            context_messages=0,
        )
        assert match_max.derailment_score == 100

    def test_all_fields_required(self):
        """All fields are required (no optional fields)."""
        with pytest.raises(ValidationError):
            ConversationFlashpointMatch()

        with pytest.raises(ValidationError):
            ConversationFlashpointMatch(derailment_score=50)

        with pytest.raises(ValidationError):
            ConversationFlashpointMatch(derailment_score=50, reasoning="Test")

    def test_serialization_to_dict(self):
        """Match should serialize to dictionary with scan_type."""
        match = ConversationFlashpointMatch(
            derailment_score=85,
            reasoning="Hostile language detected",
            context_messages=3,
        )

        data = match.model_dump()

        assert data["scan_type"] == "conversation_flashpoint"
        assert data["derailment_score"] == 85
        assert data["reasoning"] == "Hostile language detected"
        assert data["context_messages"] == 3

    def test_json_serialization(self):
        """Match should serialize to JSON correctly."""
        match = ConversationFlashpointMatch(
            derailment_score=75,
            reasoning="Test reasoning",
            context_messages=2,
        )

        json_str = match.model_dump_json()

        assert '"scan_type":"conversation_flashpoint"' in json_str
        assert '"derailment_score":75' in json_str


class TestMatchResultUnion:
    """Integration tests for MatchResult discriminated union with flashpoint matches."""

    def test_flashpoint_match_in_union(self):
        """ConversationFlashpointMatch should work in MatchResult union."""
        from pydantic import TypeAdapter

        adapter = TypeAdapter(MatchResult)

        data = {
            "scan_type": "conversation_flashpoint",
            "derailment_score": 80,
            "reasoning": "Test",
            "context_messages": 3,
        }

        parsed = adapter.validate_python(data)
        assert isinstance(parsed, ConversationFlashpointMatch)
        assert parsed.derailment_score == 80

    def test_discriminator_selects_correct_type(self):
        """Discriminator should select correct type based on scan_type."""
        from pydantic import TypeAdapter

        from src.bulk_content_scan.schemas import (
            OpenAIModerationMatch,
            SimilarityMatch,
        )

        adapter = TypeAdapter(MatchResult)

        similarity_data = {
            "scan_type": "similarity",
            "score": 0.9,
            "matched_claim": "Test claim",
            "matched_source": "https://example.com",
            "fact_check_item_id": "12345678-1234-1234-1234-123456789abc",
        }

        moderation_data = {
            "scan_type": "openai_moderation",
            "max_score": 0.95,
            "categories": {"violence": True},
            "scores": {"violence": 0.95},
            "flagged_categories": ["violence"],
        }

        flashpoint_data = {
            "scan_type": "conversation_flashpoint",
            "derailment_score": 85,
            "reasoning": "Escalating",
            "context_messages": 5,
        }

        assert isinstance(adapter.validate_python(similarity_data), SimilarityMatch)
        assert isinstance(adapter.validate_python(moderation_data), OpenAIModerationMatch)
        assert isinstance(adapter.validate_python(flashpoint_data), ConversationFlashpointMatch)


class TestFlaggedMessageWithFlashpoint:
    """Integration tests for FlaggedMessage containing flashpoint matches."""

    def test_flagged_message_can_contain_flashpoint(self):
        """FlaggedMessage should accept ConversationFlashpointMatch in matches list."""
        flashpoint_match = ConversationFlashpointMatch(
            derailment_score=80,
            reasoning="Hostile tone detected",
            context_messages=4,
        )

        flagged = FlaggedMessage(
            message_id="msg_12345",
            channel_id="ch_67890",
            content="You're completely wrong about this!",
            author_id="user_54321",
            timestamp=datetime.now(UTC),
            matches=[flashpoint_match],
        )

        assert len(flagged.matches) == 1
        assert flagged.matches[0].scan_type == "conversation_flashpoint"
        assert isinstance(flagged.matches[0], ConversationFlashpointMatch)

    def test_flagged_message_with_mixed_match_types(self):
        """FlaggedMessage should support multiple match types including flashpoint."""
        from src.bulk_content_scan.schemas import SimilarityMatch

        similarity_match = SimilarityMatch(
            score=0.85,
            matched_claim="Misinformation claim",
            matched_source="https://factcheck.org/article",
            fact_check_item_id="12345678-1234-1234-1234-123456789abc",
        )

        flashpoint_match = ConversationFlashpointMatch(
            derailment_score=75,
            reasoning="Aggressive response pattern",
            context_messages=3,
        )

        flagged = FlaggedMessage(
            message_id="msg_mixed",
            channel_id="ch_1",
            content="Some controversial content",
            author_id="user_1",
            timestamp=datetime.now(UTC),
            matches=[similarity_match, flashpoint_match],
        )

        assert len(flagged.matches) == 2
        assert flagged.matches[0].scan_type == "similarity"
        assert flagged.matches[1].scan_type == "conversation_flashpoint"
