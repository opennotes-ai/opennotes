from __future__ import annotations

from src.url_content_scan.utterances.annotate_html import annotate_utterances_in_html
from src.url_content_scan.utterances.schema import Utterance


def _utterance(
    text: str,
    utterance_id: str = "u1",
    kind: str = "post",
) -> Utterance:
    return Utterance(
        utterance_id=utterance_id,
        kind=kind,
        text=text,
        author=None,
        timestamp=None,
        parent_id=None,
    )


def test_annotate_utterances_returns_unchanged_when_no_utterances() -> None:
    html = "<html><body><p>Hello world</p></body></html>"
    result = annotate_utterances_in_html(html, [])
    assert result == html


def test_annotate_utterances_adds_data_attribute_to_matching_block() -> None:
    html = "<html><body><p>Hello world</p></body></html>"
    utterances = [_utterance("Hello world", utterance_id="u1")]
    result = annotate_utterances_in_html(html, utterances)
    assert 'data-utterance-id="u1"' in result


def test_annotate_utterances_does_not_annotate_when_text_not_found() -> None:
    html = "<html><body><p>Some other content</p></body></html>"
    utterances = [_utterance("Missing text", utterance_id="u1")]
    result = annotate_utterances_in_html(html, utterances)
    assert "data-utterance-id" not in result


def test_annotate_utterances_skips_utterances_without_id() -> None:
    html = "<html><body><p>Hello world</p></body></html>"
    utterance = Utterance(
        utterance_id=None,
        kind="post",
        text="Hello world",
    )
    result = annotate_utterances_in_html(html, [utterance])
    assert "data-utterance-id" not in result


def test_annotate_utterances_annotates_multiple_utterances() -> None:
    html = "<html><body><p>First utterance text</p><p>Second utterance text</p></body></html>"
    utterances = [
        _utterance("First utterance text", utterance_id="u1"),
        _utterance("Second utterance text", utterance_id="u2"),
    ]
    result = annotate_utterances_in_html(html, utterances)
    assert 'data-utterance-id="u1"' in result
    assert 'data-utterance-id="u2"' in result


def test_annotate_utterances_reveals_hidden_openweb_ancestor() -> None:
    html = (
        "<html><body>"
        '<div id="openweb-container" style="display:none">'
        "<p>Hidden comment text</p>"
        "</div>"
        "</body></html>"
    )
    utterances = [_utterance("Hidden comment text", utterance_id="u1")]
    result = annotate_utterances_in_html(html, utterances)
    assert 'data-utterance-id="u1"' in result
    assert "data-utterance-ancestor" in result


def test_annotate_utterances_injects_visible_style_for_hidden_ancestors() -> None:
    html = (
        "<html><body>"
        '<div class="spcv_hidden" style="height:0">'
        "<p>Hidden comment text</p>"
        "</div>"
        "</body></html>"
    )
    utterances = [_utterance("Hidden comment text", utterance_id="u1")]
    result = annotate_utterances_in_html(html, utterances)
    assert "data-utterance-style" in result
    assert "display: revert" in result


def test_annotate_utterances_does_not_double_annotate_same_element() -> None:
    html = "<html><body><p>Same text appears once</p></body></html>"
    utterances = [
        _utterance("Same text appears once", utterance_id="u1"),
        _utterance("Same text appears once", utterance_id="u2"),
    ]
    result = annotate_utterances_in_html(html, utterances)
    assert result.count("data-utterance-id") == 1
