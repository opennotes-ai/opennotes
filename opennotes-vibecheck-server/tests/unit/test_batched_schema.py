import pytest
from pydantic import ValidationError

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.config import Settings
from src.utterances.schema import BatchedUtteranceRedirectionResponse, SectionHint


def test_batched_redirection_response_round_trips():
    payload = BatchedUtteranceRedirectionResponse(
        page_kind=PageKind.FORUM_THREAD,
        utterance_stream_type=UtteranceStreamType.DIALOGUE,
        page_title="Test Forum Thread",
        boundary_instructions="Split at <hr> tags between posts.",
        section_hints=[
            SectionHint(
                anchor_hint="<!-- post-42 -->",
                tolerance_bytes=500,
                parent_context_text="Previous post text...",
                overlap_with_prev_bytes=200,
            )
        ],
    )
    dumped = payload.model_dump()
    restored = BatchedUtteranceRedirectionResponse.model_validate(dumped)
    assert restored.page_kind == PageKind.FORUM_THREAD
    assert restored.utterance_stream_type == UtteranceStreamType.DIALOGUE
    assert restored.page_title == "Test Forum Thread"
    assert len(restored.section_hints) == 1
    assert restored.section_hints[0].anchor_hint == "<!-- post-42 -->"


def test_batched_redirection_response_no_byte_offset_fields():
    fields = BatchedUtteranceRedirectionResponse.model_fields
    assert "html_start" not in fields
    assert "html_end" not in fields
    assert "global_start" not in fields
    assert "global_end" not in fields


def test_section_hint_all_optional_except_anchor():
    hint = SectionHint(anchor_hint="<h2>Section Title</h2>")
    assert hint.anchor_hint == "<h2>Section Title</h2>"
    assert hint.tolerance_bytes is None
    assert hint.parent_context_text is None
    assert hint.overlap_with_prev_bytes is None


def test_settings_rejects_overlap_gte_section_target():
    with pytest.raises(ValidationError, match="VIBECHECK_BATCH_OVERLAP_BYTES"):
        Settings(
            VIBECHECK_BATCH_SECTION_TARGET_BYTES=10_000,
            VIBECHECK_BATCH_OVERLAP_BYTES=10_000,
        )


def test_settings_rejects_negative_batch_bytes():
    with pytest.raises(ValidationError, match="must be >= 0"):
        Settings(VIBECHECK_BATCH_HTML_BYTES=-1)


def test_settings_defaults_high_enough_for_normal_pages():
    s = Settings()
    assert s.VIBECHECK_BATCH_HTML_BYTES >= 200_000
    assert s.VIBECHECK_BATCH_MARKDOWN_BYTES >= 100_000


def test_settings_rejects_zero_parallel():
    with pytest.raises(ValidationError, match="VIBECHECK_BATCH_PARALLEL must be > 0"):
        Settings(VIBECHECK_BATCH_PARALLEL=0)
