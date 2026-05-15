import re
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import dataclass

import pytest

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.utterances.schema import Utterance, UtterancesPayload, BatchedUtteranceRedirectionResponse
from src.utterances.batched.assembler import assemble_sections
from src.utterances._ids import stable_utterance_id


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
            scraped_at=datetime.now(timezone.utc),
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


def test_non_overlapping_sections_all_utterances_emitted():
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

    result = assemble_sections(
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


def test_overlap_duplicate_dropped():
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

    result = assemble_sections(
        section_results=[section0, section1],
        parent=make_parent(),
        sanitized_html="<p>Hello world</p><p>Goodbye</p><p>New text</p>",
        source_url="http://example.com",
    )

    assert len(result.utterances) == 3
    texts = [u.text for u in result.utterances]
    assert texts == ["Hello world", "Goodbye", "New text"]
    assert texts.count("Goodbye") == 1


def test_normalized_whitespace_fallback():
    section = make_section(
        index=0,
        html_slice="<p>Hello world</p>",
        global_start=0,
        global_end=18,
        utterances=[
            Utterance(kind="post", text="Hello  world"),
        ],
    )

    result = assemble_sections(
        section_results=[section],
        parent=make_parent(),
        sanitized_html="<p>Hello world</p>",
        source_url="http://example.com",
    )

    assert len(result.utterances) == 1
    assert result.utterances[0].text == "Hello  world"


def test_utterance_not_found_still_emitted():
    section = make_section(
        index=0,
        html_slice="<p>Hello world</p>",
        global_start=0,
        global_end=18,
        utterances=[
            Utterance(kind="post", text="Nonexistent text"),
        ],
    )

    result = assemble_sections(
        section_results=[section],
        parent=make_parent(),
        sanitized_html="<p>Hello world</p>",
        source_url="http://example.com",
    )

    assert len(result.utterances) == 1
    assert result.utterances[0].text == "Nonexistent text"


def test_overlap_region_different_utterances_both_kept():
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

    result = assemble_sections(
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


def test_stable_ids_deterministic():
    section = make_section(
        index=0,
        html_slice="<p>Hello</p>",
        global_start=0,
        global_end=12,
        utterances=[
            Utterance(kind="post", text="Hello"),
        ],
    )

    result1 = assemble_sections(
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

    result2 = assemble_sections(
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
    r0 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env0, cwd="/Users/mike/code/opennotes-ai/multiverse/worktrees/tasks-1649/opennotes-vibecheck-server"
    )
    r1 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env1, cwd="/Users/mike/code/opennotes-ai/multiverse/worktrees/tasks-1649/opennotes-vibecheck-server"
    )
    assert r0.returncode == 0, r0.stderr
    assert r1.returncode == 0, r1.stderr
    assert r0.stdout.strip() == r1.stdout.strip()


def test_cross_section_parent_id_resolved():
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

    result = assemble_sections(
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


def test_orphan_reattaches_to_nearest_preceding_post():
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

    result = assemble_sections(
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


def test_orphan_no_preceding_post_gets_none():
    section = make_section(
        index=0,
        html_slice="<p>Reply only</p>",
        global_start=0,
        global_end=17,
        utterances=[
            Utterance(kind="reply", text="Reply only", parent_id="ghost"),
        ],
    )

    result = assemble_sections(
        section_results=[section],
        parent=make_parent(),
        sanitized_html="<p>Reply only</p>",
        source_url="http://example.com",
    )

    assert len(result.utterances) == 1
    assert result.utterances[0].parent_id is None
