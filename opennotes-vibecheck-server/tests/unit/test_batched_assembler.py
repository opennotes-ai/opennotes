import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.utterances._ids import stable_utterance_id
from src.utterances.batched.assembler import assemble_sections
from src.utterances.schema import BatchedUtteranceRedirectionResponse, Utterance, UtterancesPayload


@dataclass
class _HtmlSection:
    index: int
    html_slice: str
    global_start: int
    global_end: int
    overlap_with_prev_bytes: int
    parent_context_text: str


@dataclass
class _SectionResult:
    section: _HtmlSection
    payload: UtterancesPayload
    per_section_page_kind_guess: str


def make_section(
    index: int,
    html_slice: str,
    global_start: int,
    global_end: int,
    overlap_with_prev_bytes: int = 0,
    utterances: list[Utterance] | None = None,
) -> _SectionResult:
    if utterances is None:
        utterances = []
    return _SectionResult(
        section=_HtmlSection(
            index=index,
            html_slice=html_slice,
            global_start=global_start,
            global_end=global_end,
            overlap_with_prev_bytes=overlap_with_prev_bytes,
            parent_context_text="",
        ),
        payload=UtterancesPayload(
            source_url="http://example.com",
            scraped_at=datetime.now(UTC),
            utterances=utterances,
            page_kind=PageKind.OTHER,
            utterance_stream_type=UtteranceStreamType.UNKNOWN,
        ),
        per_section_page_kind_guess=PageKind.OTHER,
    )


def make_parent() -> BatchedUtteranceRedirectionResponse:
    return BatchedUtteranceRedirectionResponse(
        page_kind=PageKind.OTHER,
        utterance_stream_type=UtteranceStreamType.UNKNOWN,
        boundary_instructions="",
    )


