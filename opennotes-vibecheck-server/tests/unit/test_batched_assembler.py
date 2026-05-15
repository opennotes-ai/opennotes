import re
from datetime import datetime, timezone
from dataclasses import dataclass

import pytest

from src.analyses.schemas import PageKind, UtteranceStreamType
from src.utterances.schema import Utterance, UtterancesPayload, BatchedUtteranceRedirectionResponse
from src.utterances.batched.assembler import assemble_sections


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
