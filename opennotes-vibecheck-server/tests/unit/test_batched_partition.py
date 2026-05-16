from unittest.mock import MagicMock

from src.analyses.schemas import PageKind
from src.analyses.stream_types import UtteranceStreamType
from src.utterances.batched.partition import partition_html
from src.utterances.schema import BatchedUtteranceRedirectionResponse, SectionHint


def make_settings(target: int, overlap: int) -> MagicMock:
    s = MagicMock()
    s.VIBECHECK_BATCH_SECTION_TARGET_BYTES = target
    s.VIBECHECK_BATCH_OVERLAP_BYTES = overlap
    return s


def empty_response() -> BatchedUtteranceRedirectionResponse:
    return BatchedUtteranceRedirectionResponse(
        page_kind=PageKind.ARTICLE,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
        boundary_instructions="none",
        section_hints=[],
    )


class TestAC1FullCoverageMonotonic:
    def test_covers_entire_input_monotonically_nondecreasing(self):
        html = "A" * 1000
        settings = make_settings(target=400, overlap=50)
        sections = partition_html(html, empty_response(), settings)

        assert len(sections) > 0, "Should produce at least one section"

        assert sections[0].global_start == 0, "First section should start at 0"

        final_bytes = len(html.encode("utf-8"))
        assert (
            sections[-1].global_end == final_bytes
        ), "Last section should end at total bytes"

        for i in range(len(sections) - 1):
            assert (
                sections[i].global_start <= sections[i + 1].global_start
            ), f"Section {i} start should <= section {i+1} start"


class TestAC2DeterminismNoAnchor:
    def test_determinism_same_input_same_output(self):
        html = "X" * 900
        settings = make_settings(target=300, overlap=0)
        s1 = partition_html(html, empty_response(), settings)
        s2 = partition_html(html, empty_response(), settings)

        assert len(s1) == len(s2), "Should produce same number of sections"
        for i in range(len(s1)):
            assert s1[i] == s2[i], f"Section {i} should be identical"

    def test_deterministic_cuts_at_no_anchor(self):
        html = "X" * 900
        settings = make_settings(target=300, overlap=0)
        sections = partition_html(html, empty_response(), settings)

        expected_starts = [0, 300, 600]
        actual_starts = [s.global_start for s in sections]

        for i, expected in enumerate(expected_starts):
            assert (
                actual_starts[i] == expected
            ), f"Section {i} should start at {expected}, got {actual_starts[i]}"


class TestAC3AnchorSnap:
    def test_anchor_snap_pulls_cut_to_marker(self):
        marker = b"<section data-platform-comments>"
        prefix = b"A" * 310
        suffix = b"B" * (1000 - 310 - len(marker))
        html_bytes = prefix + marker + suffix
        html = html_bytes.decode("utf-8")

        hint = SectionHint(
            anchor_hint="<section data-platform-comments>", tolerance_bytes=50
        )
        response = BatchedUtteranceRedirectionResponse(
            page_kind=PageKind.ARTICLE,
            utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
            boundary_instructions="none",
            section_hints=[hint],
        )
        settings = make_settings(target=300, overlap=50)
        sections = partition_html(html, response, settings)

        assert len(sections) >= 2, "Should have at least 2 sections"

        non_overlap_start_of_second = 310
        overlap_bytes = 50
        expected_global_start = max(0, non_overlap_start_of_second - overlap_bytes)
        assert (
            sections[1].global_start == expected_global_start
        ), "Second section should snap and apply overlap"


class TestAC4OverlapBytes:
    def test_overlap_exactly_setting_bytes_for_plain_sections(self):
        html = "Y" * 900
        settings = make_settings(target=300, overlap=60)
        sections = partition_html(html, empty_response(), settings)

        assert len(sections) >= 2, "Should have at least 2 sections"

        assert (
            sections[1].overlap_with_prev_bytes == 60
        ), "Second section overlap should match setting"

        assert (
            sections[1].global_start == 300 - 60
        ), "Second section should start 60 bytes before deterministic cut"


class TestAC5Emoji4ByteAtBoundary:
    def test_emoji_4byte_at_cut_boundary_no_corruption(self):
        emoji = "🎉"
        pre = "A" * 299
        rest = "B" * 500
        html = pre + emoji + rest

        settings = make_settings(target=300, overlap=0)
        sections = partition_html(html, empty_response(), settings)

        full_text = "".join(s.html_slice for s in sections)
        assert "🎉" in full_text, "Emoji should be present in reconstructed text"
        assert full_text.count("🎉") == 1, "Exactly one emoji in output"

        for section in sections:
            _ = section.html_slice
            assert (
                isinstance(section.html_slice, str)
            ), "html_slice must be decodable string"


