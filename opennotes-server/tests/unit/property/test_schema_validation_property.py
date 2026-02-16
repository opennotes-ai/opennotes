"""
Property-based tests for schema validation boundaries and Unicode handling.

Covers:
- Pydantic schema roundtrip consistency for input schemas
- StrictInputSchema extra field rejection
- Field constraint boundaries (ge/le/min_length/max_length)
- Unicode edge cases (zero-width chars, RTL marks, combining diacritics)
- Whitespace stripping behavior from StrictInputSchema
"""

from uuid import uuid4

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from pydantic import ValidationError

from src.bulk_content_scan.schemas import (
    BulkScanCreateRequest,
    ConversationFlashpointMatch,
    RelevanceCheckResult,
    RiskLevel,
    SimilarityMatch,
)
from src.common.base_schemas import StrictInputSchema
from src.notes.schemas import (
    HelpfulnessLevel,
    NoteClassification,
    NoteCreate,
    NoteUpdate,
    RatingCreate,
    RatingUpdate,
    RequestCreate,
)
from src.users.profile_schemas import (
    UserProfileCreate,
)

ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\ufeff"
RTL_MARKS = "\u202e\u200f"
COMBINING_DIACRITICS = "\u0300\u0301\u0302\u0303\u0327"

unicode_padding_strategy = st.text(
    alphabet=st.characters(categories=("Zs", "Cc", "Cf")),
    min_size=0,
    max_size=5,
)

zero_width_strategy = st.text(
    alphabet=st.sampled_from(list(ZERO_WIDTH_CHARS)),
    min_size=1,
    max_size=5,
)

rtl_strategy = st.text(
    alphabet=st.sampled_from(list(RTL_MARKS)),
    min_size=1,
    max_size=3,
)

combining_strategy = st.text(
    alphabet=st.sampled_from(list(COMBINING_DIACRITICS)),
    min_size=1,
    max_size=5,
)


class TestStrictInputSchemaExtraFieldRejection:
    """StrictInputSchema subclasses must reject unknown fields."""

    @given(
        extra_key=st.text(min_size=1, max_size=30).filter(
            lambda s: s.strip()
            and s
            not in {
                "community_server_id",
                "scan_window_days",
                "channel_ids",
            }
        ),
        extra_value=st.one_of(st.text(max_size=50), st.integers(), st.booleans()),
    )
    def test_bulk_scan_create_rejects_extra_fields(self, extra_key, extra_value):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            BulkScanCreateRequest(
                community_server_id=uuid4(),
                scan_window_days=7,
                **{extra_key: extra_value},
            )

    @given(
        extra_key=st.text(min_size=1, max_size=30).filter(
            lambda s: s.strip()
            and s
            not in {
                "author_id",
                "channel_id",
                "request_id",
                "summary",
                "classification",
                "community_server_id",
            }
        ),
    )
    def test_note_create_rejects_extra_fields(self, extra_key):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            NoteCreate(
                author_id=uuid4(),
                summary="valid summary",
                classification=NoteClassification.NOT_MISLEADING,
                community_server_id=uuid4(),
                **{extra_key: "unexpected"},
            )

    @given(
        extra_key=st.text(min_size=1, max_size=30).filter(
            lambda s: s.strip()
            and s
            not in {
                "note_id",
                "rater_id",
                "helpfulness_level",
            }
        ),
    )
    def test_rating_create_rejects_extra_fields(self, extra_key):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            RatingCreate(
                note_id=uuid4(),
                rater_id=uuid4(),
                helpfulness_level=HelpfulnessLevel.HELPFUL,
                **{extra_key: "unexpected"},
            )

    @given(
        extra_key=st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True).filter(
            lambda s: s
            not in {
                "display_name",
                "avatar_url",
                "bio",
                "role",
                "is_opennotes_admin",
                "is_human",
                "is_active",
                "is_banned",
                "banned_at",
                "banned_reason",
            }
        ),
    )
    def test_user_profile_create_rejects_extra_fields(self, extra_key):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            UserProfileCreate(
                display_name="Test User",
                **{extra_key: "unexpected"},
            )


