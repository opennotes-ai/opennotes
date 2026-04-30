from bs4 import BeautifulSoup
from bs4.element import Tag

from src.utterances.annotate_html import annotate_utterances_in_html
from src.utterances.schema import Utterance


def utterance(utterance_id: str, text: str) -> Utterance:
    return Utterance(utterance_id=utterance_id, kind="comment", text=text)


def find_tag(soup: BeautifulSoup, name: str) -> Tag:
    tag = soup.find(name)
    assert isinstance(tag, Tag)
    return tag


def test_annotates_single_block_element() -> None:
    annotated = annotate_utterances_in_html(
        "<main><p>Alice opens the thread calmly.</p></main>",
        [utterance("comment-0-aaa", "Alice opens the thread calmly.")],
    )

    soup = BeautifulSoup(annotated, "html.parser")
    assert find_tag(soup, "p")["data-utterance-id"] == "comment-0-aaa"


def test_annotates_parent_when_utterance_spans_inline_children() -> None:
    annotated = annotate_utterances_in_html(
        "<main><p>Alice <em>pushes</em> back softly.</p></main>",
        [utterance("comment-1-bbb", "Alice pushes back softly.")],
    )

    soup = BeautifulSoup(annotated, "html.parser")
    assert find_tag(soup, "p")["data-utterance-id"] == "comment-1-bbb"


def test_unmatched_utterance_does_not_block_other_matches() -> None:
    annotated = annotate_utterances_in_html(
        "<main><p>Bob stays measured.</p></main>",
        [
            utterance("comment-0-miss", "This sentence is absent."),
            utterance("comment-1-hit", "Bob stays measured."),
        ],
    )

    soup = BeautifulSoup(annotated, "html.parser")
    assert find_tag(soup, "p")["data-utterance-id"] == "comment-1-hit"


def test_repeated_text_marks_only_first_unannotated_occurrence() -> None:
    annotated = annotate_utterances_in_html(
        "<main><p>same text</p><p>same text</p></main>",
        [
            utterance("comment-0-first", "same text"),
            utterance("comment-1-second", "same text"),
        ],
    )

    paragraphs = BeautifulSoup(annotated, "html.parser").find_all("p")
    assert paragraphs[0]["data-utterance-id"] == "comment-0-first"
    assert paragraphs[1]["data-utterance-id"] == "comment-1-second"


def test_whitespace_differences_do_not_prevent_matching() -> None:
    annotated = annotate_utterances_in_html(
        "<main><p>foo\n\n  bar\tbaz</p></main>",
        [utterance("comment-2-space", "foo bar baz")],
    )

    soup = BeautifulSoup(annotated, "html.parser")
    assert find_tag(soup, "p")["data-utterance-id"] == "comment-2-space"


def test_idempotent_for_already_annotated_html() -> None:
    html = "<main><p>Alice opens the thread calmly.</p></main>"
    utterances = [utterance("comment-0-aaa", "Alice opens the thread calmly.")]

    once = annotate_utterances_in_html(html, utterances)
    twice = annotate_utterances_in_html(once, utterances)

    assert BeautifulSoup(twice, "html.parser").decode() == BeautifulSoup(
        once, "html.parser"
    ).decode()


def test_empty_utterance_list_returns_html_unchanged() -> None:
    html = "<main><p>No markers here.</p></main>"

    assert annotate_utterances_in_html(html, []) == html