class TestEdgeCases:
    def test_empty_html(self):
        html = ""
        settings = make_settings(target=300, overlap=50)
        sections = partition_html(html, empty_response(), settings)

        assert sections == [], "Empty HTML should produce no sections"

    def test_single_section_under_target(self):
        html = "A" * 100
        settings = make_settings(target=300, overlap=50)
        sections = partition_html(html, empty_response(), settings)

        assert len(sections) == 1, "Should produce one section"
        assert sections[0].global_start == 0
        assert sections[0].html_slice == html
        assert sections[0].overlap_with_prev_bytes == 0, "First section has no overlap"

    def test_exact_multiple_of_target_no_remainder(self):
        html = "A" * 600
        settings = make_settings(target=300, overlap=50)
        sections = partition_html(html, empty_response(), settings)

        total_bytes = len(html.encode("utf-8"))
        assert (
            sections[-1].global_end == total_bytes
        ), "Last section must absorb to total"

    def test_hint_not_found_keeps_deterministic_cut(self):
        html = "A" * 1000
        hint = SectionHint(
            anchor_hint="<nonexistent>", tolerance_bytes=50
        )
        response = BatchedUtteranceRedirectionResponse(
            page_kind=PageKind.ARTICLE,
            utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
            boundary_instructions="none",
            section_hints=[hint],
        )
        settings = make_settings(target=300, overlap=0)
        sections = partition_html(html, response, settings)

        assert sections[1].global_start == 300, "Should stay at deterministic cut"

    def test_parent_context_recorded_on_snap(self):
        marker = b"<marker>"
        prefix = b"A" * 310
        suffix = b"B" * (1000 - 310 - len(marker))
        html_bytes = prefix + marker + suffix
        html = html_bytes.decode("utf-8")

        hint = SectionHint(
            anchor_hint="<marker>",
            tolerance_bytes=50,
            parent_context_text="parent context here",
        )
        response = BatchedUtteranceRedirectionResponse(
            page_kind=PageKind.ARTICLE,
            utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
            boundary_instructions="none",
            section_hints=[hint],
        )
        settings = make_settings(target=300, overlap=50)
        sections = partition_html(html, response, settings)

        assert (
            sections[1].parent_context_text == "parent context here"
        ), "Should record parent context from matched hint"

    def test_hint_with_custom_overlap(self):
        marker = b"<marker>"
        prefix = b"A" * 310
        suffix = b"B" * (1000 - 310 - len(marker))
        html_bytes = prefix + marker + suffix
        html = html_bytes.decode("utf-8")

        hint = SectionHint(
            anchor_hint="<marker>",
            tolerance_bytes=50,
            overlap_with_prev_bytes=100,
        )
        response = BatchedUtteranceRedirectionResponse(
            page_kind=PageKind.ARTICLE,
            utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
            boundary_instructions="none",
            section_hints=[hint],
        )
        settings = make_settings(target=300, overlap=50)
        sections = partition_html(html, response, settings)

        assert (
            sections[1].overlap_with_prev_bytes == 100
        ), "Should use hint's custom overlap over setting"


class TestAC6MultibyteBoundaryHintMetadata:
    def test_hint_metadata_survives_utf8_widen(self):
        from unittest.mock import patch

        prefix_len = 300
        prefix = "A" * prefix_len
        marker = "<section>"
        suffix = "B" * 600
        html = prefix + marker + suffix
        raw = html.encode("utf-8")

        marker_byte_pos = raw.index(marker.encode("utf-8"))

        hint = SectionHint(
            anchor_hint=marker,
            tolerance_bytes=50,
            parent_context_text="ctx-after-widen",
            overlap_with_prev_bytes=80,
        )
        response = BatchedUtteranceRedirectionResponse(
            page_kind=PageKind.ARTICLE,
            utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
            boundary_instructions="none",
            section_hints=[hint],
        )
        settings = make_settings(target=300, overlap=40)

        original_snap = __import__(
            "src.utterances.batched.partition",
            fromlist=["_snap_to_utf8_boundary"],
        )._snap_to_utf8_boundary

        def snap_that_shifts_anchor(raw_bytes: bytes, pos: int) -> int:
            if pos == marker_byte_pos:
                return marker_byte_pos + 1
            return original_snap(raw_bytes, pos)

        with patch(
            "src.utterances.batched.partition._snap_to_utf8_boundary",
            side_effect=snap_that_shifts_anchor,
        ):
            sections = partition_html(html, response, settings)

        assert len(sections) >= 2, "Should produce at least 2 sections"

        snapped_section = sections[1]
        assert snapped_section.parent_context_text == "ctx-after-widen", (
            "parent_context_text must survive UTF-8 boundary widen"
        )
        assert snapped_section.overlap_with_prev_bytes == 80, (
            "overlap_with_prev_bytes from hint must survive UTF-8 boundary widen"
        )