class TestFieldConstraintBoundaries:
    """Verify ge/le/min_length/max_length at exact boundary values."""

    def test_scan_window_days_lower_bound(self):
        req = BulkScanCreateRequest(
            community_server_id=uuid4(),
            scan_window_days=1,
        )
        assert req.scan_window_days == 1

    def test_scan_window_days_upper_bound(self):
        req = BulkScanCreateRequest(
            community_server_id=uuid4(),
            scan_window_days=30,
        )
        assert req.scan_window_days == 30

    def test_scan_window_days_below_lower_bound(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            BulkScanCreateRequest(
                community_server_id=uuid4(),
                scan_window_days=0,
            )

    def test_scan_window_days_above_upper_bound(self):
        with pytest.raises(ValidationError, match="less_than_equal"):
            BulkScanCreateRequest(
                community_server_id=uuid4(),
                scan_window_days=31,
            )

    @given(days=st.integers(min_value=1, max_value=30))
    def test_scan_window_days_valid_range(self, days):
        req = BulkScanCreateRequest(
            community_server_id=uuid4(),
            scan_window_days=days,
        )
        assert req.scan_window_days == days

    @given(days=st.one_of(st.integers(max_value=0), st.integers(min_value=31)))
    def test_scan_window_days_invalid_range(self, days):
        with pytest.raises(ValidationError):
            BulkScanCreateRequest(
                community_server_id=uuid4(),
                scan_window_days=days,
            )

    def test_derailment_score_lower_bound(self):
        match = ConversationFlashpointMatch(
            derailment_score=0,
            risk_level=RiskLevel.LOW_RISK,
            reasoning="No risk",
            context_messages=5,
        )
        assert match.derailment_score == 0

    def test_derailment_score_upper_bound(self):
        match = ConversationFlashpointMatch(
            derailment_score=100,
            risk_level=RiskLevel.DANGEROUS,
            reasoning="High risk",
            context_messages=5,
        )
        assert match.derailment_score == 100

    def test_derailment_score_below_lower_bound(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            ConversationFlashpointMatch(
                derailment_score=-1,
                risk_level=RiskLevel.LOW_RISK,
                reasoning="No risk",
                context_messages=5,
            )

    def test_derailment_score_above_upper_bound(self):
        with pytest.raises(ValidationError, match="less_than_equal"):
            ConversationFlashpointMatch(
                derailment_score=101,
                risk_level=RiskLevel.DANGEROUS,
                reasoning="High risk",
                context_messages=5,
            )

    @given(score=st.integers(min_value=0, max_value=100))
    def test_derailment_score_valid_range(self, score):
        match = ConversationFlashpointMatch(
            derailment_score=score,
            risk_level=RiskLevel.LOW_RISK,
            reasoning="test",
            context_messages=1,
        )
        assert match.derailment_score == score

    @given(score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_similarity_score_valid_range(self, score):
        match = SimilarityMatch(
            score=score,
            matched_claim="test claim",
            matched_source="https://example.com",
        )
        assert match.score == score

    def test_similarity_score_boundary_zero(self):
        match = SimilarityMatch(
            score=0.0,
            matched_claim="test",
            matched_source="https://example.com",
        )
        assert match.score == 0.0

    def test_similarity_score_boundary_one(self):
        match = SimilarityMatch(
            score=1.0,
            matched_claim="test",
            matched_source="https://example.com",
        )
        assert match.score == 1.0

    def test_similarity_score_below_zero(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            SimilarityMatch(
                score=-0.001,
                matched_claim="test",
                matched_source="https://example.com",
            )

    def test_similarity_score_above_one(self):
        with pytest.raises(ValidationError, match="less_than_equal"):
            SimilarityMatch(
                score=1.001,
                matched_claim="test",
                matched_source="https://example.com",
            )

    @given(confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_relevance_confidence_valid_range(self, confidence):
        result = RelevanceCheckResult(
            is_relevant=True,
            reasoning="test reason",
            confidence=confidence,
        )
        assert result.confidence == confidence

    def test_display_name_min_length(self):
        profile = UserProfileCreate(display_name="A")
        assert profile.display_name == "A"

    def test_display_name_max_length(self):
        name = "x" * 255
        profile = UserProfileCreate(display_name=name)
        assert profile.display_name == name

    def test_display_name_too_short_after_strip(self):
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            UserProfileCreate(display_name="")

    def test_display_name_too_long(self):
        with pytest.raises(ValidationError, match="String should have at most 255 characters"):
            UserProfileCreate(display_name="x" * 256)

    def test_avatar_url_max_length(self):
        url = "https://example.com/" + "a" * 479
        profile = UserProfileCreate(display_name="Test", avatar_url=url)
        assert profile.avatar_url == url

    def test_avatar_url_too_long(self):
        url = "https://example.com/" + "a" * 481
        with pytest.raises(ValidationError, match="String should have at most 500 characters"):
            UserProfileCreate(display_name="Test", avatar_url=url)


class TestRoundtripConsistency:
    """Schema roundtrip: model_validate(model.model_dump()) preserves data."""

    @given(
        summary=st.text(min_size=1, max_size=200),
        classification=st.sampled_from(list(NoteClassification)),
    )
    def test_note_create_roundtrip(self, summary, classification):
        assume(summary.strip())
        original = NoteCreate(
            author_id=uuid4(),
            summary=summary,
            classification=classification,
            community_server_id=uuid4(),
        )
        dumped = original.model_dump()
        restored = NoteCreate.model_validate(dumped)
        assert restored.summary == original.summary
        assert restored.classification == original.classification
        assert restored.author_id == original.author_id
        assert restored.community_server_id == original.community_server_id

    @given(
        classification=st.sampled_from(list(NoteClassification)),
    )
    def test_note_update_roundtrip(self, classification):
        original = NoteUpdate(summary="test", classification=classification)
        restored = NoteUpdate.model_validate(original.model_dump())
        assert restored.summary == original.summary
        assert restored.classification == original.classification

    @given(
        level=st.sampled_from(list(HelpfulnessLevel)),
    )
    def test_rating_create_roundtrip(self, level):
        original = RatingCreate(
            note_id=uuid4(),
            rater_id=uuid4(),
            helpfulness_level=level,
        )
        restored = RatingCreate.model_validate(original.model_dump())
        assert restored.note_id == original.note_id
        assert restored.rater_id == original.rater_id
        assert restored.helpfulness_level == original.helpfulness_level

    @given(
        level=st.sampled_from(list(HelpfulnessLevel)),
    )
    def test_rating_update_roundtrip(self, level):
        original = RatingUpdate(helpfulness_level=level)
        restored = RatingUpdate.model_validate(original.model_dump())
        assert restored.helpfulness_level == original.helpfulness_level

    @given(
        days=st.integers(min_value=1, max_value=30),
    )
    def test_bulk_scan_create_roundtrip(self, days):
        original = BulkScanCreateRequest(
            community_server_id=uuid4(),
            scan_window_days=days,
            channel_ids=["123", "456"],
        )
        restored = BulkScanCreateRequest.model_validate(original.model_dump())
        assert restored.community_server_id == original.community_server_id
        assert restored.scan_window_days == original.scan_window_days
        assert restored.channel_ids == original.channel_ids

    @given(
        score=st.integers(min_value=0, max_value=100),
        risk=st.sampled_from(list(RiskLevel)),
    )
    def test_flashpoint_match_roundtrip(self, score, risk):
        original = ConversationFlashpointMatch(
            derailment_score=score,
            risk_level=risk,
            reasoning="test reasoning",
            context_messages=3,
        )
        restored = ConversationFlashpointMatch.model_validate(original.model_dump())
        assert restored.derailment_score == original.derailment_score
        assert restored.risk_level == original.risk_level
        assert restored.reasoning == original.reasoning
        assert restored.context_messages == original.context_messages

    @given(
        name=st.text(min_size=1, max_size=100),
    )
    def test_user_profile_create_roundtrip(self, name):
        assume(name.strip())
        assume(len(name.strip()) <= 255)
        original = UserProfileCreate(display_name=name)
        restored = UserProfileCreate.model_validate(original.model_dump())
        assert restored.display_name == original.display_name
        assert restored.role == original.role
        assert restored.is_active == original.is_active


class TestUnicodeEdgeCases:
    """Unicode edge cases: zero-width chars, RTL marks, combining diacritics."""

    @given(padding=unicode_padding_strategy)
    def test_whitespace_control_chars_stripped_from_strings(self, padding):
        core = "valid content"
        raw = padding + core + padding
        note = NoteCreate(
            author_id=uuid4(),
            summary=raw,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        assert note.summary == raw.strip()

    @given(zw=zero_width_strategy)
    def test_zero_width_chars_in_content(self, zw):
        content = "Hello" + zw + "World"
        note = NoteCreate(
            author_id=uuid4(),
            summary=content,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        stripped = content.strip()
        assert note.summary == stripped
        assert len(note.summary) >= len("HelloWorld")

    @given(zw=zero_width_strategy)
    def test_only_zero_width_chars_stripped_to_empty(self, zw):
        stripped = zw.strip()
        if not stripped:
            note = NoteCreate(
                author_id=uuid4(),
                summary=zw,
                classification=NoteClassification.NOT_MISLEADING,
                community_server_id=uuid4(),
            )
            assert note.summary == ""
        else:
            note = NoteCreate(
                author_id=uuid4(),
                summary=zw,
                classification=NoteClassification.NOT_MISLEADING,
                community_server_id=uuid4(),
            )
            assert note.summary == stripped

    @given(rtl=rtl_strategy)
    def test_rtl_marks_in_content(self, rtl):
        content = "Hello" + rtl + "World"
        note = NoteCreate(
            author_id=uuid4(),
            summary=content,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        assert note.summary == content.strip()

    @given(rtl=rtl_strategy)
    def test_rtl_marks_as_padding_stripped(self, rtl):
        raw = rtl + "content" + rtl
        note = NoteCreate(
            author_id=uuid4(),
            summary=raw,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        assert note.summary == raw.strip()

    @given(combining=combining_strategy)
    def test_combining_diacritics_preserved_in_content(self, combining):
        base_char = "e"
        content = base_char + combining + " text"
        note = NoteCreate(
            author_id=uuid4(),
            summary=content,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        assert combining in note.summary
        assert note.summary == content.strip()

    @given(combining=combining_strategy)
    def test_combining_diacritics_at_boundaries(self, combining):
        content = combining + "text" + combining
        note = NoteCreate(
            author_id=uuid4(),
            summary=content,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        assert note.summary == content.strip()

    def test_bom_stripped_from_field(self):
        bom = "\ufeff"
        raw = bom + "content" + bom
        note = NoteCreate(
            author_id=uuid4(),
            summary=raw,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        assert note.summary == raw.strip()

    def test_mixed_unicode_categories(self):
        content = "\u200b\u0301Hello\u200fWorld\u0300\ufeff"
        note = NoteCreate(
            author_id=uuid4(),
            summary=content,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        assert note.summary == content.strip()

    @given(
        padding=unicode_padding_strategy,
        name=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    )
    def test_user_profile_display_name_unicode_stripping(self, padding, name):
        raw = padding + name + padding
        stripped = raw.strip()
        assume(1 <= len(stripped) <= 255)
        profile = UserProfileCreate(display_name=raw)
        assert profile.display_name == stripped

    @given(
        padding=unicode_padding_strategy,
        reason=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    )
    def test_flashpoint_reasoning_unicode_stripping(self, padding, reason):
        raw = padding + reason + padding
        match = ConversationFlashpointMatch(
            derailment_score=50,
            risk_level=RiskLevel.HEATED,
            reasoning=raw,
            context_messages=3,
        )
        assert match.reasoning == raw.strip()

    @given(
        text=st.text(
            alphabet=st.characters(categories=("Zs", "Cc", "Cf")),
            min_size=1,
            max_size=20,
        ),
    )
    def test_whitespace_only_strings_stripped_completely(self, text):
        stripped = text.strip()
        note = NoteCreate(
            author_id=uuid4(),
            summary=text,
            classification=NoteClassification.NOT_MISLEADING,
            community_server_id=uuid4(),
        )
        assert note.summary == stripped


class TestStrictInputSchemaStripBehavior:
    """Verify strip_all_string_fields handles nested structures."""

    def test_strips_strings_in_nested_dicts(self):
        class NestedSchema(StrictInputSchema):
            data: dict[str, str]

        result = NestedSchema(data={"key": "  value  "})
        assert result.data["key"] == "value"

    def test_strips_strings_in_nested_lists(self):
        class ListSchema(StrictInputSchema):
            items: list[str]

        result = ListSchema(items=["  hello  ", "  world  "])
        assert result.items == ["hello", "world"]

    def test_strips_control_chars_from_nested(self):
        class NestedSchema(StrictInputSchema):
            data: dict[str, str]

        result = NestedSchema(data={"key": "\x1dvalue\x1f"})
        assert result.data["key"] == "value"

    @given(
        padding=st.text(
            alphabet=st.characters(categories=("Zs", "Cc")),
            min_size=1,
            max_size=5,
        ),
        core=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
    )
    def test_strip_matches_python_builtin(self, padding, core):
        raw = padding + core + padding
        req = BulkScanCreateRequest(
            community_server_id=uuid4(),
            scan_window_days=7,
            channel_ids=[raw],
        )
        assert req.channel_ids[0] == raw.strip()

    def test_non_string_values_pass_through(self):
        req = BulkScanCreateRequest(
            community_server_id=uuid4(),
            scan_window_days=15,
            channel_ids=[],
        )
        assert req.scan_window_days == 15

    @given(
        request_id=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        requested_by=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    )
    def test_request_create_strips_all_string_fields(self, request_id, requested_by):
        padded_id = "  " + request_id + "\t"
        padded_by = "\n" + requested_by + "  "
        req = RequestCreate(
            request_id=padded_id,
            requested_by=padded_by,
            community_server_id=str(uuid4()),
        )
        assert req.request_id == padded_id.strip()
        assert req.requested_by == padded_by.strip()


class TestRequestCreateRoundtrip:
    """RequestCreate-specific roundtrip and validation tests."""

    @given(
        request_id=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        requested_by=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    )
    def test_request_create_roundtrip(self, request_id, requested_by):
        original = RequestCreate(
            request_id=request_id,
            requested_by=requested_by,
            community_server_id=str(uuid4()),
        )
        restored = RequestCreate.model_validate(original.model_dump())
        assert restored.request_id == original.request_id
        assert restored.requested_by == original.requested_by
        assert restored.community_server_id == original.community_server_id

    @given(
        extra_key=st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True).filter(
            lambda s: s
            not in {
                "request_id",
                "requested_by",
                "community_server_id",
                "original_message_content",
                "platform_message_id",
                "platform_channel_id",
                "platform_author_id",
                "platform_timestamp",
                "metadata",
                "attachment_url",
                "attachment_type",
                "attachment_metadata",
                "embedded_image_url",
            }
        ),
    )
    def test_request_create_rejects_extra_fields(self, extra_key):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            RequestCreate(
                request_id="req-1",
                requested_by="user-1",
                community_server_id=str(uuid4()),
                **{extra_key: "unexpected"},
            )