@pytest.mark.asyncio
async def test_non_overlapping_sections_all_utterances_emitted():
    section0 = make_section(
        index=0,
        html_slice="<p>Hello world</p><p>Goodbye</p>",
        global_start=0,
        global_end=33,
        utterances=[
            Utterance(kind="post", text="Hello world"),
            Utterance(kind="comment", text="Goodbye"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>New text</p><p>More</p>",
        global_start=33,
        global_end=59,
        utterances=[
            Utterance(kind="post", text="New text"),
            Utterance(kind="comment", text="More"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0, section1],
            parent=make_parent(),
            sanitized_html="<p>Hello world</p><p>Goodbye</p><p>New text</p><p>More</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 4
    assert result.utterances[0].text == "Hello world"
    assert result.utterances[1].text == "Goodbye"
    assert result.utterances[2].text == "New text"
    assert result.utterances[3].text == "More"


@pytest.mark.asyncio
async def test_overlap_duplicate_dropped():
    section0 = make_section(
        index=0,
        html_slice="<p>Hello world</p><p>Goodbye</p>",
        global_start=0,
        global_end=33,
        utterances=[
            Utterance(kind="post", text="Hello world"),
            Utterance(kind="comment", text="Goodbye"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>Goodbye</p><p>New text</p>",
        global_start=20,
        global_end=49,
        overlap_with_prev_bytes=13,
        utterances=[
            Utterance(kind="comment", text="Goodbye"),
            Utterance(kind="post", text="New text"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0, section1],
            parent=make_parent(),
            sanitized_html="<p>Hello world</p><p>Goodbye</p><p>New text</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 3
    texts = [u.text for u in result.utterances]
    assert texts == ["Hello world", "Goodbye", "New text"]
    assert texts.count("Goodbye") == 1


@pytest.mark.asyncio
async def test_normalized_whitespace_fallback():
    section = make_section(
        index=0,
        html_slice="<p>Hello world</p>",
        global_start=0,
        global_end=18,
        utterances=[
            Utterance(kind="post", text="Hello  world"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section],
            parent=make_parent(),
            sanitized_html="<p>Hello world</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 1
    assert result.utterances[0].text == "Hello  world"


@pytest.mark.asyncio
async def test_utterance_not_found_still_emitted():
    section = make_section(
        index=0,
        html_slice="<p>Hello world</p>",
        global_start=0,
        global_end=18,
        utterances=[
            Utterance(kind="post", text="Nonexistent text"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section],
            parent=make_parent(),
            sanitized_html="<p>Hello world</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 1
    assert result.utterances[0].text == "Nonexistent text"


@pytest.mark.asyncio
async def test_overlap_region_different_utterances_both_kept():
    section0 = make_section(
        index=0,
        html_slice="<p>A</p><p>B</p><p>C</p><p>D</p>",
        global_start=0,
        global_end=100,
        utterances=[
            Utterance(kind="post", text="A"),
            Utterance(kind="comment", text="B"),
            Utterance(kind="post", text="C"),
            Utterance(kind="comment", text="D"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>X</p><p>Y</p><p>Z</p>",
        global_start=80,
        global_end=150,
        overlap_with_prev_bytes=20,
        utterances=[
            Utterance(kind="post", text="X"),
            Utterance(kind="comment", text="Y"),
            Utterance(kind="post", text="Z"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0, section1],
            parent=make_parent(),
            sanitized_html="",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 7
    texts = [u.text for u in result.utterances]
    assert "A" in texts
    assert "B" in texts
    assert "C" in texts
    assert "D" in texts
    assert "X" in texts
    assert "Y" in texts
    assert "Z" in texts


@pytest.mark.asyncio
async def test_stable_ids_deterministic():
    section = make_section(
        index=0,
        html_slice="<p>Hello</p>",
        global_start=0,
        global_end=12,
        utterances=[
            Utterance(kind="post", text="Hello"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result1 = await assemble_sections(
            section_results=[section],
            parent=make_parent(),
            sanitized_html="<p>Hello</p>",
            source_url="http://example.com",
        )

    section2 = make_section(
        index=0,
        html_slice="<p>Hello</p>",
        global_start=0,
        global_end=12,
        utterances=[
            Utterance(kind="post", text="Hello"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result2 = await assemble_sections(
            section_results=[section2],
            parent=make_parent(),
            sanitized_html="<p>Hello</p>",
            source_url="http://example.com",
        )

    assert len(result1.utterances) == 1
    assert len(result2.utterances) == 1
    assert result1.utterances[0].utterance_id == result2.utterances[0].utterance_id


def test_stable_ids_not_python_hash():
    uid = stable_utterance_id("post", "hello", 0, 0)
    old_style = f"post-{hash('hello') & 0xFFFFFFFF:08x}"
    assert uid != old_style
    assert uid == stable_utterance_id("post", "hello", 0, 0)


def test_stable_ids_subprocess_hashseed_independent():
    script = (
        "from src.utterances._ids import stable_utterance_id; "
        "print(stable_utterance_id('post', 'hello world', 0, 0))"
    )
    import os
    env0 = {**os.environ, "PYTHONHASHSEED": "0"}
    env1 = {**os.environ, "PYTHONHASHSEED": "1"}
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    r0 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env0, cwd=str(repo_root), check=False,
    )
    r1 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env1, cwd=str(repo_root), check=False,
    )
    assert r0.returncode == 0, r0.stderr
    assert r1.returncode == 0, r1.stderr
    assert r0.stdout.strip() == r1.stdout.strip()


@pytest.mark.asyncio
async def test_cross_section_parent_id_resolved():
    section0 = make_section(
        index=0,
        html_slice="<p>Root post</p>",
        global_start=0,
        global_end=16,
        utterances=[
            Utterance(kind="post", text="Root post", utterance_id="sec0-root"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>Reply</p>",
        global_start=16,
        global_end=28,
        utterances=[
            Utterance(kind="reply", text="Reply", parent_id="sec0-root"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0, section1],
            parent=make_parent(),
            sanitized_html="<p>Root post</p><p>Reply</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 2
    post = result.utterances[0]
    reply = result.utterances[1]

    assert post.kind == "post"
    assert reply.kind == "reply"
    assert reply.parent_id is not None
    assert reply.parent_id == post.utterance_id
    assert reply.parent_id != "sec0-root"


@pytest.mark.asyncio
async def test_orphan_reattaches_to_nearest_preceding_post():
    section = make_section(
        index=0,
        html_slice="<p>A</p><p>B</p><p>C</p>",
        global_start=0,
        global_end=24,
        utterances=[
            Utterance(kind="post", text="A"),
            Utterance(kind="reply", text="B", parent_id="nonexistent-id"),
            Utterance(kind="reply", text="C", parent_id="also-nonexistent"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section],
            parent=make_parent(),
            sanitized_html="<p>A</p><p>B</p><p>C</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 3
    post = result.utterances[0]
    reply_b = result.utterances[1]
    reply_c = result.utterances[2]

    assert post.kind == "post"
    assert reply_b.parent_id == post.utterance_id
    assert reply_c.parent_id == post.utterance_id


@pytest.mark.asyncio
async def test_orphan_no_preceding_post_gets_none():
    section = make_section(
        index=0,
        html_slice="<p>Reply only</p>",
        global_start=0,
        global_end=17,
        utterances=[
            Utterance(kind="reply", text="Reply only", parent_id="ghost"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section],
            parent=make_parent(),
            sanitized_html="<p>Reply only</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 1
    assert result.utterances[0].parent_id is None


@pytest.mark.asyncio
async def test_split_token_artifact_dropped_left_side_kept():
    section0 = make_section(
        index=0,
        html_slice="<p>hello apple airconditioner</p>",
        global_start=0,
        global_end=33,
        utterances=[
            Utterance(kind="post", text="hello apple airconditioner"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>conditioner gardenhose tantalum</p>",
        global_start=16,
        global_end=51,
        overlap_with_prev_bytes=19,
        utterances=[
            Utterance(kind="post", text="conditioner gardenhose tantalum"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0, section1],
            parent=make_parent(),
            sanitized_html="<p>hello apple airconditioner</p><p>conditioner gardenhose tantalum</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 1
    assert result.utterances[0].text == "hello apple airconditioner"


@pytest.mark.asyncio
async def test_non_split_overlap_both_kept():
    section0 = make_section(
        index=0,
        html_slice="<p>hello world</p>",
        global_start=0,
        global_end=18,
        utterances=[
            Utterance(kind="post", text="hello world"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>goodbye world</p>",
        global_start=10,
        global_end=30,
        overlap_with_prev_bytes=8,
        utterances=[
            Utterance(kind="post", text="goodbye world"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0, section1],
            parent=make_parent(),
            sanitized_html="<p>hello world</p><p>goodbye world</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 2
    texts = [u.text for u in result.utterances]
    assert "hello world" in texts
    assert "goodbye world" in texts


@pytest.mark.asyncio
async def test_attribute_media_called_exactly_once():
    section0 = make_section(
        index=0,
        html_slice="<p>Hello</p>",
        global_start=0,
        global_end=12,
        utterances=[
            Utterance(kind="post", text="Hello"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media") as mock_attr:
        result = await assemble_sections(
            section_results=[section0],
            parent=make_parent(),
            sanitized_html="<p>Hello</p>",
            source_url="http://example.com",
        )

    assert mock_attr.call_count == 1
    call_args = mock_attr.call_args
    assert call_args[0][0] == "<p>Hello</p>"
    assert call_args[0][1] == result.utterances


@pytest.mark.asyncio
async def test_normalized_fallback_offset_not_norm_position():
    html_slice = "<p>Hello   world  foo</p>"
    utterance_text = "Hello   world  foo"
    global_start = 50

    original_pos = html_slice.find(utterance_text)
    assert original_pos != -1, "utterance_text must appear verbatim in html_slice for this test"

    section = make_section(
        index=0,
        html_slice=html_slice,
        global_start=global_start,
        global_end=global_start + len(html_slice.encode("utf-8")),
        utterances=[Utterance(kind="post", text=utterance_text)],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section],
            parent=make_parent(),
            sanitized_html=html_slice,
            source_url="http://example.com",
        )

    assert len(result.utterances) == 1


@pytest.mark.asyncio
async def test_normalized_fallback_does_not_use_norm_position():
    html_slice = "     <p>Hello   world</p>"
    utterance_with_extra_ws = "Hello   world"
    norm_of_utterance = "Hello world"

    norm_of_html = "Hello world"
    assert norm_of_utterance in norm_of_html

    global_start = 100

    section = make_section(
        index=0,
        html_slice=html_slice,
        global_start=global_start,
        global_end=global_start + len(html_slice.encode("utf-8")),
        utterances=[Utterance(kind="post", text=utterance_with_extra_ws)],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section],
            parent=make_parent(),
            sanitized_html=html_slice,
            source_url="http://example.com",
        )

    assert len(result.utterances) == 1


@pytest.mark.asyncio
async def test_normalized_fallback_offset_is_global_start_not_norm_string_pos():
    leading_spaces = "     "
    html_slice = leading_spaces + "<p>Hello world</p>"
    utterance_text = "Hello  world"
    global_start = 200

    assert html_slice.find(utterance_text) == -1, "utterance must NOT appear verbatim"

    from src.utterances._ids import _norm_ws
    norm_html = _norm_ws(html_slice)
    norm_utt = _norm_ws(utterance_text)
    norm_match = norm_html.find(norm_utt)
    assert norm_match != -1, "normalized match must exist"
    assert norm_match != 0, "norm match pos must be non-zero so we can detect the bug"

    section = make_section(
        index=0,
        html_slice=html_slice,
        global_start=global_start,
        global_end=global_start + len(html_slice.encode("utf-8")),
        utterances=[Utterance(kind="post", text=utterance_text)],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section],
            parent=make_parent(),
            sanitized_html=html_slice,
            source_url="http://example.com",
        )

    assert len(result.utterances) == 1

    from src.utterances._ids import stable_utterance_id
    expected_id_at_global_start = stable_utterance_id("post", utterance_text, global_start, 0)
    wrong_id_at_norm_pos = stable_utterance_id("post", utterance_text, global_start + norm_match, 0)

    assert result.utterances[0].utterance_id == expected_id_at_global_start, (
        f"global_offset must be global_start ({global_start}), "
        f"not global_start+norm_match ({global_start + norm_match}). "
        f"Got utterance_id={result.utterances[0].utterance_id!r}, "
        f"wrong id would be {wrong_id_at_norm_pos!r}"
    )


@pytest.mark.asyncio
async def test_attribute_media_receives_full_sanitized_html_not_slice():
    section0 = make_section(
        index=0,
        html_slice="<p>first</p>",
        global_start=0,
        global_end=12,
        utterances=[
            Utterance(kind="post", text="first"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>second</p>",
        global_start=12,
        global_end=25,
        utterances=[
            Utterance(kind="post", text="second"),
        ],
    )
    full_html = "<html><body>full content</body></html>"

    with patch("src.utterances.batched.assembler.attribute_media") as mock_attr:
        await assemble_sections(
            section_results=[section0, section1],
            parent=make_parent(),
            sanitized_html=full_html,
            source_url="http://example.com",
        )

    assert mock_attr.call_count == 1
    assert mock_attr.call_args[0][0] == full_html


@pytest.mark.asyncio
async def test_full_integration_dedup_ids_parent_attribute_media():
    section0 = make_section(
        index=0,
        html_slice="<p>Root post</p><p>Overlap text</p>",
        global_start=0,
        global_end=35,
        utterances=[
            Utterance(kind="post", text="Root post", utterance_id="orig-root"),
            Utterance(kind="comment", text="Overlap text"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>Overlap text</p><p>Reply here</p>",
        global_start=16,
        global_end=51,
        overlap_with_prev_bytes=19,
        utterances=[
            Utterance(kind="comment", text="Overlap text"),
            Utterance(kind="reply", text="Reply here", parent_id="orig-root"),
        ],
    )
    full_html = "<p>Root post</p><p>Overlap text</p><p>Reply here</p>"

    with patch("src.utterances.batched.assembler.attribute_media") as mock_attr:
        result1 = await assemble_sections(
            section_results=[section0, section1],
            parent=make_parent(),
            sanitized_html=full_html,
            source_url="http://example.com",
        )

    section0b = make_section(
        index=0,
        html_slice="<p>Root post</p><p>Overlap text</p>",
        global_start=0,
        global_end=35,
        utterances=[
            Utterance(kind="post", text="Root post", utterance_id="orig-root"),
            Utterance(kind="comment", text="Overlap text"),
        ],
    )
    section1b = make_section(
        index=1,
        html_slice="<p>Overlap text</p><p>Reply here</p>",
        global_start=16,
        global_end=51,
        overlap_with_prev_bytes=19,
        utterances=[
            Utterance(kind="comment", text="Overlap text"),
            Utterance(kind="reply", text="Reply here", parent_id="orig-root"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result2 = await assemble_sections(
            section_results=[section0b, section1b],
            parent=make_parent(),
            sanitized_html=full_html,
            source_url="http://example.com",
        )

    assert len(result1.utterances) == 3
    assert result1.utterances[0].utterance_id == result2.utterances[0].utterance_id
    assert result1.utterances[1].utterance_id == result2.utterances[1].utterance_id

    root_id = result1.utterances[0].utterance_id
    reply = result1.utterances[2]
    assert reply.kind == "reply"
    assert reply.parent_id == root_id

    assert mock_attr.call_count == 1
    assert mock_attr.call_args[0][0] == full_html


@pytest.mark.asyncio
async def test_assembler_propagates_parent_page_title():
    parent = BatchedUtteranceRedirectionResponse(
        page_kind=PageKind.BLOG_POST,
        utterance_stream_type=UtteranceStreamType.COMMENT_SECTION,
        page_title="Parent Title From Redirect",
        boundary_instructions="",
    )
    section0 = make_section(
        index=0,
        html_slice="<p>A</p>",
        global_start=0,
        global_end=8,
        utterances=[],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>B</p>",
        global_start=8,
        global_end=16,
        utterances=[Utterance(kind="post", text="B")],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0, section1],
            parent=parent,
            sanitized_html="<p>A</p><p>B</p>",
            source_url="http://example.com",
        )

    assert result.page_title == "Parent Title From Redirect"
    assert result.page_kind == PageKind.BLOG_POST
    assert result.utterance_stream_type == UtteranceStreamType.COMMENT_SECTION


@pytest.mark.asyncio
async def test_cross_section_parent_id_not_nearest_preceding_post():
    parent = make_parent()
    section0 = make_section(
        index=0,
        html_slice="<p>Sec0 post</p>",
        global_start=0,
        global_end=16,
        utterances=[
            Utterance(kind="post", text="Sec0 post", utterance_id="sec0-original-id"),
        ],
    )
    section1 = make_section(
        index=1,
        html_slice="<p>Sec1 post</p>",
        global_start=16,
        global_end=32,
        utterances=[
            Utterance(kind="post", text="Sec1 post", utterance_id="sec1-post-id"),
        ],
    )
    section2 = make_section(
        index=2,
        html_slice="<p>Reply to sec0</p>",
        global_start=32,
        global_end=52,
        utterances=[
            Utterance(kind="reply", text="Reply to sec0", parent_id="sec0-original-id"),
        ],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0, section1, section2],
            parent=parent,
            sanitized_html="<p>Sec0 post</p><p>Sec1 post</p><p>Reply to sec0</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 3
    sec0_post = result.utterances[0]
    sec1_post = result.utterances[1]
    reply = result.utterances[2]

    assert sec0_post.text == "Sec0 post"
    assert sec1_post.text == "Sec1 post"
    assert reply.text == "Reply to sec0"
    assert reply.parent_id == sec0_post.utterance_id
    assert reply.parent_id != sec1_post.utterance_id


@pytest.mark.asyncio
async def test_assemble_sections_is_async():
    section0 = make_section(
        index=0,
        html_slice="<p>Hello</p>",
        global_start=0,
        global_end=12,
        utterances=[Utterance(kind="post", text="Hello")],
    )

    with patch("src.utterances.batched.assembler.attribute_media"):
        result = await assemble_sections(
            section_results=[section0],
            parent=make_parent(),
            sanitized_html="<p>Hello</p>",
            source_url="http://example.com",
        )

    assert len(result.utterances) == 1
